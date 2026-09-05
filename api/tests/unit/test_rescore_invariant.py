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
SANCTIONED = {"quote_lines.py"}  # the one module allowed to mutate lines

MUTABLE_LINE_FIELDS = {
    "qty",
    "unit_price",
    "discount_pct",
    "ceiling_pct_applied",
    "margin_pct",
    "is_recurring",
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
                and target.attr in MUTABLE_LINE_FIELDS
                and isinstance(target.value, ast.Name)
                and "line" in target.value.id.lower()
            ):
                pytest.fail(
                    f"{path.name}:{node.lineno} assigns {target.value.id}."
                    f"{target.attr} directly — go through mutate_lines (§7)"
                )


def test_the_sanctioned_module_actually_implements_the_three_steps():
    """void approvals -> re-run governance -> transition to RISK_SCORED."""
    src = (APP / "services" / "quote_lines.py").read_text(encoding="utf-8")
    assert "VOIDED_BY_EDIT" in src
    assert "governance_decide" in src
    assert "QuoteState.RISK_SCORED" in src


def test_rescore_states_match_the_spec():
    from app.models.enums import QuoteState, REQUIRES_RESCORE_ON_EDIT

    assert REQUIRES_RESCORE_ON_EDIT == {
        QuoteState.READY_TO_FULFILL,
        QuoteState.SENT,
        QuoteState.UNDER_NEGOTIATION,
    }
