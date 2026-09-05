"""ORM -> pure-domain snapshot builders.

This is the only place the database meets the domain.  Routers stay thin (§12):
they build a Snapshot here, call the domain, persist the Decision, and return.

CEILING RESOLUTION
------------------
§5.1 takes `ceiling_i = min(tier_ceiling_pct, category_ceiling_pct)`, while §6
stores one `discount_policy` row per UNIQUE(tier, category).  The two are
reconciled like this:

  category_ceiling_pct = the (tier, category) policy row — the specific rule
  tier_ceiling_pct     = MAX(ceiling_pct) across that tier's policies — the
                         broadest this tier is ever allowed, an upper bound the
                         category rule can only tighten

min() then yields the policy ceiling in the normal case, which reproduces the
golden Case A values exactly (GOLD/Hardware 15, GOLD/Service 10).

Every resolved line records `ceiling_source`, naming the policy row it came
from.  A line whose ceiling could NOT be resolved is a hard error, never a
default — the Governance verifier (§8) fails the run if a ceiling looks
defaulted, and silently guessing here is precisely what that check exists to
catch.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.exceptions import DomainError
from app.domain.pricing import margin_pct
from app.domain.types import CustomerTier, GovernanceSnapshot, LineSnapshot
from app.models.tables import (
    Config,
    Customer,
    DiscountPolicy,
    Product,
    Quotation,
    QuoteLine,
)

DEFAULT_LARGE_ORDER_THRESHOLD = Decimal("500000")


class PolicyResolutionError(DomainError):
    """No discount_policy row for a (tier, category) — refuse to guess."""


def _config(session: Session, key: str, fallback: Decimal) -> Decimal:
    row = session.scalar(select(Config).where(Config.key == key))
    return Decimal(row.value) if row else fallback


def build_governance_snapshot(
    session: Session,
    quotation: Quotation,
    rep_discount_robust_z: float = 0.0,
) -> GovernanceSnapshot:
    """Resolve every ceiling from policy and assemble the scoring input."""
    customer = session.get(Customer, quotation.customer_id)
    if customer is None:
        raise PolicyResolutionError(f"quotation {quotation.id} has no customer")

    policies = session.scalars(
        select(DiscountPolicy).where(DiscountPolicy.tier == customer.tier)
    ).all()
    if not policies:
        raise PolicyResolutionError(
            f"no discount_policy rows for tier {customer.tier!r} — "
            f"cannot resolve ceilings, refusing to default"
        )

    by_category = {p.category: p for p in policies}
    tier_ceiling = max(p.ceiling_pct for p in policies)

    lines = session.scalars(
        select(QuoteLine)
        .where(QuoteLine.quotation_id == quotation.id)
        .order_by(QuoteLine.id)
    ).all()

    snapshot_lines: list[LineSnapshot] = []
    for line in lines:
        product = session.get(Product, line.product_id)
        if product is None:
            raise PolicyResolutionError(f"quote_line {line.id} has no product")

        policy = by_category.get(product.category)
        if policy is None:
            raise PolicyResolutionError(
                f"no discount_policy for ({customer.tier}, {product.category}) — "
                f"quote_line {line.id} ({product.name}) cannot be scored"
            )

        snapshot_lines.append(
            LineSnapshot(
                line_id=line.id,
                product_name=product.name,
                category=product.category,
                list_value=line.unit_price * Decimal(line.qty),
                discount_pct=line.discount_pct,
                tier_ceiling_pct=tier_ceiling,
                category_ceiling_pct=policy.ceiling_pct,
                margin_pct=margin_pct(line.unit_price, line.discount_pct,
                                      product.unit_cost),
                floor_margin_pct=policy.floor_margin_pct,
                is_recurring=line.is_recurring,
                ceiling_source=f"discount_policy:{customer.tier}/{product.category}",
            )
        )

    subscription_months = 24 if any(ln.is_recurring for ln in snapshot_lines) else 0

    return GovernanceSnapshot(
        quotation_id=quotation.id,
        customer_tier=CustomerTier(str(customer.tier)),
        customer_is_new=customer.first_order_at is None,
        subscription_term_months=subscription_months,
        rep_discount_robust_z=rep_discount_robust_z,
        large_order_threshold=_config(
            session, "large_order_threshold", DEFAULT_LARGE_ORDER_THRESHOLD
        ),
        lines=snapshot_lines,
    )


def persist_resolved_ceilings(
    session: Session, snapshot: GovernanceSnapshot
) -> None:
    """Write the ceiling/margin actually used back onto the quote lines.

    §6 keeps `ceiling_pct_applied` and `margin_pct` on `quote_line` so the
    approval screen can show a per-line breach without recomputing, and so the
    audit trail records what the rule engine actually saw.
    """
    for line_snap in snapshot.lines:
        line = session.get(QuoteLine, line_snap.line_id)
        if line is not None:
            line.ceiling_pct_applied = line_snap.ceiling_pct
            line.margin_pct = line_snap.margin_pct
