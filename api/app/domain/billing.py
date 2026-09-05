"""Proration and invoice partitioning.  Spec §5.3.

Day-based, never month fractions.  All money is Decimal — a float in a
monetary path is a bug (§12).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from datetime import timedelta

from app.domain.exceptions import ProrationError
from app.domain.pricing import line_net_value
from app.domain.types import (
    Decision,
    InvoicePlanSnapshot,
    Proration,
    ProrationSnapshot,
)

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


def plan_invoices(snapshot: InvoicePlanSnapshot) -> dict:
    """Partition a confirmed quotation into what to bill now and what to
    schedule.  Pure: `as_of` is injected, never read from the clock (§3).

    A quotation with both kinds produces BOTH an immediate one-time invoice and
    a subscription whose first period is billed now — that is the whole point
    of "hybrid billing lives on the same quotation".
    """
    one_time, recurring = [], []
    for ln in snapshot.lines:
        amount = _money(line_net_value(ln.unit_price, ln.discount_pct, ln.qty))
        row = {
            "product_id": ln.product_id,
            "description": ln.description,
            "qty": ln.qty,
            "unit_price": str(_money(ln.unit_price)),
            "amount": str(amount),
        }
        (recurring if ln.is_recurring else one_time).append(row)

    def total(rows: list[dict]) -> Decimal:
        return _money(sum((Decimal(r["amount"]) for r in rows), Decimal(0)))

    plan: dict = {
        "one_time": {"lines": one_time, "total": str(total(one_time))},
        "recurring": {"lines": recurring, "total": str(total(recurring))},
        "order_total": str(total(one_time) + total(recurring)),
        "as_of": str(snapshot.as_of),
    }

    if recurring:
        start = snapshot.as_of
        period_end = start + timedelta(days=snapshot.billing_interval_days)
        plan["subscription"] = {
            "start_date": str(start),
            "next_bill_date": str(period_end),
            "period_key": start.strftime("%Y-%m"),
            "first_period_total": str(total(recurring)),
        }

    return plan


def decide_invoice_plan(snapshot: InvoicePlanSnapshot) -> Decision:
    plan = plan_invoices(snapshot)
    explanation = [
        f"{len(plan['one_time']['lines'])} one-time line(s) "
        f"→ invoice now for {plan['one_time']['total']}",
    ]
    if plan["recurring"]["lines"]:
        sub = plan["subscription"]
        explanation.append(
            f"{len(plan['recurring']['lines'])} recurring line(s) → subscription "
            f"from {sub['start_date']}, next bill {sub['next_bill_date']}"
        )
    else:
        explanation.append("no recurring lines → no subscription created")

    return Decision(
        output=plan,
        engine_version=ENGINE_VERSION,
        input_hash=snapshot.input_hash(),
        explanation=explanation,
    )


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
