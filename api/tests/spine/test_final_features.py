"""The last brief requirements: §A2 general info, §A4/A5 setup, §B3 order
discount."""

from __future__ import annotations

from decimal import Decimal

from tests.spine.conftest import auth
from tests.spine.test_spine import _gold_customer, _product


# --------------------------------------------------------------------------
# §A2 — product general info
# --------------------------------------------------------------------------


def test_every_product_carries_unit_tax_and_description(client, rep):
    rows = client.get("/api/catalog/products", headers=auth(rep["token"])).json()
    assert rows
    for r in rows[:8]:
        d = client.get(
            f"/api/catalog/products/{r['id']}", headers=auth(rep["token"])
        ).json()
        assert d["unit"], f"{d['sku']} has no sales unit"
        assert Decimal(d["tax_pct"]) >= 0
        assert d["description"] and d["sku"] not in d["description"]


def test_tax_is_a_whole_number_percentage(client, rep):
    """§12: 18.00 means 18%, never 0.18."""
    rows = client.get("/api/catalog/products", headers=auth(rep["token"])).json()
    for r in rows:
        assert Decimal(r["tax_pct"]) > 1, f"{r['sku']} tax looks like a fraction"


# --------------------------------------------------------------------------
# §A4 / §A5 — warehouse and plan setup
# --------------------------------------------------------------------------


def test_warehouses_report_their_stock_position(client, rep):
    rows = client.get("/api/admin/warehouses", headers=auth(rep["token"])).json()
    assert len(rows) >= 3
    for w in rows:
        assert w["code"] and w["name"]
        assert w["units_on_hand"] >= w["units_reserved"] >= 0


def test_admin_can_add_a_warehouse_and_a_plan(client, admin):
    created = client.post("/api/admin/warehouses", headers=auth(admin["token"]), json={
        "code": "nrth", "name": "Northern Depot", "unit_ship_cost": "3.25",
    })
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "NRTH", "codes are normalised"

    dupe = client.post("/api/admin/warehouses", headers=auth(admin["token"]), json={
        "code": "NRTH", "name": "Clash", "unit_ship_cost": "1",
    })
    assert dupe.status_code == 409

    plan = client.post(
        "/api/admin/subscription-plans", headers=auth(admin["token"]),
        json={"name": "Quarterly Care", "interval": "quarterly"},
    )
    assert plan.status_code == 201, plan.text
    assert plan.json()["interval"] == "quarterly"


def test_a_rep_cannot_create_warehouses_or_plans(client, rep):
    assert client.post("/api/admin/warehouses", headers=auth(rep["token"]), json={
        "code": "NOPE", "name": "Nope", "unit_ship_cost": "1",
    }).status_code == 403
    assert client.post("/api/admin/subscription-plans", headers=auth(rep["token"]),
                       json={"name": "Nope", "interval": "monthly"}).status_code == 403


# --------------------------------------------------------------------------
# §B3 — order-level discount
# --------------------------------------------------------------------------


def test_order_discount_applies_to_every_line(client, rep):
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")
    dock = _product(client, token, "HW-DK-01")

    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [
            {"product_id": laptop["id"], "qty": 1, "discount_pct": "5"},
            {"product_id": dock["id"], "qty": 2, "discount_pct": "0"},
        ],
    }).json()

    res = client.post(f"/api/quotes/{quote['id']}/order-discount",
                      headers=auth(token), json={"discount_pct": "12"})
    assert res.status_code == 200, res.text
    assert {Decimal(l["discount_pct"]) for l in res.json()["lines"]} == {Decimal("12")}


def test_an_order_discount_is_visible_to_the_score(client, rep):
    """THE reason it is written onto the lines rather than stored separately.

    An order-level field would sit outside the per-line ceilings that §5.1
    scores, so a rep could set 30% against a 10% ceiling and score zero.
    """
    token = rep["token"]
    customer = _gold_customer(client, token)
    setup = _product(client, token, "SV-INST-01")   # gold/Service ceiling is 10%

    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": setup["id"], "qty": 2, "discount_pct": "0"}],
    }).json()
    client.post(f"/api/quotes/{quote['id']}/order-discount",
                headers=auth(token), json={"discount_pct": "30"})

    score = client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token)).json()
    assert score["approval_chain"], "a 30% order discount must not auto-approve"
    assert score["aggregates"]["worst"] == 20.0, "30% against a 10% ceiling"


def test_an_order_discount_on_an_approved_quote_re_enters_the_chain(
    client, rep, manager
):
    """§7 must hold for the order-level control too — otherwise it is the
    easiest way to slip a discount past the approval chain."""
    token = rep["token"]
    customer = _gold_customer(client, token)
    laptop = _product(client, token, "HW-LT-14")

    quote = client.post("/api/quotes", headers=auth(token), json={
        "customer_id": customer["id"],
        "lines": [{"product_id": laptop["id"], "qty": 1, "discount_pct": "5"}],
    }).json()
    client.post(f"/api/quotes/{quote['id']}/confirm", headers=auth(token))
    detail = client.get(f"/api/quotes/{quote['id']}", headers=auth(token)).json()
    assert detail["state"] == "READY_TO_FULFILL", "compliant quote auto-approves"

    res = client.post(f"/api/quotes/{quote['id']}/order-discount",
                      headers=auth(token), json={"discount_pct": "40"})
    assert res.status_code == 200, res.text
    assert res.json()["state"].startswith("PENDING"), (
        "an order-level discount must re-enter the approval chain"
    )
