"""Quotation routes.  Thin by contract (§12): build a Snapshot, call the
domain, persist the Decision, write decision_log, return."""

from __future__ import annotations

from decimal import Decimal

import math
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    check_quote_ownership,
    current_internal_user,
    endpoint_name,
    get_session,
    idempotency_key,
    record_idempotent,
    replay_or_none,
)
from app.api.schemas import LineIn, LineUpdate, QuoteCreate, QuoteOut, ScoreOut
from app.models.enums import QuoteState, Role
from app.models.tables import Product, Quotation, QuoteLine, User
from app.services.presenters import quote_out
from app.services.quote_lines import (
    ConcurrencyError,
    append_line,
    apply_line_update,
    mutate_lines,
    remove_line,
)
from app.services.scoring import rep_discount_robust_z, score_quotation
from app.services.snapshots import build_governance_snapshot
from app.services.state_machine import Event, fire

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


def _load(session: Session, quote_id: int) -> Quotation:
    quote = session.get(Quotation, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"quotation {quote_id} not found")
    return quote


def _check_version(quote: Quotation, expected: int | None) -> int:
    """Optimistic concurrency (§8): mismatch -> 409."""
    if expected is None:
        return quote.version
    if expected != quote.version:
        raise ConcurrencyError(
            f"quotation {quote.id} is at version {quote.version}, "
            f"caller held {expected}"
        )
    return expected


