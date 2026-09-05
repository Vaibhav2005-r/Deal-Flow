"""Operational list/detail surfaces.  Product flow screens 2, 7, 9, 12, 13.

Read-only views over data the other phases already produce. Thin (§12): these
query and shape, they never decide anything.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_internal_user, get_session
from app.models.enums import InvoiceStatus, QuoteState, Role, SubscriptionStatus
from app.models.tables import (
    ApprovalRequest,
    CreditNote,
    Customer,
    FulfillmentLine,
    FulfillmentPlan,
    Invoice,
    InvoiceLine,
    Payment,
    Product,
    Quotation,
    QuoteLine,
    Stock,
    Subscription,
    User,
    Warehouse,
)

router = APIRouter(prefix="/api", tags=["operations"])

#: States where the deal is live — neither a draft nor finished.
OPEN_STATES = [
    QuoteState.RISK_SCORED, QuoteState.PENDING_MANAGER, QuoteState.PENDING_FINANCE,
    QuoteState.READY_TO_FULFILL, QuoteState.SENT, QuoteState.UNDER_NEGOTIATION,
    QuoteState.CONFIRMED, QuoteState.FULFILLING,
]
AWAITING_FULFILLMENT = [QuoteState.CONFIRMED, QuoteState.FULFILLING]


def _net_total(session: Session, quotation_id: int) -> Decimal:
    lines = session.scalars(
        select(QuoteLine).where(QuoteLine.quotation_id == quotation_id)
    ).all()
    return sum(
        (
            ln.unit_price * Decimal(ln.qty)
            * (Decimal(1) - ln.discount_pct / Decimal(100))
            for ln in lines
        ),
        Decimal(0),
    )


# --------------------------------------------------------------------------
# screen 2 — sales dashboard
# --------------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    """The landing view: what needs attention, and what just happened."""
    pending = session.scalar(
        select(func.count(func.distinct(Quotation.id)))
        .select_from(Quotation)
        .where(Quotation.state.in_(
            [QuoteState.PENDING_MANAGER, QuoteState.PENDING_FINANCE]
        ))
    ) or 0
    open_quotes = session.scalar(
        select(func.count()).select_from(Quotation)
        .where(Quotation.state.in_(OPEN_STATES))
    ) or 0
    awaiting = session.scalar(
        select(func.count()).select_from(Quotation)
        .where(Quotation.state.in_(AWAITING_FULFILLMENT))
    ) or 0
    unpaid = session.scalar(
        select(func.count()).select_from(Invoice)
        .where(Invoice.status != InvoiceStatus.PAID)
    ) or 0

    # At-risk is computed by the Sentinel service (T1). Imported lazily so the
    # dashboard does not pull sklearn on every other route's import.
    from app.services.sentinel import assess_all_quotations

    at_risk = [row for row in assess_all_quotations(session) if row["alert"]]

    recent = session.scalars(
        select(Quotation)
        .where(Quotation.state.in_(OPEN_STATES + [QuoteState.PAID]))
        .order_by(Quotation.last_activity_at.desc())
        .limit(8)
    ).all()

    activity = []
    for q in recent:
        customer = session.get(Customer, q.customer_id)
        rep = session.get(User, q.rep_id)
        activity.append({
            "quotation_id": q.id,
            "customer_name": customer.name if customer else "",
            "state": str(q.state),
            "rep_name": rep.full_name if rep else "",
            "risk_score": str(q.risk_score) if q.risk_score is not None else None,
            "last_activity_at": q.last_activity_at.isoformat(),
        })

    return {
        "role": str(user.role),
        "full_name": user.full_name,
        "cards": {
            "pending_approvals": pending,
            "open_quotations": open_quotes,
            "at_risk_deals": len(at_risk),
            "awaiting_fulfillment": awaiting,
            "unpaid_invoices": unpaid,
        },
        "at_risk": [
            {
                "quotation_id": r["quotation_id"],
                "customer_name": r["customer_name"],
                "state": r["state"],
                "days_inactive": r["days_inactive"],
                "reason": (r["explanation"] or ["flagged"])[0],
            }
            for r in at_risk[:5]
        ],
        "recent_activity": activity,
    }


# --------------------------------------------------------------------------
# screen 7 — fulfillment & stock
# --------------------------------------------------------------------------


@router.get("/fulfillment/stock")
def stock_by_warehouse(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Live stock per warehouse: on hand, reserved, available."""
    rows = session.execute(
        select(Stock, Warehouse, Product)
        .join(Warehouse, Stock.warehouse_id == Warehouse.id)
        .join(Product, Stock.product_id == Product.id)
        .order_by(Warehouse.code, Product.sku)
    ).all()
    return [
        {
            "warehouse": w.code,
            # the id, not just the code: the manual-override endpoint addresses
            # warehouses by id, and resolving a code client-side is a guess
            "warehouse_id": w.id,
            "warehouse_name": w.name,
            "product_id": p.id,
            "sku": p.sku,
            "product_name": p.name,
            "category": p.category,
            "qty_on_hand": st.qty_on_hand,
            "qty_reserved": st.qty_reserved,
            "qty_available": st.qty_available,
        }
        for st, w, p in rows
    ]


