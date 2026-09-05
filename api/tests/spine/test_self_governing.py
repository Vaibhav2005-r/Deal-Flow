"""§7's invariant and §8's failure containment, over real HTTP.

The self-governing claim is: you cannot edit an approved quote without it
re-entering the approval chain. §13 lists bypassing this as an anti-pattern
and §7 says the claim is false if it can be bypassed — so it is tested through
the router, not just at the service boundary.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models.tables import ApprovalRequest, DecisionLog
from tests.spine.conftest import auth
from tests.spine.test_spine import _gold_customer, _product, build_over_ceiling_quote


def approved_quote(client, rep, manager) -> dict:
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    res = client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"]))
    assert res.json()["state"] == "READY_TO_FULFILL"
    return res.json()


def test_editing_an_approved_quote_voids_approvals_and_rescores(
    client, rep, manager, session
):
    quote = approved_quote(client, rep, manager)
    line = next(ln for ln in quote["lines"] if ln["breaches_ceiling"])

    res = client.patch(
        f"/api/quotes/{quote['id']}/lines/{line['id']}",
        headers=auth(rep["token"]),
        json={"discount_pct": "30"},   # deepen the breach
    )
    assert res.status_code == 200, res.text
    updated = res.json()

    # 1. it left READY_TO_FULFILL and re-entered the chain
    assert updated["state"] in ("PENDING_MANAGER", "PENDING_FINANCE")

    # 2. the earlier approval was voided, not left standing
    session.expire_all()
    decisions = [
        s.decision
        for s in session.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.quotation_id == quote["id"])
            .order_by(ApprovalRequest.id)
        ).all()
    ]
    assert "VOIDED_BY_EDIT" in [str(d) for d in decisions]

    # 3. there is now a fresh PENDING step
    assert any(s["decision"] == "PENDING" for s in updated["approval_steps"])


def test_the_rescore_actually_reran_governance(client, rep, manager, session):
    quote = approved_quote(client, rep, manager)
    line = next(ln for ln in quote["lines"] if ln["breaches_ceiling"])

    before = len(session.scalars(
        select(DecisionLog).where(DecisionLog.quotation_id == quote["id"])
    ).all())

    client.patch(f"/api/quotes/{quote['id']}/lines/{line['id']}",
                 headers=auth(rep["token"]), json={"discount_pct": "30"})

    session.expire_all()
    after = session.scalars(
        select(DecisionLog).where(DecisionLog.quotation_id == quote["id"])
    ).all()
    assert len(after) == before + 1, "the edit must produce a new governance call"
    assert after[-1].output_json["score"] > after[0].output_json["score"]


def test_adding_a_line_to_an_approved_quote_also_rescores(client, rep, manager):
    quote = approved_quote(client, rep, manager)
    audit = _product(client, rep["token"], "SV-AUD-01")

    res = client.post(
        f"/api/quotes/{quote['id']}/lines",
        headers=auth(rep["token"]),
        json={"product_id": audit["id"], "qty": 1, "discount_pct": "25"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["state"] in ("PENDING_MANAGER", "PENDING_FINANCE")
    assert len(res.json()["lines"]) == 3


def test_removing_a_line_from_an_approved_quote_also_rescores(client, rep, manager):
    quote = approved_quote(client, rep, manager)
    line = next(ln for ln in quote["lines"] if ln["breaches_ceiling"])

    res = client.delete(f"/api/quotes/{quote['id']}/lines/{line['id']}",
                        headers=auth(rep["token"]))
    assert res.status_code == 200, res.text
    # removing the ONLY breaching line should clear the chain entirely
    assert res.json()["state"] == "READY_TO_FULFILL"
    assert len(res.json()["lines"]) == 1


def test_a_softened_edit_can_drop_the_quote_out_of_the_chain(client, rep, manager):
    """Re-scoring is symmetric: it can relax as well as escalate."""
    quote = approved_quote(client, rep, manager)
    line = next(ln for ln in quote["lines"] if ln["breaches_ceiling"])

    res = client.patch(f"/api/quotes/{quote['id']}/lines/{line['id']}",
                       headers=auth(rep["token"]),
                       json={"discount_pct": "5"})  # now inside the ceiling
    assert res.json()["state"] == "READY_TO_FULFILL"
    assert res.json()["approval_steps"][-1]["decision"] in ("VOIDED_BY_EDIT", "APPROVED")


# --------------------------------------------------------------------------
# §8 failure containment
# --------------------------------------------------------------------------


def test_optimistic_concurrency_returns_409(client, rep, manager):
    quote = approved_quote(client, rep, manager)
    line = quote["lines"][0]
    stale_version = quote["version"] - 1

    res = client.patch(
        f"/api/quotes/{quote['id']}/lines/{line['id']}?expected_version={stale_version}",
        headers=auth(rep["token"]), json={"discount_pct": "9"},
    )
    assert res.status_code == 409
    assert res.json()["error"] == "ConcurrencyError"


def test_version_increments_on_every_line_mutation(client, rep, manager):
    quote = approved_quote(client, rep, manager)
    line = quote["lines"][0]
    v0 = quote["version"]

    res = client.patch(f"/api/quotes/{quote['id']}/lines/{line['id']}",
                       headers=auth(rep["token"]), json={"qty": 3})
    assert res.json()["version"] == v0 + 1


def test_idempotent_confirm_does_not_score_twice(client, rep, session):
    """A double-clicked confirm must return the ORIGINAL response (§8)."""
    quote = build_over_ceiling_quote(client, rep)
    headers = {**auth(rep["token"]), "Idempotency-Key": f"confirm-{quote['id']}"}

    first = client.post(f"/api/quotes/{quote['id']}/confirm", headers=headers)
    second = client.post(f"/api/quotes/{quote['id']}/confirm", headers=headers)

    assert first.status_code == second.status_code == 200
    assert second.headers.get("Idempotent-Replay") == "true"
    assert first.json() == second.json()

    session.expire_all()
    rows = session.scalars(
        select(DecisionLog).where(DecisionLog.quotation_id == quote["id"])
    ).all()
    assert len(rows) == 1, "the replay must not have re-run governance"


def test_idempotent_approve_does_not_double_advance(client, rep, manager):
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    headers = {**auth(manager["token"]), "Idempotency-Key": f"approve-{quote['id']}"}

    first = client.post(f"/api/quotes/{quote['id']}/approve", headers=headers)
    second = client.post(f"/api/quotes/{quote['id']}/approve", headers=headers)

    assert first.json()["state"] == "READY_TO_FULFILL"
    assert second.headers.get("Idempotent-Replay") == "true"
    assert first.json() == second.json()


def test_outbox_rows_are_written_with_the_state_change(client, rep, manager, session):
    from app.models.tables import Outbox

    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(manager["token"]))

    session.expire_all()
    topics = [
        r.topic for r in session.scalars(select(Outbox)).all()
        if r.payload.get("quotation_id") == quote["id"]
    ]
    assert "quotation.confirm" in topics
    assert "quotation.approve" in topics


# --------------------------------------------------------------------------
# scope separation (§1 constraint 2)
# --------------------------------------------------------------------------


def test_portal_token_cannot_reach_internal_routes(client):
    portal = client.post("/api/auth/login", json={
        "email": "portal1@northwind.example",
        "password": "Northwind Logistics Pvt Ltd",
    })
    assert portal.status_code == 200, portal.text
    assert portal.json()["scope"] == "portal"

    res = client.get("/api/quotes", headers=auth(portal.json()["token"]))
    assert res.status_code == 403
    assert "internal scope required" in res.json()["detail"]


def test_a_rep_cannot_approve_their_own_quote(client, rep):
    quote = build_over_ceiling_quote(client, rep)
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(rep["token"]))
    res = client.post(f"/api/quotes/{quote['id']}/approve", headers=auth(rep["token"]))
    assert res.status_code == 403


def test_unsigned_token_is_rejected(client):
    res = client.get("/api/quotes", headers={"Authorization": "Bearer forged.deadbeef"})
    assert res.status_code == 401


# --------------------------------------------------------------------------
# regressions found by driving the real UI
# --------------------------------------------------------------------------


def test_adding_a_line_to_a_draft_does_not_score_it(client, rep):
    """§7: DRAFT leaves DRAFT only via `confirm`.

    Regression — `mutate_lines` used to re-score unconditionally, so adding a
    line in the quote builder silently pushed a DRAFT into PENDING_MANAGER
    before the rep ever pressed Confirm.
    """
    token = rep["token"]
    customer = _gold_customer(client, token)
    setup = _product(client, token, "SV-INST-01")

    quote = client.post("/api/quotes", headers=auth(token),
                        json={"customer_id": customer["id"], "lines": []}).json()
    assert quote["state"] == "DRAFT"

    res = client.post(f"/api/quotes/{quote['id']}/lines", headers=auth(token),
                      json={"product_id": setup["id"], "qty": 1, "discount_pct": "18"})
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "DRAFT", "adding a line must not score a draft"
    assert res.json()["approval_steps"] == []
    assert res.json()["risk_score"] is None

    # …and confirming still works normally afterwards
    score = client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token)).json()
    assert score["state"] == "PENDING_MANAGER"
    assert score["score"] == 62.0


def test_editing_a_quote_awaiting_approval_rescores_it(client, rep):
    """A mid-chain edit must not leave a pending approver looking at stale
    terms. Widens §7's three named states to cover PENDING_* as well."""
    token = rep["token"]
    customer = _gold_customer(client, token)
    setup = _product(client, token, "SV-INST-01")

    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": setup["id"], "qty": 1, "discount_pct": "18"}],
    }).json()
    confirmed = client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token)).json()
    assert confirmed["state"] == "PENDING_MANAGER"

    line_id = client.get(f"/api/quotes/{quote['id']}", headers=auth(token)).json()["lines"][0]["id"]
    res = client.patch(f"/api/quotes/{quote['id']}/lines/{line_id}",
                       headers=auth(token), json={"discount_pct": "5"})
    assert res.status_code == 200, res.text

    # now inside the ceiling -> the chain must be gone, not stale-pending
    assert res.json()["state"] == "READY_TO_FULFILL"
    assert "VOIDED_BY_EDIT" in [s["decision"] for s in res.json()["approval_steps"]]
