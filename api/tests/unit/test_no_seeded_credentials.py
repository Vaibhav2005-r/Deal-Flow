"""No seeded login may appear in shipped frontend source.

Hardcoded demo credentials have been removed from this repository three times
and returned twice through merges — because they are genuinely convenient for
demoing, so they keep getting re-added in good faith.

Removing them again is not a fix; noticing automatically is. These are working
accounts and both repositories are public, so a credential committed here is
published the moment it is pushed, and deleting it later does not un-publish
it. This fails the build instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "web" / "src"

#: The seeded accounts, from app/seed.py. Any of these appearing in shipped
#: frontend source means a real login is being rendered into a public page.
SEEDED_LOGINS = re.compile(
    r"(priya\.raghavan|daniel\.okafor|sofia\.marchetti|james\.whitfield"
    r"|aisha\.karim|root@dealflow|portal\d+@)",
    re.IGNORECASE,
)

#: Shapes that hold a credential even without a seeded address in them.
CREDENTIAL_SHAPES = re.compile(
    r"(DEMO_CREDENTIALS|DEMO_PORTAL_USERS|demoPassword|const\s+\w*PASSWORD\w*\s*=)",
)


def sources() -> list[Path]:
    return sorted(p for p in WEB.rglob("*.ts*") if "node_modules" not in p.parts)


def test_there_are_sources_to_check():
    assert sources(), f"no frontend sources under {WEB}"


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.name)
def test_no_seeded_login_in_frontend_source(path: Path):
    hits = [
        f"{path.name}:{i}: {line.strip()[:90]}"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if SEEDED_LOGINS.search(line)
    ]
    assert not hits, (
        "a seeded login appears in shipped frontend source — these are working "
        "accounts and the repositories are public:\n  " + "\n  ".join(hits)
    )


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.name)
def test_no_credential_map_in_frontend_source(path: Path):
    hits = [
        f"{path.name}:{i}: {line.strip()[:90]}"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if CREDENTIAL_SHAPES.search(line)
    ]
    assert not hits, (
        "a credential map is defined in frontend source:\n  " + "\n  ".join(hits)
    )
