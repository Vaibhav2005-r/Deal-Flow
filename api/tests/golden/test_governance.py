"""BDRS golden cases — spec §10.1.

These values are the contract.  They run in well under 2s and are wired to the
pre-push hook: when someone edits a constant at hour 19, this is what saves the
demo.
"""

from decimal import Decimal as D

import pytest

from app.domain import governance
from app.domain.governance import decide
from app.domain.verifiers import verify_governance
from app.domain.types import VerifierVerdict
from tests.golden.conftest import line, snapshot


# --------------------------------------------------------------------------
# Case A — the brief's own example
# --------------------------------------------------------------------------

def case_a():
    return snapshot([
        line(1, "Laptop", "Hardware", "100000", "12", "15", "15", "30"),
        line(2, "Setup Service", "Service", "20000", "18", "20", "10", "14"),
    ])


def test_case_a_score_and_route():
    d = decide(case_a())
    assert d.output["score"] == 41.9
    assert d.output["approval_chain"] == ["SALES_MANAGER"]


def test_case_a_aggregates():
    agg = decide(case_a()).output["aggregates"]
    assert agg["worst"] == 8.0
    assert agg["leak_pct"] == 1.33
    assert agg["margin_short"] == 0.94


def test_case_a_components():
    c = decide(case_a()).output["components"]
    assert [c["worst_line"], c["blended_leak"],
            c["margin_shortfall"], c["context"]] == [32.0, 8.0, 1.9, 0.0]


def test_case_a_explanation_names_the_breaching_line():
    """§5.1 requires the explanation to name each breaching line and its
    contribution, in exactly this shape."""
    d = decide(case_a())
    assert (
        "Setup Service: 18% given vs 10% ceiling → 8.0pp over "
        "(contributes 32.0 of 40)"
    ) in d.explanation


# --------------------------------------------------------------------------
# Case B — death by a thousand cuts
# --------------------------------------------------------------------------

def case_b():
    spec = [("15", "17"), ("15", "18"), ("10", "12"), ("15", "18"), ("10", "12")]
    return snapshot([
        line(i, f"Line {i}", "Hardware", "40000", given, ceil, ceil, "18")
        for i, (ceil, given) in enumerate(spec, start=1)
    ])


def test_case_b_score_and_route():
    d = decide(case_b())
    assert d.output["score"] == 30.4
    assert d.output["approval_chain"] == ["SALES_MANAGER"]


def test_case_b_aggregates_and_components():
    o = decide(case_b()).output
    assert o["aggregates"]["worst"] == 3.0
    assert o["aggregates"]["leak_pct"] == 2.40
    assert o["aggregates"]["margin_short"] == 2.00
    c = o["components"]
    assert [c["worst_line"], c["blended_leak"],
            c["margin_shortfall"], c["context"]] == [12.0, 14.4, 4.0, 0.0]


def test_case_b_beats_the_naive_rule():
    """THE demo moment (§10.1).

    A naive "flag if any single line is >5pp over ceiling" rule passes this
    quote — the worst line is only 3pp over.  BDRS still routes it to a
    manager, because five small breaches blend into real leakage.
    Assert BOTH halves so the contrast cannot silently break.
    """
    snap = case_b()
    naive_flags = any(ln.excess_pct > D("5") for ln in snap.lines)
    assert naive_flags is False, "naive per-line rule should NOT flag Case B"

    d = decide(snap)
    assert d.output["approval_chain"] == ["SALES_MANAGER"], (
        "BDRS must catch what the naive rule misses"
    )


# --------------------------------------------------------------------------
# Case C — compliant
# --------------------------------------------------------------------------

def test_case_c_auto_approves():
    d = decide(snapshot([
        line(1, "Laptop", "Hardware", "100000", "10", "15", "15", "35"),
        line(2, "Support", "Service", "20000", "5", "10", "10", "40"),
    ]))
    assert d.output["score"] == 0.0
    assert d.output["approval_chain"] == []


