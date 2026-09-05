"""Approval routes.  The manager/finance side of the chain (§7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    current_internal_user,
    endpoint_name,
    get_session,
    idempotency_key,
    record_idempotent,
    replay_or_none,
    require_roles,
)
from app.api.schemas import DecisionRequest, QuoteOut
from app.models.enums import ApprovalDecision, QuoteState, Role
from app.models.tables import ApprovalRequest, Quotation, User
from app.services.presenters import quote_out
from app.services.state_machine import Event, fire

router = APIRouter(prefix="/api", tags=["approvals"])

#: Which approver_role each internal role may act on.
ROLE_TO_STEP = {Role.MANAGER: "SALES_MANAGER", Role.FINANCE: "FINANCE"}


@router.get("/approvals", response_model=list[QuoteOut])
def approval_queue(
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> list[QuoteOut]:
    """Quotations waiting on THIS approver's step."""
    step_role = ROLE_TO_STEP.get(user.role)
    stmt = (
        select(Quotation)
        .join(ApprovalRequest, ApprovalRequest.quotation_id == Quotation.id)
        .where(ApprovalRequest.decision == ApprovalDecision.PENDING)
        .where(
            Quotation.state.in_([QuoteState.PENDING_MANAGER, QuoteState.PENDING_FINANCE])
        )
        .order_by(Quotation.id.desc())
        .distinct()
    )
    if step_role:
        stmt = stmt.where(ApprovalRequest.approver_role == step_role)
    elif user.role != Role.ADMIN:
        return []
    return [quote_out(session, q) for q in session.scalars(stmt).all()]


def _decide(
    session: Session,
    quote_id: int,
    event: Event,
    user: User,
    reason: str | None,
    request: Request,
    response: Response,
    key: str | None,
) -> QuoteOut:
    endpoint = endpoint_name(request)
    replayed = replay_or_none(session, key, endpoint)
    if replayed is not None:
        response.headers["Idempotent-Replay"] = "true"
        return QuoteOut.model_validate(replayed)

    quote = session.get(Quotation, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"quotation {quote_id} not found")

    _guard_step_belongs_to_role(session, quote, user)
    fire(session, quote, event, actor_id=user.id, reason=reason)
    session.flush()

    result = quote_out(session, quote)
    record_idempotent(session, key, endpoint, result.model_dump(mode="json"))
    session.flush()
    return result


def _guard_step_belongs_to_role(
    session: Session, quote: Quotation, user: User
) -> None:
    """A finance approver may not sign off a manager step, or vice versa."""
    if user.role == Role.ADMIN:
        return
    step = session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.quotation_id == quote.id,
            ApprovalRequest.decision == ApprovalDecision.PENDING,
        )
        .order_by(ApprovalRequest.step_index)
    )
    if step is None:
        raise HTTPException(
            status_code=409,
            detail=f"quotation {quote.id} has no pending approval step",
        )
    expected = ROLE_TO_STEP.get(user.role)
    if step.approver_role != expected:
        raise HTTPException(
            status_code=403,
            detail=f"current step needs {step.approver_role}, you are {expected}",
        )


@router.post("/quotes/{quote_id}/approve", response_model=QuoteOut)
def approve(
    quote_id: int,
    request: Request,
    response: Response,
    body: DecisionRequest | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.MANAGER, Role.FINANCE, Role.ADMIN)),
    key: str | None = Depends(idempotency_key),
) -> QuoteOut:
    return _decide(session, quote_id, Event.APPROVE, user,
                   body.reason if body else None, request, response, key)


@router.post("/quotes/{quote_id}/reject", response_model=QuoteOut)
def reject(
    quote_id: int,
    body: DecisionRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.MANAGER, Role.FINANCE, Role.ADMIN)),
    key: str | None = Depends(idempotency_key),
) -> QuoteOut:
    return _decide(session, quote_id, Event.REJECT, user, body.reason,
                   request, response, key)


@router.post("/quotes/{quote_id}/return", response_model=QuoteOut)
def return_for_revision(
    quote_id: int,
    body: DecisionRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles(Role.MANAGER, Role.FINANCE, Role.ADMIN)),
    key: str | None = Depends(idempotency_key),
) -> QuoteOut:
    return _decide(session, quote_id, Event.RETURN_FOR_REVISION, user, body.reason,
                   request, response, key)
