"""The demo-account endpoint that backs the sign-in screen's role buttons.

The buttons cannot hold credentials themselves: web/src is shipped and both
repositories are public, and tests/unit/test_no_seeded_credentials.py fails the
build when a seeded login appears there. So the server serves them from the one
copy in app/seed.py.

That makes the endpoint's boundary the thing worth pinning: it must offer only
accounts that still carry the seed hash, and the credentials it hands out must
be real ones -- a button that returns a wrong password is a broken demo, and a
button that returns a *non-seeded* account is a credential leak.
"""

from __future__ import annotations

import pytest

from app.api.security import hash_password
from app.models.enums import Role
from app.models.tables import User
from tests.spine.conftest import auth


ENDPOINT = "/api/auth/demo-accounts"


def test_offers_one_account_per_role(client):
    rows = client.get(ENDPOINT).json()
    assert {r["role"] for r in rows} == {"rep", "manager", "finance", "admin", "portal"}
    assert [r["label"] for r in rows] == [
        "Sales Rep", "Manager", "Finance", "Admin", "Customer",
    ]


@pytest.mark.parametrize(
    "role", ["rep", "manager", "finance", "admin", "portal"]
)
def test_every_offered_credential_actually_signs_in(client, role):
    """The button must work, and land in the scope it advertises."""
    row = next(r for r in client.get(ENDPOINT).json() if r["role"] == role)

    res = client.post(
        "/api/auth/login",
        json={"email": row["email"], "password": row["password"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["role"] == role
    assert body["scope"] == row["scope"]


def test_the_portal_account_is_scoped_to_the_portal(client):
    rows = client.get(ENDPOINT).json()
    scopes = {r["role"]: r["scope"] for r in rows}
    assert scopes["portal"] == "portal"
    assert set(scopes.values()) == {"internal", "portal"}


def test_a_real_account_is_never_offered(client, session):
    """The boundary.

    A signed-up account is hashed with pbkdf2, not the seed scheme, so it can
    never be published here -- not even when it is the only user of its role.
    This is what keeps the endpoint a fixtures list rather than a credential
    dump.
    """
    session.add(
        User(
            email="real.person@dealflow.example",
            full_name="Real Person",
            role=Role.MANAGER,
            password_hash=hash_password("a real password"),
        )
    )
    session.commit()

    emails = {r["email"] for r in client.get(ENDPOINT).json()}
    assert "real.person@dealflow.example" not in emails


def test_a_seeded_account_whose_password_changed_drops_out(client, session):
    """Verification, not derivation.

    The endpoint computes the candidate password from the seed's own rule and
    checks it against the stored hash. Rotate that account's password and it
    stops being offered, rather than being advertised with a stale value.
    """
    before = {r["role"] for r in client.get(ENDPOINT).json()}
    assert "admin" in before

    admin = session.scalars(
        session.query(User).where(User.role == Role.ADMIN).order_by(User.id).statement
    ).first()
    original = admin.password_hash
    admin.password_hash = hash_password("rotated")
    session.commit()
    try:
        assert "admin" not in {r["role"] for r in client.get(ENDPOINT).json()}
    finally:
        admin.password_hash = original
        session.commit()


def test_the_endpoint_needs_no_token(client):
    """It backs a sign-in screen, so it is reachable before signing in."""
    assert client.get(ENDPOINT).status_code == 200


def test_it_does_not_leak_anything_beyond_the_demo_fixtures(client):
    """Only the five fixture accounts, and only the fields the buttons need."""
    rows = client.get(ENDPOINT).json()
    assert len(rows) == 5
    for row in rows:
        assert set(row) == {"role", "label", "email", "password", "scope"}
        assert row["email"].endswith(".example")


def test_an_offered_account_still_obeys_its_role(client):
    """Signing in through a button grants that role's capabilities, no more.

    The buttons go through /api/auth/login like everything else, so there is
    no second, weaker path that skips the capability model.
    """
    row = next(r for r in client.get(ENDPOINT).json() if r["role"] == "rep")
    token = client.post(
        "/api/auth/login",
        json={"email": row["email"], "password": row["password"]},
    ).json()["token"]

    me = client.get("/api/me", headers=auth(token)).json()
    assert me["role"] == "rep"
    assert "view_approvals" not in me["capabilities"]
    assert "configure_discounts" not in me["capabilities"]
