"""Proration and invoice partitioning.  Spec §5.3.

Day-based, never month fractions.  All money is Decimal — a float in a
monetary path is a bug (§12).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.exceptions import ProrationError
from app.domain.types import Decision, Proration, ProrationSnapshot

ENGINE_VERSION = "billing/1.0.0"

CENTS = Decimal("0.01")


def _money(d: Decimal) -> Decimal:
    """Quantise to 2dp. ROUND_HALF_UP is the money convention — Python's bare
    round() would use banker's rounding and drift against the ledger."""
    return Decimal(d).quantize(CENTS, rounding=ROUND_HALF_UP)


def prorate(
    period_start: date,
    period_end: date,
    change_date: date,
    old_amount: Decimal,
    new_amount: Decimal,
) -> Proration:
    """Day-based proration of a mid-period plan change.

    credit = what we refund for the unused remainder at the OLD price
    charge = what we bill for that same remainder at the NEW price
    delta  = charge - credit  (negative => credit note, never a negative line)
    """
    total = (period_end - period_start).days
    remaining = (period_end - change_date).days

    if total <= 0:
        raise ProrationError(
            f"period_end {period_end} must be after period_start {period_start}"
        )
    if not (0 <= remaining <= total):
        raise ProrationError(
            f"change_date {change_date} outside period "
            f"[{period_start}, {period_end}] (remaining={remaining}, total={total})"
        )

    credit = _money(Decimal(old_amount) * remaining / total)
    charge = _money(Decimal(new_amount) * remaining / total)
    return Proration(credit=credit, charge=charge, delta=charge - credit)


def partition_invoice_lines(lines: list[dict]) -> dict[str, list[dict]]:
    """Hybrid billing (§5.3): one-time and recurring live on the SAME quotation.

    One-time lines invoice immediately on confirmation; recurring lines create
    a subscription and invoice on schedule.
    """
    one_time = [ln for ln in lines if not ln.get("is_recurring")]
    recurring = [ln for ln in lines if ln.get("is_recurring")]
    return {"one_time": one_time, "recurring": recurring}


def decide(snapshot: ProrationSnapshot) -> Decision:
    p = prorate(
        snapshot.period_start,
        snapshot.period_end,
        snapshot.change_date,
        snapshot.old_amount,
        snapshot.new_amount,
    )
    total = (snapshot.period_end - snapshot.period_start).days
    remaining = (snapshot.period_end - snapshot.change_date).days

    output = {
        "credit": str(p.credit),
        "charge": str(p.charge),
        "delta": str(p.delta),
        "days_total": total,
        "days_remaining": remaining,
        "emits_credit_note": p.delta < 0,
    }
    explanation = [
        f"{remaining} of {total} days remain in the period",
        f"credit {p.credit} at the old rate, charge {p.charge} at the new rate",
        (
            f"net {p.delta} → credit note"
            if p.delta < 0
            else f"net {p.delta} → invoice line"
        ),
    ]
    return Decision(
        output=output,
        engine_version=ENGINE_VERSION,
        input_hash=snapshot.input_hash(),
        explanation=explanation,
    )
