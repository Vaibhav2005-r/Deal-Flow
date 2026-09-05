"""Anomaly detection golden cases — spec §10.4."""

from datetime import date

import pytest

from app.domain.sentinel import MIN_HISTORY_FOR_REP, decide, effective_history, robust_z
from app.domain.types import SentinelSnapshot

HISTORY = [8, 9, 7, 10, 8, 9, 11, 8, 7, 9, 10, 8]


def test_robust_z_golden_values():
    assert round(robust_z(9, HISTORY), 2) == 0.67    # normal
    assert round(robust_z(14, HISTORY), 2) == 7.42   # anomaly
    assert round(robust_z(22, HISTORY), 2) == 18.21  # anomaly


def test_only_the_outliers_cross_the_threshold():
    assert abs(robust_z(9, HISTORY)) <= 3.5
    assert abs(robust_z(14, HISTORY)) > 3.5
    assert abs(robust_z(22, HISTORY)) > 3.5


def test_mad_of_zero_does_not_divide_by_zero():
    """A perfectly flat history has MAD 0; the 1e-9 floor keeps this finite."""
    z = robust_z(10, [5, 5, 5, 5])
    assert z != 0 and z == z  # finite, not NaN


def test_small_n_guard_uses_team_history():
    """§5.5: with <8 historical quotes the rep's OWN median must not be used —
    otherwise every new rep's second quote reads as an anomaly."""
    snap = SentinelSnapshot(
        as_of=date(2026, 9, 5),
        last_activity_at=date(2026, 9, 5),
        discount_pct=14,
        rep_discount_history=[8, 9, 7],          # only 3 -> too few
        team_discount_history=[float(h) for h in HISTORY],
    )
    history, source = effective_history(snap)
    assert source == "team"
    assert history == [float(h) for h in HISTORY]
    assert len(snap.rep_discount_history) < MIN_HISTORY_FOR_REP


def test_rep_history_used_once_it_is_large_enough():
    snap = SentinelSnapshot(
        as_of=date(2026, 9, 5),
        last_activity_at=date(2026, 9, 5),
        discount_pct=9,
        rep_discount_history=[float(h) for h in HISTORY],
        team_discount_history=[1.0, 2.0],
    )
    _history, source = effective_history(snap)
    assert source == "rep"


def _snap(**kw):
    base = dict(
        as_of=date(2026, 9, 5),
        last_activity_at=date(2026, 9, 5),
        stall_days=7,
        discount_pct=9,
        rep_discount_history=[float(h) for h in HISTORY],
    )
    base.update(kw)
    return SentinelSnapshot(**base)


def test_stalled_deal_alerts_alone():
    """Stalled is the one detector that does not need a second vote."""
    d = decide(_snap(last_activity_at=date(2026, 8, 20)))
    assert d.output["stalled"] is True
    assert d.output["alert"] is True


def test_single_detector_does_not_alert():
    """One detector agreeing is not enough (§5.5)."""
    d = decide(_snap(discount_pct=22))
    assert d.output["discount_anomaly"] is True
    assert d.output["delivery_slippage"] is False
    assert d.output["alert"] is False, "one non-stall detector must not alert"


def test_two_detectors_agreeing_alerts():
    d = decide(_snap(
        discount_pct=22,
        promised_date=date(2026, 9, 10),
        earliest_feasible_date=date(2026, 9, 20),
    ))
    assert d.output["discount_anomaly"] and d.output["delivery_slippage"]
    assert d.output["alert"] is True


def test_isolation_forest_is_never_the_sole_reason():
    """§5.5: the multivariate model is a SECONDARY signal only."""
    d = decide(_snap(isolation_forest_outlier=True))
    assert d.output["isolation_forest_outlier"] is True
    assert d.output["alert"] is False, "iForest alone must never raise an alert"

    # but it can supply the second vote alongside a real detector
    d2 = decide(_snap(discount_pct=22, isolation_forest_outlier=True))
    assert d2.output["alert"] is True


def test_sentinel_is_tier_1_and_writes_no_state():
    """§8 trust ladder: T1 agents emit proposals, never state."""
    o = decide(_snap()).output
    assert o["tier"] == 1
    assert o["writes_state"] is False


# --------------------------------------------------------------------------
# closed deals cannot stall
# --------------------------------------------------------------------------


def _idle(state: str) -> SentinelSnapshot:
    """A deal untouched for 243 days, in the given state."""
    return SentinelSnapshot(
        quotation_id=1,
        quotation_state=state,
        as_of=date(2026, 9, 5),
        last_activity_at=date(2026, 1, 5),
        stall_days=7,
        discount_pct=9,
        rep_discount_history=[float(h) for h in HISTORY],
    )


def test_a_paid_deal_never_stalls():
    """REGRESSION. "Stalled" means someone still owes this deal an action.
    A PAID deal is complete, so elapsed silence carries no signal.

    Before this rule, every won deal in the history re-read as stalled
    forever: 200 of 202 alerts on the Deal Health dashboard were PAID deals,
    while the only two live deals went unflagged.
    """
    out = decide(_idle("PAID")).output
    assert out["closed"] is True
    assert out["stalled"] is False
    assert out["alert"] is False
    assert any("cannot stall" in line for line in decide(_idle("PAID")).explanation)


@pytest.mark.parametrize(
    "state",
    ["DRAFT", "PENDING_MANAGER", "READY_TO_FULFILL", "SENT",
     "UNDER_NEGOTIATION", "CONFIRMED", "FULFILLING"],
)
def test_open_deals_still_stall(state):
    out = decide(_idle(state)).output
    assert out["closed"] is False
    assert out["stalled"] is True
    assert out["alert"] is True, "stalled stands alone (§5.5)"


def test_an_unpaid_invoice_still_stalls():
    """The gate is deliberately narrow: INVOICED is NOT closed, because an
    unpaid invoice is still awaiting an action."""
    out = decide(_idle("INVOICED")).output
    assert out["closed"] is False
    assert out["stalled"] is True


def test_an_unknown_state_is_treated_as_open():
    """Fail safe: a caller that omits the state gets the un-gated behaviour
    rather than a silent pass that hides real stalls."""
    out = decide(_idle("")).output
    assert out["closed"] is False
    assert out["stalled"] is True


def test_closing_a_deal_is_the_only_thing_that_changed():
    """A closed deal still reports its other detectors honestly — we suppress
    the stall, not the whole record."""
    snap = _idle("PAID").model_copy(update={"discount_pct": 22.0})
    out = decide(snap).output
    assert out["stalled"] is False
    assert out["discount_anomaly"] is True, "other detectors still run"


def test_engine_version_was_bumped_for_the_rule_change():
    """§4: bump engine_version on ANY rule change, so rows logged under the
    old rule keep replaying against the old rule."""
    from app.domain import sentinel

    assert sentinel.ENGINE_VERSION == "sentinel/1.1.0"
    assert sentinel.CLOSED_STATES == frozenset({"PAID"})
