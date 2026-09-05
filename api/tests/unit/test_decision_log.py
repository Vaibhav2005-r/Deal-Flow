"""§4: "Every call to any agent writes one row to decision_log. No exceptions."

Uses a stub session so this stays a fast unit test with no database.
"""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from app.domain.governance import decide as governance_decide
from app.domain.types import VerifierVerdict
from app.domain.verifiers import verify_governance
from app.services.decision_log import run_agent
from tests.golden.conftest import line, snapshot


class StubSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def gov_snap(discount="18"):
    return snapshot([
        line(1, "Laptop", "Hardware", "100000", "12", "15", "15", "30"),
        line(2, "Setup Service", "Service", "20000", discount, "20", "10", "14"),
    ])


def test_run_agent_writes_exactly_one_row():
    s = StubSession()
    run_agent(s, agent="governance", decide=governance_decide,
              snapshot=gov_snap(), verifier=verify_governance)
    assert len(s.added) == 1


def test_logged_row_carries_the_full_replay_payload():
    """input_json must be the FULL snapshot so replay needs no other table."""
    s = StubSession()
    snap = gov_snap()
    decision, verdict, _reasons = run_agent(
        s, agent="governance", decide=governance_decide,
        snapshot=snap, verifier=verify_governance, quotation_id=42, actor_id=7,
    )
    row = s.added[0]
    assert row.agent == "governance"
    assert row.engine_version == "governance/1.1.0"
    assert row.quotation_id == 42
    assert row.actor_id == 7
    assert row.input_hash == decision.input_hash
    assert row.input_json == snap.model_dump(mode="json")
    assert row.output_json == decision.output
    assert row.verifier_verdict == "PASS"
    assert verdict is VerifierVerdict.PASS
    assert isinstance(row.latency_ms, int) and row.latency_ms >= 0


def test_row_is_written_even_when_the_verifier_fails():
    """A failing verdict must still be recorded — that IS the audit signal."""
    s = StubSession()

    def always_fail(_snap, _decision):
        return VerifierVerdict.FAIL, ["synthetic failure"]

    _d, verdict, reasons = run_agent(
        s, agent="governance", decide=governance_decide,
        snapshot=gov_snap(), verifier=always_fail,
    )
    assert len(s.added) == 1
    assert s.added[0].verifier_verdict == "FAIL"
    assert verdict is VerifierVerdict.FAIL
    assert reasons == ["synthetic failure"]


def test_missing_verifier_is_recorded_as_skipped_not_silently_passed():
    s = StubSession()
    _d, verdict, _r = run_agent(
        s, agent="governance", decide=governance_decide,
        snapshot=gov_snap(), verifier=None,
    )
    assert verdict is VerifierVerdict.SKIPPED
    assert s.added[0].verifier_verdict == "SKIPPED"


def test_logged_output_replays_to_the_same_decision():
    """§10.5 end to end: the logged input reproduces the logged output."""
    s = StubSession()
    snap = gov_snap()
    run_agent(s, agent="governance", decide=governance_decide,
              snapshot=snap, verifier=verify_governance)
    row = s.added[0]

    replayed = governance_decide(type(snap).model_validate(row.input_json))
    assert replayed.output == row.output_json
    assert replayed.input_hash == row.input_hash
