"""Fulfillment, billing and payment routes.  Phase 4.

Thin (§12): build a Snapshot, call the domain through a service, return.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    check_quote_ownership,
    current_internal_user,
    endpoint_name,
    get_session,
    idempotency_key,
    record_idempotent,
    replay_or_none,
    require_roles,
)
from app.models.enums import QuoteState, Role
from app.models.tables import (
    CreditNote,
    FulfillmentLine,
    FulfillmentPlan,
    Invoice,
    InvoiceLine,
    Payment,
    PortalMessage,
    Product,
    Quotation,
    QuoteLine,
    Subscription,
    User,
    Warehouse,
)
from app.services import billing as billing_service
from app.services import fulfillment as fulfillment_service
from app.services.advisor import suggest
from app.services.quote_lines import apply_line_update, mutate_lines
from app.services.scoring import rep_discount_robust_z
from app.services.snapshots import build_governance_snapshot
from app.services.state_machine import Event, fire

router = APIRouter(prefix="/api/quotes", tags=["fulfillment"])


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = "bank_transfer"


class OverrideAllocation(BaseModel):
    product_id: int
    warehouse_id: int | None = None   # None = deliberately backordered
    qty: int = Field(gt=0)


class OverrideIn(BaseModel):
    allocations: list[OverrideAllocation] = Field(min_length=1)


class CancelIn(BaseModel):
    reason: str = Field(min_length=3)


class PauseIn(BaseModel):
    paused: bool


class SubscriptionChangeIn(BaseModel):
    change_date: date
    old_amount: Decimal
    new_amount: Decimal


def _load(session: Session, quote_id: int) -> Quotation:
    quote = session.get(Quotation, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"quotation {quote_id} not found")
    return quote


# --------------------------------------------------------------------------
# the tail of the state machine (§7)
# --------------------------------------------------------------------------


@router.post("/{quote_id}/send-to-portal")
def send_to_portal(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    quote = _load(session, quote_id)
    check_quote_ownership(user, quote)
    state = fire(session, quote, Event.SEND_TO_PORTAL, actor_id=user.id)
    return {"quotation_id": quote.id, "state": str(state)}


@router.post("/{quote_id}/customer-confirm")
def customer_confirm(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.MANAGER, Role.FINANCE, Role.ADMIN)),
) -> dict:
    """Phase 5 moves this to the portal; kept here so the chain is completable."""
    quote = _load(session, quote_id)
    state = fire(session, quote, Event.CUSTOMER_CONFIRM, actor_id=user.id)
    return {"quotation_id": quote.id, "state": str(state)}


@router.post("/{quote_id}/plan-fulfillment")
def plan_fulfillment(
    quote_id: int,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.MANAGER, Role.FINANCE, Role.ADMIN)),
    key: str | None = Depends(idempotency_key),
) -> dict:
    endpoint = endpoint_name(request)
    replayed = replay_or_none(session, key, endpoint)
    if replayed is not None:
        response.headers["Idempotent-Replay"] = "true"
        return replayed

    quote = _load(session, quote_id)
    fire(session, quote, Event.PLAN_FULFILLMENT, actor_id=user.id)
    plan, decision, verdict, reasons = fulfillment_service.plan_fulfillment(
        session, quote, actor_id=user.id
    )

    result = {
        "quotation_id": quote.id,
        "state": str(quote.state),
        "plan_id": plan.id,
        "total_cost": str(plan.total_cost),
        "shipment_count": plan.shipment_count,
        "method": decision.output.get("method"),
        "has_backorder": decision.output.get("has_backorder", False),
        "explanation": decision.explanation,
        "verifier_verdict": str(verdict),
        "verifier_reasons": reasons,
    }
    record_idempotent(session, key, endpoint, result)
    session.flush()
    return result


@router.get("/{quote_id}/fulfillment")
def get_fulfillment(
    quote_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    plan = session.scalar(
        select(FulfillmentPlan)
        .where(FulfillmentPlan.quotation_id == quote_id)
        .order_by(FulfillmentPlan.id.desc())
    )
    if plan is None:
        return {"quotation_id": quote_id, "plan": None, "lines": []}

    warehouses = {w.id: w.code for w in session.scalars(select(Warehouse)).all()}
    lines = session.scalars(
        select(FulfillmentLine)
        .where(FulfillmentLine.plan_id == plan.id)
        .order_by(FulfillmentLine.id)
    ).all()

    return {
        "quotation_id": quote_id,
        "plan": {"id": plan.id, "total_cost": str(plan.total_cost),
                 "shipment_count": plan.shipment_count},
        "lines": [
            {
                "product_id": ln.product_id,
                "product_name": (p.name if (p := session.get(Product, ln.product_id)) else ""),
                "warehouse": warehouses.get(ln.warehouse_id) if ln.warehouse_id else None,
                "qty": ln.qty,
                "is_backorder": ln.is_backorder,
            }
            for ln in lines
        ],
    }


@router.post("/{quote_id}/generate-invoices")
def generate_invoices(
    quote_id: int,
    request: Request,
    response: Response,
    as_of: date | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.FINANCE, Role.ADMIN)),
    key: str | None = Depends(idempotency_key),
) -> dict:
    endpoint = endpoint_name(request)
    replayed = replay_or_none(session, key, endpoint)
    if replayed is not None:
        response.headers["Idempotent-Replay"] = "true"
        return replayed

    quote = _load(session, quote_id)
    fire(session, quote, Event.GENERATE_INVOICES, actor_id=user.id)
    result = billing_service.generate_invoices(
        session, quote, as_of or date.today(), actor_id=user.id
    )
    result["state"] = str(quote.state)

    record_idempotent(session, key, endpoint, result)
    session.flush()
    return result


@router.get("/{quote_id}/invoices")
def get_invoices(
    quote_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    invoices = session.scalars(
        select(Invoice).where(Invoice.quotation_id == quote_id).order_by(Invoice.id)
    ).all()
    subscription = session.scalar(
        select(Subscription).where(Subscription.quotation_id == quote_id)
    )
    return {
        "quotation_id": quote_id,
        "invoices": [
            {
                "id": inv.id,
                "kind": str(inv.kind),
                "total": str(inv.total),
                "status": str(inv.status),
                "period_key": inv.period_key,
                "lines": [
                    {"description": ln.description, "qty": ln.qty,
                     "unit_price": str(ln.unit_price), "amount": str(ln.amount)}
                    for ln in session.scalars(
                        select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id)
                    ).all()
                ],
                "credit_notes": [
                    {"amount": str(c.amount), "reason": c.reason}
                    for c in session.scalars(
                        select(CreditNote).where(CreditNote.invoice_id == inv.id)
                    ).all()
                ],
                "payments": [
                    {"amount": str(p.amount), "method": p.method}
                    for p in session.scalars(
                        select(Payment).where(Payment.invoice_id == inv.id)
                    ).all()
                ],
            }
            for inv in invoices
        ],
        "subscription": (
            {"id": subscription.id, "start_date": str(subscription.start_date),
             "next_bill_date": str(subscription.next_bill_date),
             "status": str(subscription.status)}
            if subscription else None
        ),
    }


@router.post("/{quote_id}/payments")
def record_payment(
    quote_id: int,
    body: PaymentIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.FINANCE, Role.ADMIN)),
) -> dict:
    quote = _load(session, quote_id)
    result = billing_service.record_payment(session, quote, body.amount, body.method)
    if result["fully_paid"]:
        fire(session, quote, Event.RECORD_PAYMENT, actor_id=user.id)
    result["state"] = str(quote.state)
    session.flush()
    return result


@router.post("/{quote_id}/fulfillment/override")
def override_fulfillment(
    quote_id: int,
    body: OverrideIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.MANAGER, Role.ADMIN)),
) -> dict:
    """Screen 8's "manual override" — replace the optimizer's split.

    The operator may choose a costlier plan; they may not choose an impossible
    one, so coverage and stock are re-checked exactly as for the optimizer.
    """
    quote = _load(session, quote_id)
    plan, notes = fulfillment_service.override_plan(
        session,
        quote,
        [a.model_dump() for a in body.allocations],
        actor_id=user.id,
    )
    session.flush()
    return {
        "quotation_id": quote.id,
        "plan_id": plan.id,
        "total_cost": str(plan.total_cost),
        "shipment_count": plan.shipment_count,
        "notes": notes,
    }


@router.post("/{quote_id}/fulfillment/consolidate/{product_id}")
def consolidate_backorders(
    quote_id: int,
    product_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    """§5.2: on stock receipt, re-check open backorders and propose a
    consolidation. Raises a proposal; it does not move stock by itself."""
    _load(session, quote_id)
    return fulfillment_service.consolidate_backorders(session, product_id)


@router.post("/{quote_id}/subscription/cancel")
def cancel_subscription(
    quote_id: int,
    body: CancelIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.FINANCE, Role.ADMIN)),
) -> dict:
    subscription = session.scalar(
        select(Subscription).where(Subscription.quotation_id == quote_id)
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="no subscription on this quotation")
    return billing_service.cancel_subscription(
        session, subscription, date.today(), body.reason
    )


@router.post("/{quote_id}/subscription/pause")
def pause_subscription(
    quote_id: int,
    body: PauseIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.FINANCE, Role.ADMIN)),
) -> dict:
    subscription = session.scalar(
        select(Subscription).where(Subscription.quotation_id == quote_id)
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="no subscription on this quotation")
    return billing_service.pause_subscription(session, subscription, body.paused)


@router.get("/{quote_id}/billing-detail")
def billing_detail(
    quote_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    """Screen 10: one-time lines from the original quotation, recurring lines
    on their own schedule, side by side."""
    quote = _load(session, quote_id)
    lines = session.scalars(
        select(QuoteLine).where(QuoteLine.quotation_id == quote.id).order_by(QuoteLine.id)
    ).all()

    def shape(ln: QuoteLine) -> dict:
        product = session.get(Product, ln.product_id)
        net = ln.unit_price * Decimal(ln.qty) * (1 - ln.discount_pct / 100)
        return {
            "product_id": ln.product_id,
            "product_name": product.name if product else "",
            "qty": ln.qty,
            "amount": str(net.quantize(Decimal("0.01"))),
        }

    subscription = session.scalar(
        select(Subscription).where(Subscription.quotation_id == quote.id)
    )
    return {
        "quotation_id": quote.id,
        "state": str(quote.state),
        "one_time_lines": [shape(ln) for ln in lines if not ln.is_recurring],
        "recurring_lines": [shape(ln) for ln in lines if ln.is_recurring],
        "subscription": (
            {
                "id": subscription.id,
                "start_date": str(subscription.start_date),
                "next_bill_date": str(subscription.next_bill_date),
                "status": str(subscription.status),
            }
            if subscription else None
        ),
    }


@router.get("/{quote_id}/amount-due")
def get_amount_due(
    quote_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> dict:
    return billing_service.amount_due(session, _load(session, quote_id))


@router.post("/{quote_id}/subscription-change")
def subscription_change(
    quote_id: int,
    body: SubscriptionChangeIn,
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles(Role.FINANCE, Role.ADMIN)),
) -> dict:
    subscription = session.scalar(
        select(Subscription).where(Subscription.quotation_id == quote_id)
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="no subscription on this quotation")
    return billing_service.change_subscription_amount(
        session, subscription, body.change_date, body.old_amount, body.new_amount
    )


# --------------------------------------------------------------------------
# negotiation loop (Phase 5)
# --------------------------------------------------------------------------


@router.post("/{quote_id}/accept-counter")
def accept_counter(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    """Rep accepts the customer's counter-discount.

    1. Find the latest portal_message with a counter_discount_pct.
    2. Apply it to the targeted line through ``mutate_lines`` — this voids
       existing approvals, re-scores, and re-enters the chain (§7).
    3. Fire REP_ACCEPTS_COUNTER: UNDER_NEGOTIATION → RISK_SCORED (state machine
       handles the immediate transition to PENDING_* or READY_TO_FULFILL).
    """
    quote = _load(session, quote_id)

    if QuoteState(str(quote.state)) != QuoteState.UNDER_NEGOTIATION:
        raise HTTPException(
            status_code=400,
            detail=f"quote must be UNDER_NEGOTIATION to accept counter, "
                   f"current state is {quote.state}",
        )

    # Find the latest counter-discount message
    counter_msg = session.scalar(
        select(PortalMessage)
        .where(
            PortalMessage.quotation_id == quote.id,
            PortalMessage.counter_discount_pct.is_not(None),
        )
        .order_by(PortalMessage.id.desc())
    )
    if counter_msg is None:
        raise HTTPException(
            status_code=400,
            detail="no counter-discount proposal found on this quotation",
        )

    line = session.get(QuoteLine, counter_msg.quote_line_id)
    if line is None or line.quotation_id != quote.id:
        raise HTTPException(
            status_code=400,
            detail=f"counter targets line {counter_msg.quote_line_id} "
                   f"which is not on this quotation",
        )

    new_discount = counter_msg.counter_discount_pct

    def _snapshot_builder(q: Quotation):
        return build_governance_snapshot(
            session, q, rep_discount_robust_z(session, q)
        )

    score, chain = mutate_lines(
        session,
        quote,
        expected_version=quote.version,
        mutate=lambda _q: apply_line_update(line, discount_pct=new_discount),
        build_snapshot=_snapshot_builder,
        actor_id=user.id,
    )

    session.flush()

    return {
        "quotation_id": quote.id,
        "state": str(quote.state),
        "version": quote.version,
        "score": float(score),
        "approval_chain": chain,
        "applied_discount_pct": str(new_discount),
        "line_id": line.id,
    }


# --------------------------------------------------------------------------
# advisor (T1 — proposals only)
# --------------------------------------------------------------------------


@router.get("/{quote_id}/suggestions")
def suggestions(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    return suggest(session, _load(session, quote_id), actor_id=user.id)
