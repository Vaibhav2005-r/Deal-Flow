"""§7's self-governing claim, enforced structurally.

"Implement this as a single service function that EVERY line-mutating path
calls. There must be no code path that edits a line without going through it."

A claim like that decays the moment someone adds a router in a hurry, so it is
asserted here by walking the AST rather than trusted to review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
#: The one module allowed to mutate lines on a live quotation, plus seed.py —
#: a standalone bulk-fixture script that builds historical PAID orders and one
#: DRAFT demo quote. It never touches a quotation inside the approval flow and
#: is not reachable from a request path.
SANCTIONED = {"quote_lines.py", "seed.py"}

#: COMMERCIAL fields: changing any of these changes the score, so every edit
#: must void approvals and re-score (§7).
COMMERCIAL_LINE_FIELDS = {
    "qty",
    "unit_price",
    "discount_pct",
    "is_recurring",
}

#: DERIVED fields: outputs the scoring path writes back after it runs (§6).
#: These are deliberately NOT guarded — they are results of a re-score, not
#: inputs to one, and routing a scoring result back through mutate_lines would
#: recurse forever.
DERIVED_LINE_FIELDS = {
    "ceiling_pct_applied",
    "margin_pct",
}


def app_modules() -> list[Path]:
    return sorted(
        p
        for p in APP.rglob("*.py")
        if p.name != "__init__.py"
        and "domain" not in p.parts
        and "models" not in p.parts
    )


def test_there_are_modules_to_check():
    assert app_modules()


@pytest.mark.parametrize("path", app_modules(), ids=lambda p: p.name)
def test_only_the_sanctioned_module_constructs_or_deletes_quote_lines(path: Path):
    if path.name in SANCTIONED:
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        # QuoteLine(...) construction
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "QuoteLine", (
                f"{path.name}:{node.lineno} constructs QuoteLine directly — "
                f"route line mutations through services/quote_lines.mutate_lines (§7)"
            )
        # session.delete(<something>) on a line
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "delete"
            and node.args
        ):
            src = ast.dump(node.args[0])
            assert "QuoteLine" not in src and "quote_line" not in src, (
                f"{path.name}:{node.lineno} deletes a quote line outside the "
                f"sanctioned path (§7)"
            )


@pytest.mark.parametrize("path", app_modules(), ids=lambda p: p.name)
def test_no_module_assigns_quote_line_fields_directly(path: Path):
    if path.name in SANCTIONED:
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr in COMMERCIAL_LINE_FIELDS
                and isinstance(target.value, ast.Name)
                and "line" in target.value.id.lower()
            ):
                pytest.fail(
                    f"{path.name}:{node.lineno} assigns {target.value.id}."
                    f"{target.attr} directly — go through mutate_lines (§7)"
                )


def test_the_two_field_sets_are_disjoint():
    """A field must be classified as one or the other, never both — otherwise
    the guard above has a hole."""
    assert not (COMMERCIAL_LINE_FIELDS & DERIVED_LINE_FIELDS)


def test_every_guarded_field_actually_feeds_the_score():
    """The guard is only meaningful if each commercial field really moves the
    BDRS input — otherwise we are protecting a field nobody scores."""
    from app.domain.types import LineSnapshot

    fields = set(LineSnapshot.model_fields)
    assert {"discount_pct", "list_value", "is_recurring"} <= fields
    # qty and unit_price reach the snapshot multiplied together as list_value
    assert "list_value" in fields


def test_the_sanctioned_module_actually_implements_the_three_steps():
    """void approvals -> re-run governance -> transition to RISK_SCORED.

    Step 2 is delegated to services/scoring.py so that the confirm route and
    the edit path share ONE scoring implementation, so the assertion follows
    the delegation rather than demanding it be inlined here.
    """
    src = (APP / "services" / "quote_lines.py").read_text(encoding="utf-8")
    scoring = (APP / "services" / "scoring.py").read_text(encoding="utf-8")

    assert "VOIDED_BY_EDIT" in src, "step 1: approvals must be voided"
    assert "score_quotation" in src, "step 2: governance must be re-run"
    assert "governance_decide" in scoring
    assert "QuoteState.RISK_SCORED" in scoring, "step 3: must re-enter at RISK_SCORED"


def test_voiding_covers_approved_rows_not_just_pending_ones():
    """An APPROVED step grants authority over terms that an edit has just
    changed. Leaving it standing is how an edited quote looks approved against
    a score nobody computed."""
    from app.models.enums import ApprovalDecision
    from app.services.quote_lines import LIVE_AUTHORITY

    assert ApprovalDecision.PENDING in LIVE_AUTHORITY
    assert ApprovalDecision.APPROVED in LIVE_AUTHORITY
    # closed cycles are history and must never be rewritten
    assert ApprovalDecision.REJECTED not in LIVE_AUTHORITY
    assert ApprovalDecision.VOIDED_BY_EDIT not in LIVE_AUTHORITY


def test_mutate_lines_flushes_before_it_rebuilds_the_snapshot():
    """The session runs autoflush=False, so an unflushed add/delete would make
    the re-score read the quote as it was BEFORE the edit."""
    import inspect

    from app.services import quote_lines

    src = inspect.getsource(quote_lines.mutate_lines)
    flush_at = src.index("session.flush()")
    snapshot_at = src.index("build_snapshot(quotation)")
    assert flush_at < snapshot_at, "must flush before building the snapshot"


def test_rescore_states_cover_the_spec_and_close_the_midchain_hole():
    """§7 names three states; we cover those plus the two mid-chain PENDING_*
    ones, so an edit cannot leave a pending approver looking at stale terms.
    The set must WIDEN §7, never narrow it — and must never include DRAFT."""
    from app.models.enums import QuoteState, REQUIRES_RESCORE_ON_EDIT

    spec_named = {
        QuoteState.READY_TO_FULFILL,
        QuoteState.SENT,
        QuoteState.UNDER_NEGOTIATION,
    }
    assert spec_named <= REQUIRES_RESCORE_ON_EDIT, "must not narrow §7"
    assert QuoteState.PENDING_MANAGER in REQUIRES_RESCORE_ON_EDIT
    assert QuoteState.PENDING_FINANCE in REQUIRES_RESCORE_ON_EDIT
    assert QuoteState.DRAFT not in REQUIRES_RESCORE_ON_EDIT, (
        "a DRAFT has no approvals to void; §7 says it leaves DRAFT only via confirm"
    )


def test_void_approvals_flushes_before_returning():
    """Regression: without the flush, the re-score's stale-PENDING cleanup
    deleted the rows void_approvals had just marked VOIDED_BY_EDIT."""
    import inspect

    from app.services import quote_lines

    src = inspect.getsource(quote_lines.void_approvals)
    assert "session.flush()" in src
