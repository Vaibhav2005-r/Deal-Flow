"""THE architecture test.  Spec §3.

``app/domain/**`` may import only stdlib (minus ``datetime.now``, ``random``,
``os.environ``), ``pydantic`` and ``numpy``.  Time is injected as ``as_of``;
randomness is banned outright.

Written early on purpose: this is what keeps the domain pure at hour 19 when
somebody reaches for a database session inside a scoring function.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[2] / "app" / "domain"

ALLOWED_THIRD_PARTY = {"pydantic", "numpy"}

# stdlib modules that are banned outright rather than merely restricted
BANNED_MODULES = {
    "random",
    "secrets",
    "sqlalchemy",
    "fastapi",
    "starlette",
    "requests",
    "httpx",
    "alembic",
    "psycopg",
    "psycopg2",
    "pymysql",
    "MySQLdb",
    "sklearn",
    "mlxtend",
}

# attribute chains that smuggle in ambient state
BANNED_ATTRS = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
    ("date", "today"),
    ("time", "time"),
    ("os", "environ"),
    ("os", "getenv"),
}


def domain_files() -> list[Path]:
    return sorted(p for p in DOMAIN.rglob("*.py") if p.name != "__init__.py")


def test_domain_package_exists_and_is_non_empty():
    assert domain_files(), f"no domain modules found under {DOMAIN}"


@pytest.mark.parametrize("path", domain_files(), ids=lambda p: p.name)
def test_module_imports_are_pure(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    stdlib = sys.stdlib_module_names

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside the package
                continue
            names = [node.module or ""]
        else:
            continue

        for full in names:
            root = full.split(".")[0]
            assert root not in BANNED_MODULES, (
                f"{path.name} imports banned module {full!r} — "
                f"domain/ must stay pure (§3)"
            )
            if root == "app":
                assert full.startswith("app.domain"), (
                    f"{path.name} imports {full!r}; domain/ may only import "
                    f"from app.domain (§3)"
                )
                continue
            assert root in stdlib or root in ALLOWED_THIRD_PARTY, (
                f"{path.name} imports {full!r}, which is neither stdlib nor one "
                f"of {sorted(ALLOWED_THIRD_PARTY)} (§3)"
            )


@pytest.mark.parametrize("path", domain_files(), ids=lambda p: p.name)
def test_no_ambient_time_or_environment(path: Path):
    """No datetime.now(), no date.today(), no os.environ. Time is injected."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        value = node.value
        if isinstance(value, ast.Name):
            pair = (value.id, node.attr)
        elif isinstance(value, ast.Attribute):
            pair = (value.attr, node.attr)
        else:
            continue
        assert pair not in BANNED_ATTRS, (
            f"{path.name}:{node.lineno} uses {pair[0]}.{pair[1]} — "
            f"inject `as_of: date` instead (§3)"
        )


@pytest.mark.parametrize("path", domain_files(), ids=lambda p: p.name)
def test_no_bare_now_or_today_calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"now", "today", "utcnow"}, (
                f"{path.name}:{node.lineno} calls {node.func.id}() — "
                f"time must be injected (§3)"
            )
