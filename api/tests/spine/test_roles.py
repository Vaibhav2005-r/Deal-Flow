"""Role capabilities and self-service registration.  Spec §3.

The approval chain is the product. Anything that lets a user grant themselves
an approver role defeats it, so registration and capability boundaries are
pinned here.
"""

from __future__ import annotations

import pytest

from app.domain.capabilities import BY_ROLE, Capability, for_role
from tests.spine.conftest import auth, login


# --------------------------------------------------------------------------
# self-service registration cannot grant privilege
# --------------------------------------------------------------------------


@pytest.mark.parametrize("claimed", ["manager", "finance", "admin", "portal"])
@pytest.mark.parametrize("endpoint", ["/api/auth/register", "/api/auth/signup"])
def test_registration_ignores_a_claimed_role(client, claimed, endpoint):
    """REGRESSION — this was exploitable.

    /api/auth/register honoured `role` from the request body, so a public
    POST of {"role": "admin"} returned a token with all 19 capabilities:
    approve your own over-ceiling quotes, rewrite the discount policy, record
    payments, manage the catalog. Every self-service account is a rep.
    """
    suffix = claimed + endpoint.rsplit("/", 1)[-1]
    res = client.post(endpoint, json={
        "email": f"escalate-{suffix}@example.test",
        "password": "a-long-enough-password",
        "full_name": "Escalation Attempt",
        "role": claimed,
    })
    assert res.status_code in (200, 201), res.text
    assert res.json()["role"] == "rep", f"{endpoint} granted '{claimed}'"

    me = client.get("/api/me", headers=auth(res.json()["token"])).json()
    assert me["role"] == "rep"
    for forbidden in (
        Capability.APPROVE_MANAGER_STEP, Capability.APPROVE_FINANCE_STEP,
        Capability.CONFIGURE_DISCOUNTS, Capability.RECORD_PAYMENT,
        Capability.MANAGE_CATALOG,
    ):
        assert str(forbidden) not in me["capabilities"]


def test_a_self_registered_user_cannot_approve(client):
    """The capability list is advisory to the UI; the endpoint guard is real."""
    res = client.post("/api/auth/register", json={
        "email": "cannot-approve@example.test", "password": "a-long-password",
        "full_name": "No Approver", "role": "manager",
    })
    token = res.json()["token"]
    assert client.put("/api/admin/discount-config", headers=auth(token), json={
        "tier_ceilings": [{"tier": "gold", "ceiling_pct": "99"}],
        "category_ceilings": [],
    }).status_code == 403


# --------------------------------------------------------------------------
# capability boundaries
# --------------------------------------------------------------------------


def test_every_role_reports_its_capabilities(client):
    for email, expected in [
        ("priya.raghavan@dealflow.example", "rep"),
        ("james.whitfield@dealflow.example", "manager"),
        ("aisha.karim@dealflow.example", "finance"),
        ("root@dealflow.example", "admin"),
    ]:
        me = client.get("/api/me", headers=auth(login(client, email)["token"])).json()
        assert me["role"] == expected
        assert set(me["capabilities"]) == {str(c) for c in for_role(expected)}


def test_a_rep_can_never_approve_their_own_work(client):
    """§3 separates building from approving; a rep who could approve would be
    signing off their own discounts."""
    caps = for_role("rep")
    assert Capability.BUILD_QUOTE in caps
    assert Capability.APPROVE_MANAGER_STEP not in caps
    assert Capability.APPROVE_FINANCE_STEP not in caps


def test_finance_reviews_rather_than_sells(client):
    caps = for_role("finance")
    assert Capability.APPROVE_FINANCE_STEP in caps
    assert Capability.RECORD_PAYMENT in caps
    assert Capability.BUILD_QUOTE not in caps


def test_a_customer_sees_only_their_own_portal(client):
    caps = for_role("portal")
    assert caps == {
        Capability.PORTAL_VIEW_QUOTES, Capability.PORTAL_NEGOTIATE,
        Capability.PORTAL_CONFIRM, Capability.PORTAL_VIEW_PROFILE,
    }
    assert not any(str(c).startswith("view_reports") for c in caps)


def test_an_unknown_role_gets_nothing(client):
    """Fail closed. A typo in a role must not open the system."""
    assert for_role("superuser") == frozenset()
    assert for_role("") == frozenset()


def test_portal_identity_names_its_customer(client):
    me = client.get("/api/me", headers=auth(
        login(client, "portal1@northwind.example",
              "Northwind Logistics Pvt Ltd")["token"])).json()
    assert me["scope"] == "portal"
    assert me["customer"]["name"] == "Northwind Logistics Pvt Ltd"


def test_every_defined_role_has_a_capability_set():
    for role in ("rep", "manager", "finance", "admin", "portal"):
        assert BY_ROLE[role], f"{role} has no capabilities"