@router.get("", response_model=list[QuoteOut])
def list_quotes(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    state: str | None = None,
    all_quotes: bool = False,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> list[QuoteOut]:
    base_query = select(Quotation)
    if state:
        base_query = base_query.where(Quotation.state == state)
    if user.role == Role.REP and not all_quotes:
        has_quotes = session.scalar(
            select(func.count()).select_from(Quotation).where(Quotation.rep_id == user.id)
        )
        if has_quotes and has_quotes > 0:
            base_query = base_query.where(Quotation.rep_id == user.id)

    # Compute total count in database
    total_count = session.scalar(
        select(func.count()).select_from(base_query.subquery())
    ) or 0

    # Paginate in database
    offset = (page - 1) * page_size
    stmt = base_query.order_by(Quotation.id.desc()).offset(offset).limit(page_size)
    items = [quote_out(session, q) for q in session.scalars(stmt).all()]

    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Pages"] = str(total_pages)
    return items


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> QuoteOut:
    return quote_out(session, _load(session, quote_id))


@router.post("", response_model=QuoteOut, status_code=201)
def create_quote(
    body: QuoteCreate,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> QuoteOut:
    quote = Quotation(
        customer_id=body.customer_id, rep_id=user.id, state=QuoteState.DRAFT
    )
    session.add(quote)
    session.flush()

    for line in body.lines:
        append_line(session, quote, _product(session, line.product_id),
                    line.qty, line.discount_pct, line.unit_price)
    session.flush()
    return quote_out(session, quote)


def _product(session: Session, product_id: int) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"product {product_id} not found")
    return product


def _snapshot_for(session: Session):
    """Snapshot builder passed to mutate_lines on every mutating route."""
    return lambda q: build_governance_snapshot(
        session, q, rep_discount_robust_z(session, q)
    )


@router.post("/{quote_id}/lines", response_model=QuoteOut)
def add_line(
    quote_id: int,
    body: LineIn,
    expected_version: int | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> QuoteOut:
    quote = _load(session, quote_id)
    check_quote_ownership(user, quote)
    version = _check_version(quote, expected_version)
    mutate_lines(
        session,
        quote,
        expected_version=version,
        mutate=lambda q: append_line(
            session, q, _product(session, body.product_id),
            body.qty, body.discount_pct, body.unit_price,
        ),
        build_snapshot=_snapshot_for(session),
        actor_id=user.id,
    )
    session.flush()
    return quote_out(session, quote)


@router.patch("/{quote_id}/lines/{line_id}", response_model=QuoteOut)
def update_line(
    quote_id: int,
    line_id: int,
    body: LineUpdate,
    expected_version: int | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> QuoteOut:
    quote = _load(session, quote_id)
    check_quote_ownership(user, quote)
    version = _check_version(quote, expected_version)

    line = session.get(QuoteLine, line_id)
    if line is None or line.quotation_id != quote.id:
        raise HTTPException(status_code=404, detail=f"line {line_id} not on this quote")

    mutate_lines(
        session, quote, expected_version=version,
        mutate=lambda _q: apply_line_update(line, body.qty, body.discount_pct),
        build_snapshot=_snapshot_for(session),
        actor_id=user.id,
    )
    session.flush()
    return quote_out(session, quote)


@router.delete("/{quote_id}/lines/{line_id}", response_model=QuoteOut)
def delete_line(
    quote_id: int,
    line_id: int,
    expected_version: int | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> QuoteOut:
    quote = _load(session, quote_id)
    check_quote_ownership(user, quote)
    version = _check_version(quote, expected_version)
    line = session.get(QuoteLine, line_id)
    if line is None or line.quotation_id != quote.id:
        raise HTTPException(status_code=404, detail=f"line {line_id} not on this quote")

    mutate_lines(
        session, quote, expected_version=version,
        mutate=lambda _q: remove_line(session, line),
        build_snapshot=_snapshot_for(session),
        actor_id=user.id,
    )
    session.flush()
    return quote_out(session, quote)


@router.post("/{quote_id}/confirm", response_model=ScoreOut)
def confirm(
    quote_id: int,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
    key: str | None = Depends(idempotency_key),
) -> ScoreOut:
    """DRAFT -> RISK_SCORED -> (READY_TO_FULFILL | PENDING_MANAGER).  §7."""
    endpoint = endpoint_name(request)
    replayed = replay_or_none(session, key, endpoint)
    if replayed is not None:
        response.headers["Idempotent-Replay"] = "true"
        return ScoreOut.model_validate(replayed)

    quote = _load(session, quote_id)
    check_quote_ownership(user, quote)
    fire(session, quote, Event.CONFIRM, actor_id=user.id)
    result = score_quotation(session, quote, actor_id=user.id)

    record_idempotent(session, key, endpoint, result.model_dump(mode="json"))
    session.flush()
    return result


@router.get("/{quote_id}/messages")
def get_quote_messages(
    quote_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(current_internal_user),
) -> list[dict]:
    """Retrieve portal negotiation thread messages for internal reps."""
    quote = _load(session, quote_id)
    from app.models.tables import PortalMessage
    messages = session.scalars(
        select(PortalMessage)
        .where(PortalMessage.quotation_id == quote.id)
        .order_by(PortalMessage.id)
    ).all()
    return [
        {
            "id": m.id,
            "author_name": (
                session.get(User, m.author_id).full_name
                if session.get(User, m.author_id) else "unknown"
            ),
            "body": m.body,
            "quote_line_id": m.quote_line_id,
            "counter_discount_pct": (
                str(m.counter_discount_pct) if m.counter_discount_pct is not None else None
            ),
            "created_at": str(m.created_at),
        }
        for m in messages
    ]


class MessageIn(BaseModel):
    body: str
    quote_line_id: int | None = None
    counter_discount_pct: Decimal | None = None


@router.post("/{quote_id}/messages")
def post_quote_message(
    quote_id: int,
    body: MessageIn,
    session: Session = Depends(get_session),
    user: User = Depends(current_internal_user),
) -> dict:
    """Internal rep posts a message to the quotation portal negotiation thread."""
    quote = _load(session, quote_id)
    check_quote_ownership(user, quote)
    from app.models.tables import PortalMessage
    msg = PortalMessage(
        quotation_id=quote.id,
        quote_line_id=body.quote_line_id,
        author_id=user.id,
        body=body.body,
        counter_discount_pct=body.counter_discount_pct,
    )
    session.add(msg)
    session.flush()
    return {
        "id": msg.id,
        "author_name": user.full_name,
        "body": msg.body,
        "quote_line_id": msg.quote_line_id,
        "counter_discount_pct": (
            str(msg.counter_discount_pct) if msg.counter_discount_pct is not None else None
        ),
        "created_at": str(msg.created_at),
    }


