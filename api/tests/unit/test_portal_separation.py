"""§1 constraint 2 / §13 anti-pattern.

"The customer portal is a genuinely separate, restricted view. Different auth
scope, different router, different components. Not the internal screen with a
flag."

The cheapest way for that to quietly become false is one convenient import
from src/portal into src/internal. This test makes that a build failure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "web" / "src"
PORTAL, INTERNAL = WEB / "portal", WEB / "internal"

IMPORT = re.compile(r"""(?:from|import)\s+['"]([^'"]+)['"]""")


def sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.ts*")) if root.exists() else []


def test_both_trees_exist():
    assert sources(PORTAL), f"no portal sources under {PORTAL}"
    assert sources(INTERNAL), f"no internal sources under {INTERNAL}"


@pytest.mark.parametrize("path", sources(PORTAL), ids=lambda p: p.name)
def test_portal_never_imports_from_internal(path: Path):
    for spec in IMPORT.findall(path.read_text(encoding="utf-8")):
        assert "internal" not in spec, (
            f"web/src/portal/{path.name} imports {spec!r} from the internal "
            f"tree — the portal must be a separate view (§1)"
        )


@pytest.mark.parametrize("path", sources(INTERNAL), ids=lambda p: p.name)
def test_internal_never_imports_from_portal(path: Path):
    for spec in IMPORT.findall(path.read_text(encoding="utf-8")):
        assert "portal" not in spec, (
            f"web/src/internal/{path.name} imports {spec!r} from the portal "
            f"tree — keep the trees separate (§1)"
        )


def test_the_two_scopes_are_distinct_and_not_interchangeable():
    auth = (WEB / "lib" / "auth.ts").read_text(encoding="utf-8")
    assert '"internal"' in auth and '"portal"' in auth
    assert "df360.internal.token" in auth
    assert "df360.portal.token" in auth, "portal must not reuse the internal token"


def test_portal_guard_does_not_accept_an_internal_session():
    """A `?portal=true` style flag on the internal guard is the anti-pattern."""
    portal = (PORTAL / "router.tsx").read_text(encoding="utf-8")
    assert 'hasScope("portal")' in portal
    assert 'hasScope("internal")' not in portal
