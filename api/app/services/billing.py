"""Invoicing, subscriptions, proration and payments.  Spec §5.3 and §8.

The Billing verifier's invariant is enforced here before anything is issued:
Σ invoices − Σ credit notes must equal the order total, and no
(subscription, period) may be billed twice.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.billing import decide_invoice_plan, prorate
from app.domain.exceptions import VerifierFailure
from app.domain.types import (
    InvoiceLineSnapshot,
    InvoicePlanSnapshot,
    VerifierVerdict,
)
from app.domain.verifiers import verify_billing
from app.models.enums import InvoiceKind, InvoiceStatus, SubscriptionStatus
from app.models.tables import (
    CreditNote,
    Outbox,
    Invoice,
    InvoiceLine,
    Payment,
    Product,
    Quotation,
    QuoteLine,
    Subscription,
    SubscriptionPlan,
)
from app.services.decision_log import run_agent

BILLING_INTERVAL_DAYS = 30


def build_invoice_snapshot(
    session: Session, quotation: Quotation, as_of: date
) -> InvoicePlanSnapshot:
    lines = session.scalars(
        select(QuoteLine)
        .where(QuoteLine.quotation_id == quotation.id)
        .order_by(QuoteLine.id)
    ).all()

    snapshot_lines = []
    for line in lines:
        product = session.get(Product, line.product_id)
        snapshot_lines.append(
            InvoiceLineSnapshot(
                product_id=line.product_id,
                description=product.name if product else f"product {line.product_id}",
                qty=line.qty,
                unit_price=line.unit_price,
                discount_pct=line.discount_pct,
                is_recurring=line.is_recurring,
            )
        )

    return InvoicePlanSnapshot(
        quotation_id=quotation.id,
        as_of=as_of,
        lines=snapshot_lines,
        billing_interval_days=BILLING_INTERVAL_DAYS,
    )


def generate_invoices(
    session: Session,
    quotation: Quotation,
    as_of: date,
    actor_id: int | None = None,
) -> dict:
    """Partition the quote and issue what is due now.

    Hybrid (§5.3): one-time lines invoice immediately; recurring lines create a
    subscription whose first period is billed now and whose `next_bill_date` is
    set for the scheduler.
    """
    snapshot = build_invoice_snapshot(session, quotation, as_of)
    decision, verdict, _reasons = run_agent(
        session,
        agent="billing",
        decide=decide_invoice_plan,
        snapshot=snapshot,
        verifier=None,  # the money invariant is checked below, once rows exist
        quotation_id=quotation.id,
        actor_id=actor_id,
    )
    plan = decision.output

    issued: list[Invoice] = []

    if plan["one_time"]["lines"]:
        issued.append(
            _issue(session, quotation, InvoiceKind.ONE_TIME,
                   plan["one_time"]["lines"], Decimal(plan["one_time"]["total"]))
        )

    subscription = None
    if plan["recurring"]["lines"]:
        sub_meta = plan["subscription"]
        subscription = _open_subscription(session, quotation, sub_meta)
        issued.append(
            _issue(
                session, quotation, InvoiceKind.RECURRING,
                plan["recurring"]["lines"], Decimal(plan["recurring"]["total"]),
                subscription=subscription, period_key=sub_meta["period_key"],
            )
        )

    session.flush()
    _assert_books_balance(session, quotation, Decimal(plan["order_total"]))

    return {
        "quotation_id": quotation.id,
        "invoices": [
            {"id": inv.id, "kind": str(inv.kind), "total": str(inv.total),
             "status": str(inv.status), "period_key": inv.period_key}
            for inv in issued
        ],
        "subscription": (
            {"id": subscription.id, "start_date": str(subscription.start_date),
             "next_bill_date": str(subscription.next_bill_date),
             "status": str(subscription.status)}
            if subscription else None
        ),
        "order_total": plan["order_total"],
        "explanation": decision.explanation,
        "verifier_verdict": str(verdict),
    }


def _issue(
    session: Session,
    quotation: Quotation,
    kind: InvoiceKind,
    rows: list[dict],
    total: Decimal,
    subscription: Subscription | None = None,
    period_key: str | None = None,
) -> Invoice:
    invoice = Invoice(
        quotation_id=quotation.id,
        subscription_id=subscription.id if subscription else None,
        period_key=period_key,
        kind=kind,
        total=total,
        status=InvoiceStatus.ISSUED,
    )
    session.add(invoice)
    session.flush()

    for row in rows:
        session.add(
            InvoiceLine(
                invoice_id=invoice.id,
                description=row["description"],
                qty=row["qty"],
                unit_price=Decimal(row["unit_price"]),
                amount=Decimal(row["amount"]),
            )
        )
    session.flush()
    return invoice


def _open_subscription(
    session: Session, quotation: Quotation, meta: dict
) -> Subscription:
    plan = session.scalar(select(SubscriptionPlan).order_by(SubscriptionPlan.id))
    subscription = Subscription(
        quotation_id=quotation.id,
        plan_id=plan.id if plan else 1,
        start_date=date.fromisoformat(meta["start_date"]),
        next_bill_date=date.fromisoformat(meta["next_bill_date"]),
        status=SubscriptionStatus.ACTIVE,
    )
    session.add(subscription)
    session.flush()
    return subscription


def _assert_books_balance(
    session: Session, quotation: Quotation, order_total: Decimal
) -> None:
    """§8: block the invoice and raise for Finance if the books do not tie."""
    invoices = list(session.scalars(
        select(Invoice.total).where(Invoice.quotation_id == quotation.id)
    ).all())
    credit_notes = list(session.scalars(
        select(CreditNote.amount)
        .join(Invoice, CreditNote.invoice_id == Invoice.id)
        .where(Invoice.quotation_id == quotation.id)
    ).all())
    period_keys = [
        (row.subscription_id, row.period_key)
        for row in session.scalars(
            select(Invoice).where(
                Invoice.quotation_id == quotation.id,
                Invoice.subscription_id.is_not(None),
            )
        ).all()
    ]

    verdict, reasons = verify_billing(
        order_total, invoices, credit_notes, period_keys
    )
    if verdict is VerifierVerdict.FAIL:
        raise VerifierFailure("billing", reasons)


# --------------------------------------------------------------------------
# mid-period plan changes
# --------------------------------------------------------------------------


def change_subscription_amount(
    session: Session,
    subscription: Subscription,
    change_date: date,
    old_amount: Decimal,
    new_amount: Decimal,
) -> dict:
    """Apply a mid-period change. A negative delta becomes a CREDIT NOTE, never
    a negative invoice line (§5.3)."""
    period_start = subscription.next_bill_date - timedelta(days=BILLING_INTERVAL_DAYS)
    proration = prorate(
        period_start, subscription.next_bill_date, change_date, old_amount, new_amount
    )

    latest = session.scalar(
        select(Invoice)
        .where(Invoice.subscription_id == subscription.id)
        .order_by(Invoice.id.desc())
    )

    result = {
        "credit": str(proration.credit),
        "charge": str(proration.charge),
        "delta": str(proration.delta),
        "emitted": None,
    }

    if proration.delta < 0 and latest is not None:
        session.add(CreditNote(
            invoice_id=latest.id,
            amount=-proration.delta,
            reason=f"Downgrade prorated from {change_date}",
        ))
        result["emitted"] = "credit_note"
    elif proration.delta > 0:
        invoice = Invoice(
            quotation_id=subscription.quotation_id,
            subscription_id=subscription.id,
            period_key=f"{change_date.strftime('%Y-%m')}-adj",
            kind=InvoiceKind.RECURRING,
            total=proration.delta,
            status=InvoiceStatus.ISSUED,
        )
        session.add(invoice)
        session.flush()
        session.add(InvoiceLine(
            invoice_id=invoice.id,
            description=f"Prorated upgrade from {change_date}",
            qty=1,
            unit_price=proration.delta,
            amount=proration.delta,
        ))
        result["emitted"] = "invoice"

    session.flush()
    return result


def cancel_subscription(
    session: Session,
    subscription: Subscription,
    as_of: date,
    reason: str,
) -> dict:
    """Cancel at end of period (§5.3's cancellation policy).

    The remaining paid-for period is NOT refunded: the customer keeps service
    until `next_bill_date` and simply is not billed again. Cancelling mid-period
    with a refund is a proration, which is what `change_subscription_amount`
    is for — conflating the two is how a cancellation silently becomes a credit.
    """
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise VerifierFailure("billing", ["subscription is already cancelled"])

    subscription.status = SubscriptionStatus.CANCELLED
    session.add(Outbox(topic="subscription.cancelled", payload={
        "subscription_id": subscription.id,
        "quotation_id": subscription.quotation_id,
        "effective": str(subscription.next_bill_date),
        "reason": reason,
    }))
    session.flush()
    return {
        "subscription_id": subscription.id,
        "status": str(subscription.status),
        "service_until": str(subscription.next_bill_date),
        "refunded": False,
        "reason": reason,
    }


def pause_subscription(
    session: Session, subscription: Subscription, paused: bool
) -> dict:
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise VerifierFailure("billing", ["a cancelled subscription cannot be paused"])
    subscription.status = (
        SubscriptionStatus.PAUSED if paused else SubscriptionStatus.ACTIVE
    )
    session.flush()
    return {
        "subscription_id": subscription.id,
        "status": str(subscription.status),
        "next_bill_date": str(subscription.next_bill_date),
    }


# --------------------------------------------------------------------------
# payment
# --------------------------------------------------------------------------


def record_payment(
    session: Session,
    quotation: Quotation,
    amount: Decimal,
    method: str,
    paid_at: datetime | None = None,
) -> dict:
    """Record a payment. Returns whether the quotation is now fully paid — the
    guard on INVOICED -> PAID (§7)."""
    invoices = list(session.scalars(
        select(Invoice).where(Invoice.quotation_id == quotation.id)
    ).all())
    if not invoices:
        raise VerifierFailure("billing", ["no invoice to pay"])

    target = next(
        (i for i in invoices if i.status != InvoiceStatus.PAID), invoices[-1]
    )
    session.add(Payment(
        invoice_id=target.id,
        amount=amount,
        method=method,
        paid_at=paid_at or datetime.now(timezone.utc),
    ))
    session.flush()

    billed = sum((i.total for i in invoices), Decimal(0))
    credited = sum(
        (c for c in session.scalars(
            select(CreditNote.amount)
            .join(Invoice, CreditNote.invoice_id == Invoice.id)
            .where(Invoice.quotation_id == quotation.id)
        ).all()),
        Decimal(0),
    )
    paid = sum(
        (p for p in session.scalars(
            select(Payment.amount)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .where(Invoice.quotation_id == quotation.id)
        ).all()),
        Decimal(0),
    )

    # What the customer actually owes: invoiced less anything credited back.
    # Billing against `billed` alone would over-collect by the credit note.
    due = billed - credited
    outstanding = due - paid
    fully_paid = outstanding <= 0
    if fully_paid:
        for invoice in invoices:
            invoice.status = InvoiceStatus.PAID
    session.flush()

    return {
        "billed": str(billed),
        "credited": str(credited),
        "amount_due": str(due),
        "paid": str(paid),
        "outstanding": str(max(Decimal(0), outstanding)),
        "overpaid": str(max(Decimal(0), -outstanding)),
        "fully_paid": fully_paid,
    }


def amount_due(session: Session, quotation: Quotation) -> dict:
    """What is owed right now: invoiced, less credits, less payments."""
    billed = sum(
        session.scalars(
            select(Invoice.total).where(Invoice.quotation_id == quotation.id)
        ).all(),
        Decimal(0),
    )
    credited = sum(
        session.scalars(
            select(CreditNote.amount)
            .join(Invoice, CreditNote.invoice_id == Invoice.id)
            .where(Invoice.quotation_id == quotation.id)
        ).all(),
        Decimal(0),
    )
    paid = sum(
        session.scalars(
            select(Payment.amount)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .where(Invoice.quotation_id == quotation.id)
        ).all(),
        Decimal(0),
    )
    return {
        "billed": str(billed),
        "credited": str(credited),
        "amount_due": str(billed - credited),
        "paid": str(paid),
        "outstanding": str(max(Decimal(0), billed - credited - paid)),
    }
