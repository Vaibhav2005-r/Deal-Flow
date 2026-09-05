"""Upsell suggestions.  Spec §5.4 and §8.

ONE indexed query against the precomputed `product_affinity` table, then a
pass of pure arithmetic in `app.domain.advisor`.  No model runs here (§13).

TIER 1: the result is a proposal.  Nothing in this path writes a monetary
column or moves the state machine (§8).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.advisor import decide as advisor_decide
from app.domain.types import (
    AdvisorSnapshot,
    CandidateSnapshot,
    Decision,
    OrderLineSnapshot,
)
from app.domain.verifiers import verify_advisor
from app.models.tables import Config, Product, ProductAffinity, Quotation, QuoteLine, Stock
from app.services.decision_log import run_agent

DEFAULT_MIN_SUGGESTION_MARGIN = Decimal("15")
MAX_CANDIDATES = 24


def build_advisor_snapshot(session: Session, quotation: Quotation) -> AdvisorSnapshot:
    lines = session.scalars(
        select(QuoteLine)
        .where(QuoteLine.quotation_id == quotation.id)
        .order_by(QuoteLine.id)
    ).all()

    order_lines, on_quote = [], set()
    for line in lines:
        product = session.get(Product, line.product_id)
        if product is None:
            continue
        on_quote.add(product.id)
        order_lines.append(OrderLineSnapshot(
            product_id=product.id,
            list_price=line.unit_price,
            discount_pct=line.discount_pct,
            unit_cost=product.unit_cost,
            qty=line.qty,
        ))

    candidates: list[CandidateSnapshot] = []
    if on_quote:
        # the single indexed query (§5.4)
        edges = session.scalars(
            select(ProductAffinity)
            .where(ProductAffinity.antecedent_id.in_(on_quote))
            .order_by(ProductAffinity.lift.desc())
            .limit(MAX_CANDIDATES)
        ).all()

        seen: set[int] = set()
        for edge in edges:
            if edge.consequent_id in on_quote or edge.consequent_id in seen:
                continue  # never suggest what is already on the quote
            seen.add(edge.consequent_id)
            product = session.get(Product, edge.consequent_id)
            if product is None:
                continue
            antecedent = session.get(Product, edge.antecedent_id)
            candidates.append(CandidateSnapshot(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                category=product.category,
                list_price=product.list_price,
                unit_cost=product.unit_cost,
                is_promoted=product.is_promoted,
                has_stock=_has_stock(session, product.id),
                support=edge.support,
                confidence=edge.confidence,
                lift=edge.lift,
                antecedent_product_id=edge.antecedent_id,
                antecedent_name=antecedent.name if antecedent else "",
            ))

    return AdvisorSnapshot(
        quotation_id=quotation.id,
        lines=order_lines,
        candidates=candidates,
        min_suggestion_margin_pct=_config(
            session, "min_suggestion_margin_pct", DEFAULT_MIN_SUGGESTION_MARGIN
        ),
    )


def _has_stock(session: Session, product_id: int) -> bool:
    rows = session.scalars(
        select(Stock).where(Stock.product_id == product_id)
    ).all()
    return any(r.qty_available > 0 for r in rows)


def _config(session: Session, key: str, fallback: Decimal) -> Decimal:
    row = session.scalar(select(Config).where(Config.key == key))
    return Decimal(row.value) if row else fallback


def suggest(
    session: Session, quotation: Quotation, actor_id: int | None = None
) -> dict:
    """Run the advisor, verify it, log it. Failing suggestions are DROPPED
    silently (§8) — never surfaced with a warning attached."""
    snapshot = build_advisor_snapshot(session, quotation)
    decision, verdict, _reasons = run_agent(
        session,
        agent="advisor",
        decide=advisor_decide,
        snapshot=snapshot,
        verifier=None,  # the advisor verifier filters, it does not pass/fail
        quotation_id=quotation.id,
        actor_id=actor_id,
    )

    suggestions = decision.output["suggestions"]
    _v, dropped, kept = verify_advisor(
        [
            {
                "sku": s["sku"],
                "resulting_margin_pct": s["projected_margin_pct"],
                "has_stock": s["has_stock"],
                **s,
            }
            for s in suggestions
        ],
        snapshot.min_suggestion_margin_pct,
    )

    return {
        "quotation_id": quotation.id,
        "suggestions": kept,
        "considered": decision.output["considered"],
        "dropped": dropped,
        "explanation": decision.explanation,
        "tier": 1,
    }
