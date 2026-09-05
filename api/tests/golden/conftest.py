"""Shared builders for the golden cases (spec §10)."""

from decimal import Decimal as D

from app.domain.types import CustomerTier, GovernanceSnapshot, LineSnapshot


def line(
    line_id: int,
    name: str,
    category: str,
    list_value: str,
    discount_pct: str,
    tier_ceiling: str,
    category_ceiling: str,
    margin_pct: str,
    floor_margin: str = "20",
) -> LineSnapshot:
    return LineSnapshot(
        line_id=line_id,
        product_name=name,
        category=category,
        list_value=D(list_value),
        discount_pct=D(discount_pct),
        tier_ceiling_pct=D(tier_ceiling),
        category_ceiling_pct=D(category_ceiling),
        margin_pct=D(margin_pct),
        floor_margin_pct=D(floor_margin),
        ceiling_source=f"discount_policy:gold/{category}",
    )


def snapshot(lines, **kw) -> GovernanceSnapshot:
    kw.setdefault("customer_tier", CustomerTier.GOLD)
    # high enough that the large-order context point never fires by accident;
    # every golden case expects context = 0.0
    kw.setdefault("large_order_threshold", D("500000"))
    return GovernanceSnapshot(lines=lines, **kw)
