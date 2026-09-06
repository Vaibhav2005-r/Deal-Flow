"""The quotation state machine.  Spec §7.

The transition table is DATA, not branching scattered through routers.  A
router asks `fire(quotation, Event.APPROVE, ...)`; it does not know the graph.
That keeps §12's "routers are thin" honest and makes the whole table
assertable in one test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.exceptions import DomainError
from app.models.enums import ApprovalDecision, QuoteState
from app.models.tables import ApprovalRequest, Outbox, Quotation


class Event(StrEnum):
    CONFIRM = "confirm"
    APPROVE = "approve"
    REJECT = "reject"
    RETURN_FOR_REVISION = "return_for_revision"
    SEND_TO_PORTAL = "send_to_portal"
    CUSTOMER_COUNTER = "customer_counter"
    REP_ACCEPTS_COUNTER = "rep_accepts_counter"
    CUSTOMER_CONFIRM = "customer_confirm"
    PLAN_FULFILLMENT = "plan_fulfillment"
    GENERATE_INVOICES = "generate_invoices"
    RECORD_PAYMENT = "record_payment"


class IllegalTransition(DomainError):
    """The event is not legal from the quotation's current state (§7)."""


class GuardFailed(DomainError):
    """The transition is legal but its guard rejected it (§7)."""


#: (from_state, event) -> to_state.  `None` means the target is computed —
#: APPROVE depends on whether another approval step remains in the chain.
TRANSITIONS: dict[tuple[QuoteState, Event], QuoteState | None] = {
    (QuoteState.DRAFT, Event.CONFIRM): QuoteState.RISK_SCORED,

    (QuoteState.PENDING_MANAGER, Event.APPROVE): None,
    (QuoteState.PENDING_FINANCE, Event.APPROVE): None,

    (QuoteState.PENDING_MANAGER, Event.REJECT): QuoteState.DRAFT,
    (QuoteState.PENDING_FINANCE, Event.REJECT): QuoteState.DRAFT,
    (QuoteState.PENDING_MANAGER, Event.RETURN_FOR_REVISION): QuoteState.DRAFT,
    (QuoteState.PENDING_FINANCE, Event.RETURN_FOR_REVISION): QuoteState.DRAFT,

    (QuoteState.READY_TO_FULFILL, Event.SEND_TO_PORTAL): QuoteState.SENT,
    (QuoteState.UNDER_NEGOTIATION, Event.SEND_TO_PORTAL): QuoteState.SENT,
    (QuoteState.SENT, Event.CUSTOMER_COUNTER): QuoteState.UNDER_NEGOTIATION,
    (QuoteState.UNDER_NEGOTIATION, Event.REP_ACCEPTS_COUNTER): QuoteState.RISK_SCORED,

    (QuoteState.SENT, Event.CUSTOMER_CONFIRM): QuoteState.CONFIRMED,
    (QuoteState.UNDER_NEGOTIATION, Event.CUSTOMER_CONFIRM): QuoteState.CONFIRMED,

    (QuoteState.CONFIRMED, Event.PLAN_FULFILLMENT): QuoteState.FULFILLING,
    (QuoteState.FULFILLING, Event.GENERATE_INVOICES): QuoteState.INVOICED,
    (QuoteState.INVOICED, Event.RECORD_PAYMENT): QuoteState.PAID,
}

#: Events that cannot proceed without an explicit reason (§7).
REQUIRES_REASON = {Event.REJECT, Event.RETURN_FOR_REVISION}


def legal_events(state: QuoteState) -> list[Event]:
    return sorted({e for (s, e) in TRANSITIONS if s == state})


def pending_steps(session: Session, quotation_id: int) -> list[ApprovalRequest]:
    """Outstanding approval steps, in chain order."""
    return list(
        session.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.quotation_id == quotation_id,
                ApprovalRequest.decision == ApprovalDecision.PENDING,
            )
            .order_by(ApprovalRequest.step_index)
        ).all()
    )


def _emit(session: Session, topic: str, payload: dict) -> None:
    """Outbox row in the SAME transaction as the state change (§8)."""
    session.add(Outbox(topic=topic, payload=payload))


def fire(
    session: Session,
    quotation: Quotation,
    event: Event,
    *,
    actor_id: int | None = None,
    reason: str | None = None,
) -> QuoteState:
    """Apply an event. Raises IllegalTransition / GuardFailed. Returns new state."""
    state = QuoteState(str(quotation.state))
    key = (state, event)
    if key not in TRANSITIONS:
        raise IllegalTransition(
            f"{event} is not legal from {state}; "
            f"legal here: {[str(e) for e in legal_events(state)]}"
        )

    if event in REQUIRES_REASON and not (reason or "").strip():
        raise GuardFailed(f"{event} requires a reason (§7)")

    if event is Event.CONFIRM and not quotation.lines:
        raise GuardFailed("cannot confirm a quotation with no lines (§7)")

    target = TRANSITIONS[key]

    if event is Event.APPROVE:
        target = _approve(session, quotation, actor_id)
    elif event in (Event.REJECT, Event.RETURN_FOR_REVISION):
        _close_open_steps(
            session,
            quotation,
            ApprovalDecision.REJECTED
            if event is Event.REJECT
            else ApprovalDecision.RETURNED,
            actor_id,
            reason,
        )

    assert target is not None
    quotation.state = target
    quotation.last_activity_at = datetime.now(timezone.utc)
    _emit(session, f"quotation.{event}", {
        "quotation_id": quotation.id, "from": str(state), "to": str(target),
        "actor_id": actor_id,
    })
    return target


def _approve(
    session: Session, quotation: Quotation, actor_id: int | None
) -> QuoteState:
    """Approve the current step; advance to the next, or release the quote."""
    steps = pending_steps(session, quotation.id)
    if not steps:
        raise GuardFailed(
            f"quotation {quotation.id} is in {quotation.state} with no pending "
            f"approval step — nothing to approve"
        )

    current = steps[0]
    current.decision = ApprovalDecision.APPROVED
    current.decided_by = actor_id
    current.decided_at = datetime.now(timezone.utc)

    remaining = steps[1:]
    if not remaining:
        return QuoteState.READY_TO_FULFILL
    nxt = remaining[0].approver_role
    return (
        QuoteState.PENDING_FINANCE
        if nxt == "FINANCE"
        else QuoteState.PENDING_MANAGER
    )


def _close_open_steps(
    session: Session,
    quotation: Quotation,
    decision: ApprovalDecision,
    actor_id: int | None,
    reason: str | None,
) -> None:
    now = datetime.now(timezone.utc)
    steps = pending_steps(session, quotation.id)
    if not steps:
        return
    active = steps[0]
    active.decision = decision
    active.decided_by = actor_id
    active.decided_at = now
    active.reason = reason

    for downstream in steps[1:]:
        downstream.decision = ApprovalDecision.VOIDED_BY_EDIT
        downstream.decided_by = actor_id
        downstream.decided_at = now
        downstream.reason = "Voided due to upstream rejection/return"