@router.get("/fulfillment/pending")
def orders_pending_fulfillment(
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Orders confirmed but not yet fully shipped."""
    quotes = session.scalars(
        select(Quotation)
        .where(Quotation.state.in_(AWAITING_FULFILLMENT))
        .order_by(Quotation.id.desc())
    ).all()

    out = []
    for q in quotes:
        customer = session.get(Customer, q.customer_id)
        plan = session.scalar(
            select(FulfillmentPlan)
            .where(FulfillmentPlan.quotation_id == q.id)
            .order_by(FulfillmentPlan.id.desc())
        )
        warehouses: list[str] = []
        backordered = False
        if plan is not None:
            for ln in session.scalars(
                select(FulfillmentLine).where(FulfillmentLine.plan_id == plan.id)
            ).all():
                if ln.is_backorder:
                    backordered = True
                elif ln.warehouse_id:
                    wh = session.get(Warehouse, ln.warehouse_id)
                    if wh and wh.code not in warehouses:
                        warehouses.append(wh.code)

        out.append({
            "quotation_id": q.id,
            "customer_name": customer.name if customer else "",
            "state": str(q.state),
            "planned": plan is not None,
            "status": (
                "Backorder" if backordered
                else "Split" if len(warehouses) > 1
                else "Single site" if warehouses
                else "Not planned"
            ),
            "warehouses": warehouses,
            "shipment_count": plan.shipment_count if plan else 0,
            "net_total": str(_net_total(session, q.id)),
        })
    return out


# --------------------------------------------------------------------------
# screen 9 — subscriptions
# --------------------------------------------------------------------------


@router.get("/subscriptions")
def list_subscriptions(
    status: str | None = Query(default=None, pattern="^(active|paused|cancelled)$"),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Every recurring plan across every customer, regardless of which order
    it came from."""
    stmt = select(Subscription).order_by(Subscription.next_bill_date)
    if status:
        stmt = stmt.where(Subscription.status == SubscriptionStatus(status))

    out = []
    for sub in session.scalars(stmt).all():
        quote = session.get(Quotation, sub.quotation_id)
        customer = session.get(Customer, quote.customer_id) if quote else None
        recurring = session.scalars(
            select(QuoteLine).where(
                QuoteLine.quotation_id == sub.quotation_id,
                QuoteLine.is_recurring.is_(True),
            )
        ).all()
        amount = sum(
            (
                ln.unit_price * Decimal(ln.qty)
                * (Decimal(1) - ln.discount_pct / Decimal(100))
                for ln in recurring
            ),
            Decimal(0),
        )
        products = []
        for ln in recurring:
            product = session.get(Product, ln.product_id)
            if product:
                products.append(product.name)

        out.append({
            "id": sub.id,
            "quotation_id": sub.quotation_id,
            "customer_name": customer.name if customer else "",
            "customer_tier": str(customer.tier) if customer else "",
            "plan": ", ".join(products) or "Recurring plan",
            "cycle": "Monthly",
            "start_date": str(sub.start_date),
            "next_bill_date": str(sub.next_bill_date),
            "status": str(sub.status),
            "amount": str(amount.quantize(Decimal("0.01"))),
        })
    return out


# --------------------------------------------------------------------------
# screens 12 & 13 — invoices
# --------------------------------------------------------------------------


def _invoice_row(session: Session, inv: Invoice) -> dict:
    quote = session.get(Quotation, inv.quotation_id)
    customer = session.get(Customer, quote.customer_id) if quote else None
    paid = sum(
        session.scalars(
            select(Payment.amount).where(Payment.invoice_id == inv.id)
        ).all(),
        Decimal(0),
    )
    credited = sum(
        session.scalars(
            select(CreditNote.amount).where(CreditNote.invoice_id == inv.id)
        ).all(),
        Decimal(0),
    )
    return {
        "id": inv.id,
        "reference": f"INV-{inv.id:04d}",
        "quotation_id": inv.quotation_id,
        "customer_name": customer.name if customer else "",
        "kind": str(inv.kind),
        "total": str(inv.total),
        "paid": str(paid),
        "credited": str(credited),
        "outstanding": str(max(Decimal(0), inv.total - credited - paid)),
        "status": str(inv.status),
        "period_key": inv.period_key,
        "subscription_id": inv.subscription_id,
        "issued_at": inv.created_at.date().isoformat() if inv.created_at else None,
    }


@router.get("/invoices")
def list_invoices(
    status: str | None = Query(default=None, pattern="^(paid|unpaid)$"),
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Every invoice generated from one-time and recurring orders."""
    stmt = select(Invoice).order_by(Invoice.id.desc())
    if status == "paid":
        stmt = stmt.where(Invoice.status == InvoiceStatus.PAID)
    elif status == "unpaid":
        stmt = stmt.where(Invoice.status != InvoiceStatus.PAID)
    return [_invoice_row(session, inv) for inv in session.scalars(stmt).all()]


@router.get("/invoices/{invoice_id}")
def invoice_detail(
    invoice_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status_code=404, detail=f"invoice {invoice_id} not found")

    quote = session.get(Quotation, inv.quotation_id)
    row = _invoice_row(session, inv)

    # Order Confirmed -> Shipped -> Invoiced -> Paid
    shipped = session.scalar(
        select(func.count()).select_from(FulfillmentPlan)
        .where(FulfillmentPlan.quotation_id == inv.quotation_id)
    ) or 0
    state = QuoteState(str(quote.state)) if quote else None
    row["tracker"] = [
        {"step": "Order Confirmed", "done": state is not None},
        {"step": "Shipped", "done": shipped > 0},
        {"step": "Invoiced", "done": True},
        {"step": "Paid", "done": inv.status == InvoiceStatus.PAID},
    ]
    row["lines"] = [
        {"description": ln.description, "qty": ln.qty,
         "unit_price": str(ln.unit_price), "amount": str(ln.amount)}
        for ln in session.scalars(
            select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)
        ).all()
    ]
    row["credit_notes"] = [
        {"amount": str(c.amount), "reason": c.reason}
        for c in session.scalars(
            select(CreditNote).where(CreditNote.invoice_id == inv.id)
        ).all()
    ]
    row["payments"] = [
        {"amount": str(p.amount), "method": p.method,
         "paid_at": p.paid_at.date().isoformat()}
        for p in session.scalars(
            select(Payment).where(Payment.invoice_id == inv.id)
        ).all()
    ]
    row["quotation_state"] = str(quote.state) if quote else None
    return row
