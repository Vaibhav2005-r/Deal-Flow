"""The agent contract and the replay guarantee.  Spec §4 and §10.5."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import allocation, billing, governance, sentinel
from app.domain.types import (
    AllocationSnapshot,
    Decision,
    ProrationSnapshot,
    SentinelSnapshot,
    WarehouseSnapshot,
    canonical_json,
    sha256_of,
)
from tests.golden.conftest import line, snapshot


def gov_snap():
    return snapshot([
        line(1, "Laptop", "Hardware", "100000", "12", "15", "15", "30"),
        line(2, "Setup Service", "Service", "20000", "18", "20", "10", "14"),
    ])


def alloc_snap():
    return AllocationSnapshot(
        demand={"A": 10, "B": 5, "C": 3},
        ship_fixed_cost=D("150.0"),
        warehouses=[
            WarehouseSnapshot(code="MAIN", unit_ship_cost=D("2.0"),
                              available={"A": 10, "B": 2, "C": 3}),
            WarehouseSnapshot(code="WEST", unit_ship_cost=D("2.5"),
                              available={"A": 2, "B": 5, "C": 3}),
        ],
    )


def bill_snap():
    return ProrationSnapshot(
        period_start=date(2026, 9, 1), period_end=date(2026, 10, 1),
        change_date=date(2026, 9, 16),
        old_amount=D("2000"), new_amount=D("5000"),
    )


def sent_snap():
    return SentinelSnapshot(
        as_of=date(2026, 9, 5), last_activity_at=date(2026, 9, 1),
        discount_pct=9, rep_discount_history=[8, 9, 7, 10, 8, 9, 11, 8, 7, 9, 10, 8],
    )


AGENTS = [
    (governance, gov_snap),
    (allocation, alloc_snap),
    (billing, bill_snap),
    (sentinel, sent_snap),
]
IDS = ["governance", "allocation", "billing", "sentinel"]


@pytest.mark.parametrize("module,build", AGENTS, ids=IDS)
def test_every_agent_returns_the_decision_shape(module, build):
    """§4: every agent implements `decide(snapshot) -> Decision`, exactly."""
    d = module.decide(build())
    assert isinstance(d, Decision)
    assert isinstance(d.output, dict)
    assert d.engine_version == module.ENGINE_VERSION
    assert "/" in d.engine_version, "engine_version is name/semver"
    assert isinstance(d.explanation, list)
    assert all(isinstance(e, str) for e in d.explanation)


@pytest.mark.parametrize("module,build", AGENTS, ids=IDS)
def test_input_hash_is_sha256_of_the_canonical_snapshot(module, build):
    snap = build()
    d = module.decide(snap)
    assert d.input_hash == sha256_of(snap.model_dump(mode="json"))
    assert len(d.input_hash) == 64


@pytest.mark.parametrize("module,build", AGENTS, ids=IDS)
def test_replay_is_byte_for_byte(module, build):
    """§10.5: re-running a pinned engine_version on the logged input must
    reproduce output_json exactly.  Target is 100% — one failure is a bug,
    not a tolerance."""
    snap = build()
    first = module.decide(snap)
    logged_input = snap.model_dump(mode="json")
    logged_output = canonical_json(first.output)

    for _ in range(5):
        replayed = module.decide(type(snap).model_validate(logged_input))
        assert canonical_json(replayed.output) == logged_output
        assert replayed.input_hash == first.input_hash
        assert replayed.engine_version == first.engine_version


def test_canonical_json_is_stable_under_key_order():
    a = {"b": 1, "a": 2, "c": {"z": 1, "y": 2}}
    b = {"c": {"y": 2, "z": 1}, "a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert sha256_of(a) == sha256_of(b)


def test_canonical_json_has_no_incidental_whitespace():
    assert canonical_json({"a": 1, "b": 2}) == '{"a":1,"b":2}'


def test_decision_is_immutable():
    d = governance.decide(gov_snap())
    with pytest.raises(Exception):
        d.output = {}
