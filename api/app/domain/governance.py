"""Blended Discount Risk Score (BDRS) + approval routing.  Spec §5.1.

The differentiator is that this is *blended*: it aggregates per-line ceiling
breaches rather than testing one order-level threshold.  Golden Case B ("death
by a thousand cuts") is the proof — five lines each only 2-3pp over ceiling, no
single line alarming, and the blended score still routes to a manager.  See
``tests/golden/test_governance.py::test_case_b_beats_the_naive_rule``.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.types import (
    ApproverRole,
    Decision,
    GovernanceSnapshot,
    LineSnapshot,
)

ENGINE_VERSION = "governance/1.0.0"  # bump on ANY rule change

# --- caps, in percentage points ------------------------------------------
CAP_WORST = Decimal("10.0")
CAP_LEAK = Decimal("5.0")
CAP_MARGIN = Decimal("10.0")

# --- component weights ----------------------------------------------------
W_WORST = Decimal("40.0")
W_BLEND = Decimal("30.0")
W_MARGIN = Decimal("20.0")
W_CTX = Decimal("10.0")

# --- routing thresholds ---------------------------------------------------
HARD_STOP_EXCESS_PP = Decimal("15.0")
ROUTE_MANAGER_MIN = Decimal("20.0")
ROUTE_FINANCE_MIN = Decimal("50.0")

# a line this far below its floor margin is a hard stop on its own
HARD_STOP_MARGIN_BELOW_FLOOR_PP = Decimal("10.0")

# --- context points (additive, capped at W_CTX) ---------------------------
CTX_NEW_CUSTOMER = Decimal("3")
CTX_LARGE_ORDER = Decimal("3")
CTX_LONG_TERM = Decimal("2")
CTX_REP_ANOMALY = Decimal("2")
CTX_LONG_TERM_MONTHS = 12
CTX_REP_Z_THRESHOLD = 3.5


def _fmt(d: Decimal) -> str:
    """Format a percentage for explanation prose: 18 -> '18', 7.5 -> '7.5'."""
    d = Decimal(d)
    if d == d.to_integral_value():
        return str(int(d))
    return str(d.normalize())


def _fmt1(d: Decimal) -> str:
    """One decimal place, always. '8.0pp over', 'contributes 32.0 of 40'."""
    return f"{Decimal(d):.1f}"


# --------------------------------------------------------------------------
# aggregates
# --------------------------------------------------------------------------


def worst_excess(lines: list[LineSnapshot]) -> Decimal:
    """worst = max(excess_i)"""
    return max((ln.excess_pct for ln in lines), default=Decimal(0))


def leak_pct(lines: list[LineSnapshot]) -> Decimal:
    """leak_pct = 100 * sum(excess_i/100 * list_value_i) / sum(list_value_i)

    Discount given away above ceiling, expressed as a percentage of total list
    value.  This is the term that catches many-small-breaches.
    """
    total_list = sum((ln.list_value for ln in lines), Decimal(0))
    if total_list == 0:
        return Decimal(0)
    leaked = sum(
        (ln.excess_pct / Decimal(100) * ln.list_value for ln in lines), Decimal(0)
    )
    return Decimal(100) * leaked / total_list


def margin_shortfall(lines: list[LineSnapshot]) -> Decimal:
    """margin_short = sum(shortfall_i * net_i) / sum(net_i)

    Net-value-weighted, so a shortfall on a big line counts for more.
    """
    total_net = sum((ln.net_value for ln in lines), Decimal(0))
    if total_net == 0:
        return Decimal(0)
    weighted = sum(
        (ln.margin_shortfall_pct * ln.net_value for ln in lines), Decimal(0)
    )
    return weighted / total_net


def context_points(snap: GovernanceSnapshot) -> tuple[Decimal, list[str]]:
    """Additive context signals, capped at W_CTX. Returns (points, reasons)."""
    pts = Decimal(0)
    why: list[str] = []

    if snap.customer_is_new:
        pts += CTX_NEW_CUSTOMER
        why.append(f"new customer (+{_fmt(CTX_NEW_CUSTOMER)})")

    order_value = sum((ln.net_value for ln in snap.lines), Decimal(0))
    if order_value > snap.large_order_threshold:
        pts += CTX_LARGE_ORDER
        why.append(
            f"order value {_fmt1(order_value)} above threshold "
            f"{_fmt1(snap.large_order_threshold)} (+{_fmt(CTX_LARGE_ORDER)})"
        )

    if snap.subscription_term_months > CTX_LONG_TERM_MONTHS:
        pts += CTX_LONG_TERM
        why.append(
            f"subscription term {snap.subscription_term_months} months "
            f"> {CTX_LONG_TERM_MONTHS} (+{_fmt(CTX_LONG_TERM)})"
        )

    if snap.rep_discount_robust_z > CTX_REP_Z_THRESHOLD:
        pts += CTX_REP_ANOMALY
        why.append(
            f"rep discount robust-z {snap.rep_discount_robust_z:.2f} "
            f"> {CTX_REP_Z_THRESHOLD} (+{_fmt(CTX_REP_ANOMALY)})"
        )

    return min(pts, W_CTX), why


# --------------------------------------------------------------------------
# routing
# --------------------------------------------------------------------------


def _hard_stop_lines(lines: list[LineSnapshot]) -> list[LineSnapshot]:
    """Lines that force Finance regardless of score. §5.1 routing block."""
    return [
        ln
        for ln in lines
        if ln.excess_pct > HARD_STOP_EXCESS_PP
        or ln.margin_pct < ln.floor_margin_pct - HARD_STOP_MARGIN_BELOW_FLOOR_PP
    ]


def route(score: Decimal, lines: list[LineSnapshot]) -> list[str]:
    """Approval chain for a score. Monotone non-decreasing in score."""
    if _hard_stop_lines(lines):
        return [ApproverRole.SALES_MANAGER.value, ApproverRole.FINANCE.value]
    if score < ROUTE_MANAGER_MIN:
        return []
    if score < ROUTE_FINANCE_MIN:
        return [ApproverRole.SALES_MANAGER.value]
    return [ApproverRole.SALES_MANAGER.value, ApproverRole.FINANCE.value]


# --------------------------------------------------------------------------
# the agent
# --------------------------------------------------------------------------


def decide(snapshot: GovernanceSnapshot) -> Decision:
    """Score a quotation and produce its approval chain.

    Deterministic: no clock, no randomness, no I/O.  Same snapshot in, same
    Decision out, which is what makes ``decision_log`` replayable (§10.5).
    """
    lines = snapshot.lines

    worst = worst_excess(lines)
    leak = leak_pct(lines)
    m_short = margin_shortfall(lines)
    ctx, ctx_why = context_points(snapshot)

    # each component is capped at its own weight
    c1 = min(W_WORST, W_WORST * worst / CAP_WORST)
    c2 = min(W_BLEND, W_BLEND * leak / CAP_LEAK)
    c3 = min(W_MARGIN, W_MARGIN * m_short / CAP_MARGIN)
    c4 = min(W_CTX, ctx)

    # score is rounded once, from the *unrounded* components (§5.1)
    score = round(c1 + c2 + c3 + c4, 1)
    chain = route(score, lines)

    explanation = _explain(snapshot, worst, leak, m_short, c1, c2, c3, c4,
                           ctx_why, score, chain)

    output = {
        "score": float(score),
        "approval_chain": chain,
        "components": {
            "worst_line": float(round(c1, 1)),
            "blended_leak": float(round(c2, 1)),
            "margin_shortfall": float(round(c3, 1)),
            "context": float(round(c4, 1)),
        },
        "aggregates": {
            "worst": float(round(worst, 2)),
            "leak_pct": float(round(leak, 2)),
            "margin_short": float(round(m_short, 2)),
            "context_points": float(round(ctx, 2)),
        },
        "hard_stop": bool(_hard_stop_lines(lines)),
        "breaching_line_ids": [ln.line_id for ln in lines if ln.excess_pct > 0],
    }

    return Decision(
        output=output,
        engine_version=ENGINE_VERSION,
        input_hash=snapshot.input_hash(),
        explanation=explanation,
    )


def _explain(snapshot, worst, leak, m_short, c1, c2, c3, c4, ctx_why,
             score, chain) -> list[str]:
    """Human-readable, per-line where applicable. §5.1."""
    out: list[str] = []
    lines = snapshot.lines

    breaching = [ln for ln in lines if ln.excess_pct > 0]
    # deterministic ordering: worst breach first, line_id as tie-break
    breaching.sort(key=lambda ln: (-ln.excess_pct, ln.line_id))

    for ln in breaching:
        base = (
            f"{ln.product_name}: {_fmt(ln.discount_pct)}% given vs "
            f"{_fmt(ln.ceiling_pct)}% ceiling → {_fmt1(ln.excess_pct)}pp over"
        )
        if ln.excess_pct == worst:
            # this line is what sets the worst-line component
            out.append(f"{base} (contributes {_fmt1(c1)} of {_fmt(W_WORST)})")
        else:
            out.append(base)

    if not breaching:
        out.append("All lines within their discount ceilings.")

    if leak > 0:
        out.append(
            f"Blended leak {_fmt1(leak)}% of list value across "
            f"{len(breaching)} breaching line(s) "
            f"(contributes {_fmt1(c2)} of {_fmt(W_BLEND)})"
        )

    short_lines = [ln for ln in lines if ln.margin_shortfall_pct > 0]
    short_lines.sort(key=lambda ln: (-ln.margin_shortfall_pct, ln.line_id))
    for ln in short_lines:
        out.append(
            f"{ln.product_name}: margin {_fmt(ln.margin_pct)}% below floor "
            f"{_fmt(ln.floor_margin_pct)}% → "
            f"{_fmt1(ln.margin_shortfall_pct)}pp short"
        )
    if m_short > 0:
        out.append(
            f"Net-weighted margin shortfall {_fmt1(m_short)}pp "
            f"(contributes {_fmt1(c3)} of {_fmt(W_MARGIN)})"
        )

    for reason in ctx_why:
        out.append(f"Context: {reason}")

    hard = _hard_stop_lines(lines)
    if hard:
        names = ", ".join(ln.product_name for ln in hard)
        out.append(
            f"HARD STOP: {names} breaches the "
            f"{_fmt(HARD_STOP_EXCESS_PP)}pp single-line limit or sits "
            f"{_fmt(HARD_STOP_MARGIN_BELOW_FLOOR_PP)}pp below floor margin "
            f"→ Finance regardless of score."
        )

    out.append(
        f"BDRS {_fmt1(score)} → "
        + (f"approval chain {chain}" if chain else "auto-approve")
    )
    return out
