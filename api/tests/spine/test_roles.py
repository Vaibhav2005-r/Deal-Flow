"""Role capabilities and self-service registration.  Spec §3.

The approval chain is the product. Anything that lets a user grant themselves
an approver role defeats it, so registration and capability boundaries are
pinned here.
"""

from __future__ import annotations

import pytest

from app.domain.capabilities import BY_ROLE, Capability, for_role
from app.settings import settings
from tests.spine.conftest import auth, login


# --------------------------------------------------------------------------
# self-service registration cannot grant privilege
# --------------------------------------------------------------------------


@pytest.mark.parametrize("claimed", ["manager", "finance", "admin", "portal"])
@pytest.mark.parametrize("endpoint", ["/api/auth/register", "/api/auth/signup"])
def test_a_claimed_role_is_ignored_when_demo_mode_is_off(
    client, monkeypatch, claimed, endpoint
):
    """REGRESSION — this was exploitable, and this is the setting that closes it.

    /api/auth/register honoured `role` from the request body, so a public POST
    of {"role": "admin"} returned a token with all 19 capabilities: approve
    your own over-ceiling quotes, rewrite the discount policy, record payments,
    manage the catalog.

    The sign-up form now offers a role picker, which is a demo affordance. With
    `demo_accounts_enabled` off — what a real deployment runs — the claim is
    ignored again and every self-service account is a rep.
    """
    monkeypatch.setattr(settings, "demo_accounts_enabled", False)

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


@pytest.mark.parametrize("claimed", ["rep", "manager", "finance", "admin"])
@pytest.mark.parametrize("endpoint", ["/api/auth/register", "/api/auth/signup"])
def test_the_role_picker_is_honoured_in_demo_mode(client, claimed, endpoint):
    """The feature: sign-up grants the role the form asked for.

    This is the demo build's behaviour, so a reviewer can reach each workspace
    without an admin provisioning accounts first.
    """
    assert settings.demo_accounts_enabled, "these tests assume the demo default"

    suffix = claimed + endpoint.rsplit("/", 1)[-1]
    res = client.post(endpoint, json={
        "email": f"picker-{suffix}@example.test",
        "password": "a-long-enough-password",
        "full_name": "Role Picker",
        "role": claimed,
    })
    assert res.status_code in (200, 201), res.text
    assert res.json()["role"] == claimed

    me = client.get("/api/me", headers=auth(res.json()["token"])).json()
    assert me["role"] == claimed
    assert set(me["capabilities"]) == {str(c) for c in for_role(claimed)}


@pytest.mark.parametrize("endpoint", ["/api/auth/register", "/api/auth/signup"])
def test_the_picker_cannot_claim_the_portal_role(client, endpoint):
    """Portal is not selectable, in either mode.

    A customer login without the customer row that /auth/portal-signup creates
    alongside it would sign in and then fail on every portal screen, so it is
    refused rather than quietly downgraded.
    """
    res = client.post(endpoint, json={
        "email": f"portal-claim-{endpoint.rsplit('/', 1)[-1]}@example.test",
        "password": "a-long-enough-password",
        "full_name": "Portal Claim",
        "role": "portal",
    })
    assert res.status_code == 400, res.text
    assert "portal" in res.text


@pytest.mark.parametrize("endpoint", ["/api/auth/register", "/api/auth/signup"])
def test_an_unknown_role_is_refused_rather_than_defaulted(client, endpoint):
    """A typo must not silently become a rep — that hides a broken form."""
    res = client.post(endpoint, json={
        "email": f"typo-{endpoint.rsplit('/', 1)[-1]}@example.test",
        "password": "a-long-enough-password",
        "full_name": "Typo",
        "role": "manger",
    })
    assert res.status_code == 400, res.text


def test_a_self_registered_rep_cannot_approve(client):
    """The capability list is advisory to the UI; the endpoint guard is real."""
    res = client.post("/api/auth/register", json={
        "email": "cannot-approve@example.test", "password": "a-long-password",
        "full_name": "No Approver", "role": "rep",
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
