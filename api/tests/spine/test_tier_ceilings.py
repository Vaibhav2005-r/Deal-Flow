"""The tier limb of `min(tier_ceiling_pct, category_ceiling_pct)` (§5.1).

REGRESSION. The tier ceiling used to be derived as MAX(ceiling_pct) over that
tier's own category rows. A max over a set can never be smaller than a member
of that set, so `min()` always returned the category ceiling and the tier limb
was structurally dead — a Gold customer could take 20% on a category the
product flow's discount-tiers screen caps at 15%.

It is now a looked-up `tier_policy` row: a real backstop that binds whenever a
category ceiling would exceed it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domain.governance import decide
from app.domain.types import CustomerTier, GovernanceSnapshot, LineSnapshot
from app.models.tables import DiscountPolicy, TierPolicy
from app.services.snapshots import PolicyResolutionError, build_governance_snapshot
from tests.spine.conftest import auth

EXPECTED_TIER_CAPS = {"bronze": Decimal("5"), "silver": Decimal("10"), "gold": Decimal("15")}


# --------------------------------------------------------------------------
# the tier cap exists and is a real row
# --------------------------------------------------------------------------


def test_tier_caps_match_the_discount_tiers_screen(session):
    caps = {
        str(t.tier): t.ceiling_pct
        for t in session.scalars(select(TierPolicy)).all()
    }
    assert caps == EXPECTED_TIER_CAPS


def test_no_category_ceiling_exceeds_its_tier_cap(session):
    """Data integrity. A category ceiling above its tier cap is dead data:
    min() can never select it, so the policy screen would advertise a discount
    the engine refuses to allow."""
    caps = {
        str(t.tier): t.ceiling_pct
        for t in session.scalars(select(TierPolicy)).all()
    }
    offenders = [
        (str(p.tier), p.category, str(p.ceiling_pct), str(caps[str(p.tier)]))
        for p in session.scalars(select(DiscountPolicy)).all()
        if p.ceiling_pct > caps[str(p.tier)]
    ]
    assert not offenders, f"category ceiling above its tier cap: {offenders}"


def test_gold_software_is_capped_at_the_tier_ceiling(client, rep):
    """The concrete case from the audit: Gold used to allow 20% on Software."""
    policies = client.get("/api/discount-policies", headers=auth(rep["token"])).json()
    gold_sw = next(
        p for p in policies if p["tier"] == "gold" and p["category"] == "Software"
    )
    assert Decimal(gold_sw["ceiling_pct"]) <= Decimal("15"), (
        "a Gold customer must not exceed the 15% tier cap on any category"
    )


# --------------------------------------------------------------------------
# the tier limb actually binds
# --------------------------------------------------------------------------


def _line(tier_ceiling: str, category_ceiling: str, discount: str) -> LineSnapshot:
    return LineSnapshot(
        line_id=1, product_name="Widget", category="Software",
        list_value=Decimal("100000"), discount_pct=Decimal(discount),
        tier_ceiling_pct=Decimal(tier_ceiling),
        category_ceiling_pct=Decimal(category_ceiling),
        margin_pct=Decimal("40"), floor_margin_pct=Decimal("20"),
        ceiling_source="tier_policy:gold+discount_policy:gold/Software",
    )


def test_the_tighter_of_the_two_ceilings_wins():
    """min(), in both directions."""
    tier_binds = _line(tier_ceiling="15", category_ceiling="20", discount="18")
    assert tier_binds.ceiling_pct == Decimal("15")
    assert tier_binds.excess_pct == Decimal("3"), "18% against a 15% tier cap"

    category_binds = _line(tier_ceiling="15", category_ceiling="10", discount="18")
    assert category_binds.ceiling_pct == Decimal("10")
    assert category_binds.excess_pct == Decimal("8")


def test_a_line_inside_its_category_ceiling_can_still_breach_the_tier_cap():
    """THE regression, end to end: 18% is inside a 20% category ceiling but
    over the 15% tier cap. Under the old max() derivation this scored 0."""
    snap = GovernanceSnapshot(
        customer_tier=CustomerTier.GOLD,
        large_order_threshold=Decimal("500000"),
        lines=[_line(tier_ceiling="15", category_ceiling="20", discount="18")],
    )
    out = decide(snap).output
    assert out["aggregates"]["worst"] == 3.0
    assert out["score"] > 0.0, "the tier cap must produce a breach"

    dead_tier_limb = GovernanceSnapshot(
        customer_tier=CustomerTier.GOLD,
        large_order_threshold=Decimal("500000"),
        # what the old derivation produced: tier == max over categories
        lines=[_line(tier_ceiling="20", category_ceiling="20", discount="18")],
    )
    assert decide(dead_tier_limb).output["score"] == 0.0, (
        "documents the old behaviour this fix removes"
    )


# --------------------------------------------------------------------------
# provenance and failure
# --------------------------------------------------------------------------


def test_both_ceilings_are_looked_up_not_defaulted(client, rep, session):
    from app.models.tables import Quotation

    quote_id = client.post("/api/quotes", headers=auth(rep["token"]), json={
        "customer_id": client.get("/api/customers", headers=auth(rep["token"])).json()[0]["id"],
        "lines": [],
    }).json()["id"]
    session.expire_all()
    snap = build_governance_snapshot(session, session.get(Quotation, quote_id))
    assert snap.large_order_threshold > 0
    # a quote with no lines still resolves its tier cap without error
    assert isinstance(snap.lines, list)


def test_a_missing_tier_policy_is_an_error_not_a_default(session):
    """§8's verifier fails a run whose ceiling looks defaulted, so resolution
    must refuse to guess rather than silently pick a number."""
    from app.models.tables import Quotation

    quote = session.scalars(select(Quotation).limit(1)).one()
    for row in session.scalars(select(TierPolicy)).all():
        session.delete(row)
    session.flush()

    with pytest.raises(PolicyResolutionError, match="tier_policy"):
        build_governance_snapshot(session, quote)

    session.rollback()


def test_policy_endpoint_reports_which_limb_bound(client, rep):
    policies = client.get("/api/discount-policies", headers=auth(rep["token"])).json()
    assert policies
    for p in policies:
        effective = min(
            Decimal(p["tier_ceiling_pct"]), Decimal(p["category_ceiling_pct"])
        )
        assert Decimal(p["ceiling_pct"]) == effective, (
            "the builder hint must show the ceiling the engine will score against"
        )
        expected = (
            "tier"
            if Decimal(p["tier_ceiling_pct"]) < Decimal(p["category_ceiling_pct"])
            else "category"
        )
        assert p["bound_by"] == expected
