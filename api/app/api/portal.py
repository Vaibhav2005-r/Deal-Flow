"""Customer portal routes.  Phase 5.

A GENUINELY SEPARATE router (§1 constraint 2): every endpoint uses
``current_portal_user`` and an ownership guard.  An internal token can never
satisfy a portal route and vice versa.  This module NEVER imports from
``app.api.quotes``, ``app.api.fulfillment``, or ``app.api.approvals``.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_portal_user, get_session
from app.models.enums import QuoteState
from app.models.tables import (
    Customer,
    PortalMessage,
    Product,
    Quotation,
    QuoteLine,
    User,
)
from app.services.state_machine import Event, fire

router = APIRouter(prefix="/api/portal", tags=["portal"])

#: States a portal user is allowed to see and act on.
PORTAL_VISIBLE = {QuoteState.SENT, QuoteState.UNDER_NEGOTIATION}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _customer_for_user(session: Session, user: User) -> Customer:
    """Look up the customer linked to this portal user."""
    customer = session.scalar(
        select(Customer).where(Customer.user_id == user.id)
    )
    if customer is None:
        raise HTTPException(
            status_code=403,
            detail="no customer account linked to this portal user",
        )
    return customer


def _load_owned(session: Session, quote_id: int, customer: Customer) -> Quotation:
    """Load a quotation and assert the portal user owns it."""
    quote = session.get(Quotation, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail=f"quotation {quote_id} not found")
    if quote.customer_id != customer.id:
        raise HTTPException(status_code=403, detail="not your quotation")
    return quote


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------


class PortalLineOut(BaseModel):
    id: int
    product_name: str
    category: str
    qty: int
    unit_price: str
    discount_pct: str
    net_value: str


class PortalQuoteSummary(BaseModel):
    id: int
    state: str
    line_count: int
    net_total: str


class PortalMessageOut(BaseModel):
    id: int
    author_name: str
    body: str
    quote_line_id: int | None
    counter_discount_pct: str | None
    created_at: str


@router.get("/quotes")
def list_portal_quotes(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(current_portal_user),
) -> list[PortalQuoteSummary]:
    customer = _customer_for_user(session, user)
    base_stmt = (
        select(Quotation)
        .where(
            Quotation.customer_id == customer.id,
            Quotation.state.in_(PORTAL_VISIBLE),
        )
    )

    total_count = session.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    ) or 0

    offset = (page - 1) * page_size
    stmt = base_stmt.order_by(Quotation.id.desc()).offset(offset).limit(page_size)
    quotes = session.scalars(stmt).all()

    total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Pages"] = str(total_pages)

    results: list[PortalQuoteSummary] = []
    for q in quotes:
        lines = session.scalars(
            select(QuoteLine).where(QuoteLine.quotation_id == q.id)
        ).all()
        net_total = sum(
            (ln.unit_price * Decimal(ln.qty) * (1 - ln.discount_pct / 100))
            for ln in lines
        )
        results.append(PortalQuoteSummary(
            id=q.id,
            state=str(q.state),
            line_count=len(lines),
            net_total=str(net_total),
        ))
    return results


@router.get("/quotes/{quote_id}")
def get_portal_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_portal_user),
) -> dict:
    customer = _customer_for_user(session, user)
    quote = _load_owned(session, quote_id, customer)

    lines = session.scalars(
        select(QuoteLine)
        .where(QuoteLine.quotation_id == quote.id)
        .order_by(QuoteLine.id)
    ).all()

    line_outs: list[dict] = []
    net_total = Decimal(0)
    for ln in lines:
        product = session.get(Product, ln.product_id)
        net = ln.unit_price * Decimal(ln.qty) * (1 - ln.discount_pct / 100)
        net_total += net
        line_outs.append({
            "id": ln.id,
            "product_name": product.name if product else "",
            "category": product.category if product else "",
            "qty": ln.qty,
            "unit_price": str(ln.unit_price),
            "discount_pct": str(ln.discount_pct),
            "net_value": str(net),
        })

    return {
        "id": quote.id,
        "customer_name": customer.name,
        "state": str(quote.state),
        "version": quote.version,
        "lines": line_outs,
        "net_total": str(net_total),
    }


@router.get("/quotes/{quote_id}/messages")
def get_messages(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_portal_user),
) -> list[PortalMessageOut]:
    customer = _customer_for_user(session, user)
    _load_owned(session, quote_id, customer)

    messages = session.scalars(
        select(PortalMessage)
        .where(PortalMessage.quotation_id == quote_id)
        .order_by(PortalMessage.id)
    ).all()

    return [
        PortalMessageOut(
            id=m.id,
            author_name=(
                session.get(User, m.author_id).full_name
                if session.get(User, m.author_id) else "unknown"
            ),
            body=m.body,
            quote_line_id=m.quote_line_id,
            counter_discount_pct=(
                str(m.counter_discount_pct) if m.counter_discount_pct is not None else None
            ),
            created_at=str(m.created_at),
        )
        for m in messages
    ]


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------


class PostMessageIn(BaseModel):
    body: str = Field(min_length=1)
    quote_line_id: int | None = None
    counter_discount_pct: Decimal | None = Field(default=None, ge=0, le=100)


@router.post("/quotes/{quote_id}/messages")
def post_message(
    quote_id: int,
    body: PostMessageIn,
    session: Session = Depends(get_session),
    user: User = Depends(current_portal_user),
) -> PortalMessageOut:
    customer = _customer_for_user(session, user)
    quote = _load_owned(session, quote_id, customer)

    # Validate that the quote is in a portal-actionable state
    if QuoteState(str(quote.state)) not in PORTAL_VISIBLE:
        raise HTTPException(
            status_code=400,
            detail=f"cannot post messages on a quote in state {quote.state}",
        )

    # If targeting a specific line, validate it exists on this quote
    if body.quote_line_id is not None:
        line = session.get(QuoteLine, body.quote_line_id)
        if line is None or line.quotation_id != quote.id:
            raise HTTPException(
                status_code=404,
                detail=f"line {body.quote_line_id} not on this quotation",
            )

    msg = PortalMessage(
        quotation_id=quote.id,
        quote_line_id=body.quote_line_id,
        author_id=user.id,
        body=body.body,
        counter_discount_pct=body.counter_discount_pct,
    )
    session.add(msg)
    session.flush()

    return PortalMessageOut(
        id=msg.id,
        author_name=user.full_name,
        body=msg.body,
        quote_line_id=msg.quote_line_id,
        counter_discount_pct=(
            str(msg.counter_discount_pct) if msg.counter_discount_pct is not None else None
        ),
        created_at=str(msg.created_at),
    )


@router.post("/quotes/{quote_id}/counter")
def submit_counter(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_portal_user),
) -> dict:
    """Customer submits a counter-proposal: SENT → UNDER_NEGOTIATION."""
    customer = _customer_for_user(session, user)
    quote = _load_owned(session, quote_id, customer)

    # Must have at least one counter-discount message to submit
    has_counter = session.scalar(
        select(PortalMessage.id)
        .where(
            PortalMessage.quotation_id == quote.id,
            PortalMessage.counter_discount_pct.is_not(None),
        )
        .limit(1)
    )
    if not has_counter:
        raise HTTPException(
            status_code=400,
            detail="submit at least one counter-discount before submitting",
        )

    if QuoteState(str(quote.state)) == QuoteState.UNDER_NEGOTIATION:
        return {"quotation_id": quote.id, "state": str(quote.state)}

    state = fire(session, quote, Event.CUSTOMER_COUNTER, actor_id=user.id)
    return {"quotation_id": quote.id, "state": str(state)}


@router.post("/quotes/{quote_id}/confirm")
def portal_confirm(
    quote_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(current_portal_user),
) -> dict:
    """Customer accepts the quote: SENT|UNDER_NEGOTIATION → CONFIRMED."""
    customer = _customer_for_user(session, user)
    quote = _load_owned(session, quote_id, customer)
    state = fire(session, quote, Event.CUSTOMER_CONFIRM, actor_id=user.id)
    return {"quotation_id": quote.id, "state": str(state)}
