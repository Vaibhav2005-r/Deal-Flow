"""Independent oracles.  Spec §8.

These are deterministic RE-CHECKS, not a second model call.  Each runs after
its agent and before the result is persisted or shown.  The verdict is written
to ``decision_log.verifier_verdict`` on every call.

The governance verifier deliberately recomputes the score along a **second,
independently written path**: it works from the raw snapshot fields with plain
arithmetic and does not import any aggregate helper from ``governance.py``.
A copy-pasted re-check would agree with a bug; this one can disagree.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.domain.types import (
    AllocationSnapshot,
    Decision,
    GovernanceSnapshot,
    VerifierVerdict,
)

# --------------------------------------------------------------------------
# governance
# --------------------------------------------------------------------------

_DEFAULTY = ("", "default", "fallback", "none", "hardcoded")


def verify_governance(
    snapshot: GovernanceSnapshot, decision: Decision
) -> tuple[VerifierVerdict, list[str]]:
    """Assert: score recomputed independently matches; every ceiling was really
    looked up (no defaults); routing is monotone in score."""
    reasons: list[str] = []

    # --- 1. independent recomputation (second path, raw arithmetic) --------
    total_list = Decimal(0)
    leaked = Decimal(0)
    total_net = Decimal(0)
    weighted_short = Decimal(0)
    worst = Decimal(0)

    for ln in snapshot.lines:
        ceiling = ln.tier_ceiling_pct
        if ln.category_ceiling_pct < ceiling:
            ceiling = ln.category_ceiling_pct

        excess = ln.discount_pct - ceiling
        if excess < 0:
            excess = Decimal(0)
        if excess > worst:
            worst = excess

        total_list += ln.list_value
        leaked += ln.list_value * excess / Decimal(100)

        net = ln.list_value - (ln.list_value * ln.discount_pct / Decimal(100))
        total_net += net

        short = ln.floor_margin_pct - ln.margin_pct
        if short < 0:
            short = Decimal(0)
        weighted_short += short * net

    leak = Decimal(100) * leaked / total_list if total_list else Decimal(0)
    m_short = weighted_short / total_net if total_net else Decimal(0)

    c1 = Decimal(40) * worst / Decimal(10)
    c1 = Decimal(40) if c1 > Decimal(40) else c1
    c2 = Decimal(30) * leak / Decimal(5)
    c2 = Decimal(30) if c2 > Decimal(30) else c2
    c3 = Decimal(20) * m_short / Decimal(10)
    c3 = Decimal(20) if c3 > Decimal(20) else c3

    ctx = Decimal(0)
    if snapshot.customer_is_new:
        ctx += Decimal(3)
    if total_net > snapshot.large_order_threshold:
        ctx += Decimal(3)
    if snapshot.subscription_term_months > 12:
        ctx += Decimal(2)
    if snapshot.rep_discount_robust_z > 3.5:
        ctx += Decimal(2)
    ctx = Decimal(10) if ctx > Decimal(10) else ctx

    expected = float(round(c1 + c2 + c3 + ctx, 1))
    actual = decision.output.get("score")
    if expected != actual:
        reasons.append(
            f"score mismatch: agent said {actual}, independent path says {expected}"
        )

    # --- 2. every ceiling actually looked up ------------------------------
    for ln in snapshot.lines:
        if ln.ceiling_source.strip().lower() in _DEFAULTY:
            reasons.append(
                f"line {ln.line_id} ({ln.product_name}) has no resolved ceiling "
                f"source — ceiling may have been defaulted, not looked up"
            )

    # --- 3. routing monotone in score -------------------------------------
    chain = decision.output.get("approval_chain", [])
    hard_stop = decision.output.get("hard_stop", False)
    if not hard_stop:
        if actual is not None:
            if actual < 20.0 and chain:
                reasons.append(f"score {actual} < 20 must auto-approve, got {chain}")
            elif 20.0 <= actual < 50.0 and chain != ["SALES_MANAGER"]:
                reasons.append(f"score {actual} must route to manager only, got {chain}")
            elif actual >= 50.0 and chain != ["SALES_MANAGER", "FINANCE"]:
                reasons.append(f"score {actual} must route to finance, got {chain}")
    elif chain != ["SALES_MANAGER", "FINANCE"]:
        reasons.append(f"hard stop must route to finance, got {chain}")

    verdict = VerifierVerdict.PASS if not reasons else VerifierVerdict.FAIL
    return verdict, reasons


# --------------------------------------------------------------------------
# allocation
# --------------------------------------------------------------------------


def verify_allocation(
    snapshot: AllocationSnapshot, decision: Decision
) -> tuple[VerifierVerdict, list[str]]:
    """Assert: allocated + backorder == demand per SKU; no warehouse
    over-allocated vs available; cost <= single-warehouse baseline."""
    reasons: list[str] = []
    lines = decision.output.get("lines", [])

    # --- conservation, per SKU -------------------------------------------
    for sku, want in snapshot.demand.items():
        got = sum(ln["qty"] for ln in lines if ln["sku"] == sku)
        if got != want:
            reasons.append(
                f"SKU {sku}: allocated+backorder {got} != demand {want}"
            )

    # --- capacity ---------------------------------------------------------
    avail = {w.code: w.available for w in snapshot.warehouses}
    taken: dict[tuple[str, str], int] = {}
    for ln in lines:
        if ln["is_backorder"]:
            continue
        key = (ln["warehouse"], ln["sku"])
        taken[key] = taken.get(key, 0) + ln["qty"]
    for (code, sku), qty in taken.items():
        have = avail.get(code, {}).get(sku, 0)
        if qty > have:
            reasons.append(f"{code}/{sku}: allocated {qty} > available {have}")

    # --- never worse than the naive single-warehouse plan -----------------
    from app.domain.allocation import single_warehouse_cost

    baseline = single_warehouse_cost(snapshot)
    cost = Decimal(str(decision.output.get("total_cost", 0)))
    if baseline is not None and cost > baseline:
        reasons.append(
            f"plan cost {cost} exceeds single-warehouse baseline {baseline}"
        )

    verdict = VerifierVerdict.PASS if not reasons else VerifierVerdict.FAIL
    return verdict, reasons


# --------------------------------------------------------------------------
# billing
# --------------------------------------------------------------------------


def verify_billing(
    order_total: Decimal,
    invoices: list[Decimal],
    credit_notes: list[Decimal],
    period_keys: list[tuple[int, str]] | None = None,
) -> tuple[VerifierVerdict, list[str]]:
    """Assert: invoices + credit notes reconcile to the order total, and no
    duplicate (subscription_id, period_key)."""
    reasons: list[str] = []

    booked = sum(invoices, Decimal(0)) - sum(credit_notes, Decimal(0))
    if booked != Decimal(order_total):
        reasons.append(
            f"invoices {sum(invoices, Decimal(0))} - credit notes "
            f"{sum(credit_notes, Decimal(0))} = {booked} != order total {order_total}"
        )

    if period_keys:
        seen: set[tuple[int, str]] = set()
        for key in period_keys:
            if key in seen:
                reasons.append(f"duplicate billing period {key}")
            seen.add(key)

    verdict = VerifierVerdict.PASS if not reasons else VerifierVerdict.FAIL
    return verdict, reasons


def verify_proration_symmetry(
    up_delta: Decimal, down_delta: Decimal
) -> tuple[VerifierVerdict, list[str]]:
    """An upgrade and the mirror-image downgrade must cancel exactly."""
    if up_delta + down_delta != Decimal(0):
        return VerifierVerdict.FAIL, [
            f"proration asymmetry: {up_delta} + {down_delta} != 0"
        ]
    return VerifierVerdict.PASS, []


# --------------------------------------------------------------------------
# advisor  (T1 — failures drop the suggestion silently)
# --------------------------------------------------------------------------


def verify_advisor(
    suggestions: list[dict], min_margin_pct: Decimal
) -> tuple[VerifierVerdict, list[str], list[dict]]:
    """Assert each suggestion passes the margin gate and has stock somewhere.

    On failure the suggestion is DROPPED, not surfaced — returns the survivors.
    """
    kept, reasons = [], []
    for s in suggestions:
        if Decimal(str(s.get("resulting_margin_pct", 0))) < min_margin_pct:
            reasons.append(f"{s.get('sku')}: below min suggestion margin — dropped")
            continue
        if not s.get("has_stock", False):
            reasons.append(f"{s.get('sku')}: no stock anywhere — dropped")
            continue
        kept.append(s)
    verdict = VerifierVerdict.PASS if not reasons else VerifierVerdict.FAIL
    return verdict, reasons, kept


# --------------------------------------------------------------------------
# narrator  (T2 — prose only)
# --------------------------------------------------------------------------

_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _numbers_in(text: str) -> set[str]:
    out = set()
    for raw in _NUM.findall(text):
        cleaned = raw.replace(",", "").rstrip(".")
        if cleaned in ("", "-"):
            continue
        d = Decimal(cleaned)
        out.add(str(d.normalize()))
    return out


def verify_narrator(
    text: str, source_record: dict[str, Any]
) -> tuple[VerifierVerdict, list[str]]:
    """Assert EVERY number in the generated prose also appears in the source.

    This is the guardrail behind §1's invariant: no model output ever becomes a
    number anyone trusts.  On FAIL the caller discards the text and uses the
    deterministic template.
    """
    allowed = _numbers_in(canonical_numbers(source_record))
    found = _numbers_in(text)
    hallucinated = sorted(found - allowed)
    if hallucinated:
        return VerifierVerdict.FAIL, [
            f"number(s) not present in the source record: {', '.join(hallucinated)}"
        ]
    return VerifierVerdict.PASS, []


def canonical_numbers(record: dict[str, Any]) -> str:
    """Flatten a record to a string containing every numeric literal in it."""
    parts: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        else:
            parts.append(str(v))

    walk(record)
    return " ".join(parts)
