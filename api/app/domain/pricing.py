"""Shared pricing/margin maths.  Pure.

There is exactly ONE margin function in the system.  §5.4 requires the Advisor
to compute `margin_delta_if_added` with "the same margin function the
governance engine uses" — the only way to guarantee that is for both to call
this.
"""

from __future__ import annotations

from decimal import Decimal

HUNDRED = Decimal(100)


def net_unit_price(list_price: Decimal, discount_pct: Decimal) -> Decimal:
    """Unit price after discount.  Percentages are whole numbers (§12)."""
    return Decimal(list_price) * (Decimal(1) - Decimal(discount_pct) / HUNDRED)


def line_net_value(list_price: Decimal, discount_pct: Decimal, qty: int) -> Decimal:
    return net_unit_price(list_price, discount_pct) * Decimal(qty)


def margin_pct(list_price: Decimal, discount_pct: Decimal, unit_cost: Decimal) -> Decimal:
    """Gross margin on the discounted price, as a whole-number percentage.

    Returns 0 for a zero net price rather than dividing by zero: a fully
    discounted line has no margin to speak of, and the governance engine
    already treats it as a maximal shortfall against any positive floor.
    """
    net = net_unit_price(list_price, discount_pct)
    if net <= 0:
        return Decimal(0)
    return (net - Decimal(unit_cost)) / net * HUNDRED


def order_margin_pct(lines: list[tuple[Decimal, Decimal, Decimal, int]]) -> Decimal:
    """Net-value-weighted margin across lines.

    Each line is (list_price, discount_pct, unit_cost, qty).
    """
    total_net = Decimal(0)
    total_cost = Decimal(0)
    for list_price, discount, unit_cost, qty in lines:
        total_net += line_net_value(list_price, discount, qty)
        total_cost += Decimal(unit_cost) * Decimal(qty)
    if total_net <= 0:
        return Decimal(0)
    return (total_net - total_cost) / total_net * HUNDRED