def test_score_is_zero_iff_within_ceiling_and_above_floor():
    """Guaranteed property (§5.1): score == 0 iff every line is within its
    ceiling AND above its floor margin."""
    # within ceiling but BELOW floor margin -> must not be zero
    d = decide(snapshot([
        line(1, "Laptop", "Hardware", "100000", "10", "15", "15", "5"),
    ]))
    assert d.output["score"] > 0.0

    # over ceiling but healthy margin -> must not be zero
    d = decide(snapshot([
        line(1, "Laptop", "Hardware", "100000", "20", "15", "15", "50"),
    ]))
    assert d.output["score"] > 0.0


# --------------------------------------------------------------------------
# Case D — catastrophic line (hard stop)
# --------------------------------------------------------------------------

def case_d():
    return snapshot([
        line(1, "Enterprise Bundle", "Hardware", "50000", "40", "15", "15", "2"),
        line(2, "Standard Bundle", "Hardware", "50000", "5", "15", "15", "30"),
    ])


def test_case_d_score_route_and_hard_stop():
    o = decide(case_d()).output
    assert o["score"] == 83.9
    assert o["approval_chain"] == ["SALES_MANAGER", "FINANCE"]
    assert o["hard_stop"] is True, "worst excess 25pp > 15pp must hard-stop"
    assert o["aggregates"]["worst"] == 25.0
    assert o["aggregates"]["leak_pct"] == 12.50
    assert o["aggregates"]["margin_short"] == 6.97
    c = o["components"]
    assert [c["worst_line"], c["blended_leak"],
            c["margin_shortfall"], c["context"]] == [40.0, 30.0, 13.9, 0.0]


def test_hard_stop_overrides_a_low_score():
    """A single catastrophic line goes to Finance even when the blended score
    would otherwise auto-approve.

    Note the excess limb cannot produce this: `worst` is a max, not a weighted
    average, so ANY line over 15pp saturates c1 to 40 on its own.  The margin
    limb can, because margin_short IS net-weighted — a tiny line 15pp under
    its floor barely moves the score.
    """
    snap = snapshot([
        # within ceiling, but margin 5 < floor 20 - 10 -> hard stop
        line(1, "Tiny catastrophic line", "Hardware", "100", "0", "15", "15", "5"),
        line(2, "Huge clean line", "Hardware", "900000", "0", "15", "15", "60"),
    ])
    o = decide(snap).output
    assert o["score"] < 20.0, "blended score alone would auto-approve"
    assert o["hard_stop"] is True
    assert o["approval_chain"] == ["SALES_MANAGER", "FINANCE"]


def test_any_line_over_the_pp_limit_saturates_the_worst_component():
    """`worst = max(excess_i)` is deliberately NOT value-weighted: one line
    25pp over ceiling maxes c1 even when it is a rounding error of the order."""
    snap = snapshot([
        line(1, "Tiny", "Hardware", "100", "40", "15", "15", "30"),
        line(2, "Huge", "Hardware", "900000", "0", "15", "15", "60"),
    ])
    o = decide(snap).output
    assert o["components"]["worst_line"] == 40.0
    assert o["hard_stop"] is True
    assert o["approval_chain"] == ["SALES_MANAGER", "FINANCE"]


# --------------------------------------------------------------------------
# Case E — monotonicity
# --------------------------------------------------------------------------

def case_e(discount: int):
    """Two lines, ceiling 10 each, margins comfortably above floor.

    §10.1 fixes the endpoint (70.0 at 30%) but not the list values; equal
    50000 lines with the second at its ceiling reproduce it exactly.
    """
    return snapshot([
        line(1, "Swept", "Hardware", "50000", str(discount), "10", "10", "30"),
        line(2, "Fixed", "Hardware", "50000", "10", "10", "10", "30"),
    ])


def test_case_e_monotonic_and_endpoint():
    scores = [decide(case_e(d)).output["score"] for d in range(10, 31)]
    assert scores == sorted(scores), "score must never decrease as discount rises"
    assert scores[-1] == 70.0, "at 30% the score must reach 70.0"
    assert scores[0] == 0.0


