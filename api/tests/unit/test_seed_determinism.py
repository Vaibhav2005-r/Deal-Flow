"""`make seed` must be reproducible.

CLAUDE.md §2 calls the seed "idempotent, drops and rebuilds", and §12 requires
seed data a demo can rely on. If the same seed produces a different database
each run, `make demo-reset` is not a reset — it is a reroll, and the golden
demo drifts under you.

REGRESSION: `last_activity_at` on the two demo quotations was left to its
column server_default, i.e. wall-clock `now()`. It went unnoticed because
earlier determinism checks fingerprinted only the commercial columns. It is
not a cosmetic field — it is the input to the stalled detector (§5.5).
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import seed
from app.models.tables import (
    ApprovalRequest,
    ProductAffinity,
    Quotation,
    QuoteLine,
    Stock,
)


def fingerprint(url: str) -> dict[str, str]:
    """Hash every table whose content a demo depends on — timestamps included."""
    engine = create_engine(url, future=True)
    with Session(engine) as s:
        parts = {
            "quotations": s.execute(
                select(
                    Quotation.id, Quotation.state,
                    Quotation.last_activity_at, Quotation.risk_score,
                ).order_by(Quotation.id)
            ).all(),
            "lines": s.execute(
                select(
                    QuoteLine.quotation_id, QuoteLine.product_id, QuoteLine.qty,
                    QuoteLine.discount_pct, QuoteLine.margin_pct,
                ).order_by(QuoteLine.id)
            ).all(),
            "approvals": s.execute(
                select(
                    ApprovalRequest.quotation_id, ApprovalRequest.approver_role,
                    ApprovalRequest.decision,
                ).order_by(ApprovalRequest.id)
            ).all(),
            "affinity": s.execute(
                select(
                    ProductAffinity.antecedent_id, ProductAffinity.consequent_id,
                    ProductAffinity.lift,
                ).order_by(ProductAffinity.id)
            ).all(),
            "stock": s.execute(
                select(Stock.warehouse_id, Stock.product_id, Stock.qty_on_hand)
                .order_by(Stock.id)
            ).all(),
        }
    return {
        k: hashlib.sha256(str(v).encode()).hexdigest() for k, v in parts.items()
    }


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory) -> tuple[dict, dict]:
    base = tmp_path_factory.mktemp("determinism")
    a, b = f"sqlite:///{base/'a.db'}", f"sqlite:///{base/'b.db'}"
    seed.run(a)
    seed.run(b)
    return fingerprint(a), fingerprint(b)


@pytest.mark.parametrize(
    "table", ["quotations", "lines", "approvals", "affinity", "stock"]
)
def test_two_seed_runs_are_identical(two_runs, table):
    first, second = two_runs
    assert first[table] == second[table], (
        f"{table} differs between two seed runs — the seed is not reproducible"
    )


def test_last_activity_is_never_wall_clock(two_runs):
    """The specific column that regressed. Named separately so a failure points
    straight at the cause rather than at 'quotations differ'."""
    first, second = two_runs
    assert first["quotations"] == second["quotations"]


def test_no_quotation_relies_on_the_server_default_timestamp():
    """Structural: every Quotation the seed builds sets last_activity_at."""
    import ast
    from pathlib import Path

    src = Path(seed.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    missing = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Quotation"
        and "last_activity_at" not in {kw.arg for kw in node.keywords}
    ]
    assert not missing, (
        f"Quotation constructed without last_activity_at at line(s) {missing} — "
        f"it would fall back to wall-clock now() and break seed reproducibility"
    )
