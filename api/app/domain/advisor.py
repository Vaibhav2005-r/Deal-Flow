"""Upsell / cross-sell ranking.  Spec §5.4.

TIER 1 — proposals only (§8).  Nothing here may write a monetary field or drive
a state transition.  The output is a list of suggestions for a human to accept.

Affinity is PRECOMPUTED by FP-Growth at seed time and passed in on the
snapshot; §13 explicitly forbids running FP-Growth inside a request handler.
This module does one pass of arithmetic over candidates already fetched by an
indexed query — the §5.4 target is <10ms.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.pricing import line_net_value, order_margin_pct
from app.domain.types import AdvisorSnapshot, CandidateSnapshot, Decision

ENGINE_VERSION = "advisor/1.0.0"

PROMO_BOOST = Decimal("0.5")


def _order_lines(snap: AdvisorSnapshot) -> list[tuple[Decimal, Decimal, Decimal, int]]:
    return [
        (ln.list_price, ln.discount_pct, ln.unit_cost, ln.qty) for ln in snap.lines
    ]


def margin_delta_if_added(
    snap: AdvisorSnapshot, candidate: CandidateSnapshot, qty: int = 1
) -> tuple[Decimal, Decimal, Decimal]:
    """(current_margin, projected_margin, delta) if this candidate is added.

    Uses `order_margin_pct` — the SAME margin function the governance engine
    uses (§5.4). One margin definition, or the advisor and the approver are
    looking at different numbers.
    """
    current = order_margin_pct(_order_lines(snap))
    projected = order_margin_pct(
        _order_lines(snap)
        + [(candidate.list_price, snap.assumed_discount_pct, candidate.unit_cost, qty)]
    )
    return current, projected, projected - current


def rank(snap: AdvisorSnapshot) -> list[dict]:
    """Score, gate and order the candidates.  Deterministic.

        score = lift * (1 + promo_boost) * margin_gate
        margin_gate = 0.0 if adding the line would push order margin below
                      config.min_suggestion_margin_pct else 1.0
        promo_boost = 0.5 if product.is_promoted else 0.0
    """
    scored: list[dict] = []

    for cand in snap.candidates:
        current, projected, delta = margin_delta_if_added(snap, cand)
        gate = Decimal(0) if projected < snap.min_suggestion_margin_pct else Decimal(1)
        boost = PROMO_BOOST if cand.is_promoted else Decimal(0)
        score = cand.lift * (Decimal(1) + boost) * gate

        scored.append({
            "product_id": cand.product_id,
            "sku": cand.sku,
            "name": cand.name,
            "category": cand.category,
            "score": float(round(score, 4)),
            "lift": float(round(cand.lift, 4)),
            "confidence": float(round(cand.confidence, 4)),
            "support": float(round(cand.support, 4)),
            "is_promoted": cand.is_promoted,
            "has_stock": cand.has_stock,
            "margin_gate_passed": gate == 1,
            "current_margin_pct": float(round(current, 2)),
            "projected_margin_pct": float(round(projected, 2)),
            "margin_delta_if_added": float(round(delta, 2)),
            "list_price": str(cand.list_price),
            "because_of": cand.antecedent_name,
        })

    # deterministic ordering: score desc, then lift desc, then sku for ties
    scored.sort(key=lambda s: (-s["score"], -s["lift"], s["sku"]))
    return scored


def decide(snapshot: AdvisorSnapshot) -> Decision:
    ranked = rank(snapshot)
    # a gated-out candidate has score 0 and is not a suggestion
    surviving = [s for s in ranked if s["score"] > 0 and s["has_stock"]]
    top = surviving[: snapshot.top_n]

    explanation = []
    for s in top:
        because = f" (often bought with {s['because_of']})" if s["because_of"] else ""
        explanation.append(
            f"{s['name']}: lift {s['lift']:.2f}{because}, "
            f"order margin {s['current_margin_pct']:.1f}% → "
            f"{s['projected_margin_pct']:.1f}%"
        )
    for s in ranked:
        if not s["margin_gate_passed"]:
            explanation.append(
                f"{s['name']}: dropped — would take order margin to "
                f"{s['projected_margin_pct']:.1f}%, below the "
                f"{snapshot.min_suggestion_margin_pct}% floor"
            )
        elif not s["has_stock"]:
            explanation.append(f"{s['name']}: dropped — no stock anywhere")
    if not top:
        explanation.append("No suggestion clears the margin gate.")

    return Decision(
        output={
            "suggestions": top,
            "considered": len(ranked),
            "tier": 1,
            "writes_state": False,
        },
        engine_version=ENGINE_VERSION,
        input_hash=snapshot.input_hash(),
        explanation=explanation,
    )