def test_monotonicity_holds_when_margin_is_coupled_to_discount():
    """The §5.1 monotonicity guarantee, in the regime where it is true.

    In reality unit cost is fixed, so margin FALLS as discount rises.  Under
    that coupling the property holds across the whole sweep.
    """
    def coupled(disc: int):
        net = D(1) - D(disc) / D(100)
        margin = (D(1) - D("0.5") / net) * D(100)
        return snapshot([
            line(1, "Swept", "Hardware", "50000", str(disc), "10", "10",
                 str(round(margin, 4))),
            line(2, "Fixed", "Hardware", "50000", "0", "10", "10", "90"),
        ])

    scores = [decide(coupled(d)).output["score"] for d in range(0, 46)]
    assert scores == sorted(scores)


def test_monotonicity_is_NOT_guaranteed_for_independent_margin():
    """DOCUMENTED SPEC DEVIATION — do not "fix" this without reading §5.1.

    §5.1 claims score is monotonically non-decreasing in any line's discount.
    That is FALSE under §5.1's own formulas when ``margin_pct`` is supplied as
    an independent input, because ``margin_short`` is NET-WEIGHTED:

        margin_short = Σ(shortfall_i · net_i) / Σ net_i

    Raising line 1's discount shrinks net_1, which shifts weight AWAY from
    line 1.  If line 1 is the line carrying the shortfall, c3 falls — and when
    line 1 is inside its ceiling, c1 and c2 do not rise to compensate, so the
    total score falls.

    This test pins the counterexample so the false guarantee is not quietly
    relied upon.  Case E above is unaffected: its margins sit above the floor,
    so c3 is 0 throughout.
    """
    def independent(disc: int):
        return snapshot([
            # ceiling 60: the swept line stays WITHIN ceiling the whole sweep
            line(1, "Shortfall line", "Hardware", "50000", str(disc), "60", "60", "5"),
            line(2, "Healthy line", "Hardware", "50000", "0", "60", "60", "90"),
        ])

    scores = [decide(independent(d)).output["score"] for d in range(0, 61)]
    assert scores != sorted(scores), (
        "if this now passes, margin_short weighting changed — re-read §5.1"
    )
    assert scores[0] > scores[-1]


# --------------------------------------------------------------------------
# determinism + the verifier
# --------------------------------------------------------------------------

@pytest.mark.parametrize("build", [case_a, case_b, case_d])
def test_decisions_are_deterministic(build):
    a, b = decide(build()), decide(build())
    assert a.output == b.output
    assert a.input_hash == b.input_hash
    assert a.explanation == b.explanation


@pytest.mark.parametrize("build", [case_a, case_b, case_d])
def test_independent_verifier_agrees(build):
    snap = build()
    verdict, reasons = verify_governance(snap, decide(snap))
    assert verdict is VerifierVerdict.PASS, reasons


def test_verifier_catches_a_defaulted_ceiling():
    """§8: the verifier must notice a ceiling that was never looked up."""
    snap = case_a()
    tampered = snap.model_copy(update={
        "lines": [snap.lines[0].model_copy(update={"ceiling_source": ""}),
                  snap.lines[1]],
    })
    verdict, reasons = verify_governance(tampered, decide(tampered))
    assert verdict is VerifierVerdict.FAIL
    assert any("ceiling" in r for r in reasons)


def test_verifier_catches_a_tampered_score():
    snap = case_a()
    d = decide(snap)
    bogus = d.model_copy(update={"output": {**d.output, "score": 12.0}})
    verdict, reasons = verify_governance(snap, bogus)
    assert verdict is VerifierVerdict.FAIL
    assert any("score mismatch" in r for r in reasons)


def test_engine_version_is_pinned():
    """Replay (§10.5) depends on this string; bump it on ANY rule change."""
    assert governance.ENGINE_VERSION == "governance/1.0.0"
    assert decide(case_a()).engine_version == "governance/1.0.0"
