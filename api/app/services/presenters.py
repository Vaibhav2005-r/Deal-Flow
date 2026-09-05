"""ORM -> API response assembly.

Kept out of the routers so they stay thin (§12).  The per-line breach detail
here is what the approval screen renders: a manager must see *which* line
breached and by how much, not just a number.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ApprovalStepOut, LineOut, QuoteOut
from app.domain.pricing import line_net_value
from app.models.enums import QuoteState
from app.models.tables import (
    ApprovalRequest,
    Customer,
    Product,
    Quotation,
    QuoteLine,
    User,
)
from app.services.state_machine import legal_events


def line_out(line: QuoteLine, product: Product) -> LineOut:
    list_value = line.unit_price * Decimal(line.qty)
    net_value = line_net_value(line.unit_price, line.discount_pct, line.qty)
    ceiling = line.ceiling_pct_applied
    excess = (
        max(Decimal(0), line.discount_pct - ceiling)
        if ceiling is not None
        else Decimal(0)
    )
    return LineOut(
        id=line.id,
        product_id=product.id,
        product_name=product.name,
        category=product.category,
        qty=line.qty,
        unit_price=line.unit_price,
        discount_pct=line.discount_pct,
        ceiling_pct_applied=ceiling,
        margin_pct=line.margin_pct,
        is_recurring=line.is_recurring,
        list_value=list_value,
        net_value=net_value,
        excess_pp=excess,
        breaches_ceiling=excess > 0,
    )


def quote_out(session: Session, quotation: Quotation) -> QuoteOut:
    customer = session.get(Customer, quotation.customer_id)
    lines = session.scalars(
        select(QuoteLine)
        .where(QuoteLine.quotation_id == quotation.id)
        .order_by(QuoteLine.id)
    ).all()

    outs, list_total, net_total = [], Decimal(0), Decimal(0)
    for line in lines:
        product = session.get(Product, line.product_id)
        rendered = line_out(line, product)
        outs.append(rendered)
        list_total += rendered.list_value
        net_total += rendered.net_value

    steps = session.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.quotation_id == quotation.id)
        .order_by(ApprovalRequest.step_index, ApprovalRequest.id)
    ).all()

    step_outs = []
    for step in steps:
        out = ApprovalStepOut.model_validate(step)
        if step.decided_by is not None:
            approver = session.get(User, step.decided_by)
            out = out.model_copy(
                update={"decided_by_name": approver.full_name if approver else None}
            )
        step_outs.append(out)

    pending = next(
        (s for s in steps if str(s.decision) == "PENDING"), None
    )
    score = float(quotation.risk_score) if quotation.risk_score is not None else None
    band = (
        None if score is None
        else "HIGH" if score >= 50
        else "MEDIUM" if score >= 20
        else "LOW"
    )

    return QuoteOut(
        id=quotation.id,
        customer_id=quotation.customer_id,
        customer_name=customer.name if customer else "",
        customer_tier=str(customer.tier) if customer else "",
        rep_id=quotation.rep_id,
        state=str(quotation.state),
        version=quotation.version,
        risk_score=quotation.risk_score,
        lines=outs,
        approval_steps=step_outs,
        current_stage=pending.approver_role if pending else None,
        risk_band=band,
        legal_events=[str(e) for e in legal_events(QuoteState(str(quotation.state)))],
        totals={
            "list_total": str(list_total),
            "net_total": str(net_total),
            "discount_total": str(list_total - net_total),
            "line_count": len(outs),
        },
    )
