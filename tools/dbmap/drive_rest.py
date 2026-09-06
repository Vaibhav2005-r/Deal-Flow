"""Exercise the endpoints the test suite never touched, so every row in the
mapping is observed rather than inferred.

Runs against a throwaway seeded SQLite database with the same SQL tracer
attached, then merges the result into sqltrace.json.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SP = Path(__file__).parent
sys.path.insert(0, str(SP))
sys.path.insert(0, os.getcwd())

os.environ["SQLTRACE_OUT"] = str(SP / "sqltrace_extra.json")

import sqltrace  # noqa: E402  (installs the Engine listener on import)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import seed as seed_module  # noqa: E402
from app.api.deps import get_session  # noqa: E402
from app.main import app  # noqa: E402

sqltrace._install_client_hook()

tmp = Path(tempfile.mkdtemp()) / "drive.db"
url = f"sqlite:///{tmp}"
seed_module.run(url)

engine = create_engine(url, future=True)
factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def override():
    s = factory()
    try:
        yield s
        s.commit()
    finally:
        s.close()


app.dependency_overrides[get_session] = override
client = TestClient(app)


def login(email: str, password: str | None = None) -> dict:
    res = client.post("/api/auth/login", json={"email": email, "password": password or email})
    assert res.status_code == 200, (email, res.text)
    return {"Authorization": "Bearer " + res.json()["token"]}


admin = login("root@dealflow.example")
manager = login("james.whitfield@dealflow.example")
rep = login("priya.raghavan@dealflow.example")
portal = login("portal1@northwind.example", "Northwind Logistics Pvt Ltd")

with factory() as s:
    from app.models.tables import Product, ProductVariant, Quotation, Warehouse
    from sqlalchemy import select

    product_id = s.scalars(select(Product.id).order_by(Product.id)).first()
    warehouse_id = s.scalars(select(Warehouse.id).order_by(Warehouse.id)).first()
    variant = s.scalars(select(ProductVariant).order_by(ProductVariant.id)).first()
    variant_product_id, variant_id = variant.product_id, variant.id
    # a quote sitting at manager review, for the RETURN transition
    pending = s.scalars(
        select(Quotation).where(Quotation.state == "PENDING_MANAGER").order_by(Quotation.id)
    ).first()
    pending_id = pending.id if pending else None
    portal_quote = s.scalars(
        select(Quotation).where(Quotation.state == "SENT").order_by(Quotation.id)
    ).first()
    portal_quote_id = portal_quote.id if portal_quote else None
    any_quote_id = s.scalars(select(Quotation.id).order_by(Quotation.id)).first()

CALLS: list[tuple[str, str, dict]] = [
    ("GET", "/api/admin/subscription-plans", {"headers": admin}),
    ("GET", "/api/auth/me", {"headers": rep}),
    ("GET", "/api/auth/profiles", {"headers": admin}),
    ("GET", "/api/catalog/summary", {"headers": admin}),
    ("GET", "/api/invoices/summary", {"headers": manager}),
    ("GET", "/api/reports/revenue-trend?period=monthly", {"headers": manager}),
    ("GET", "/api/warehouses", {"headers": manager}),
    ("GET", "/api/portal/profile", {"headers": portal}),
    ("GET", "/api/portal/messages", {"headers": portal}),
    ("GET", f"/api/portal/quotes/{portal_quote_id}/messages", {"headers": portal}),
    ("GET", f"/api/quotes/{portal_quote_id}/messages", {"headers": rep}),
    ("POST", f"/api/quotes/{portal_quote_id}/messages",
     {"headers": rep, "json": {"body": "Mapping probe."}}),
    ("PATCH", f"/api/admin/warehouses/{warehouse_id}",
     {"headers": admin, "json": {"unit_ship_cost": "3.25"}}),
    ("PATCH", f"/api/catalog/products/{product_id}",
     {"headers": admin, "json": {"description": "Mapping probe."}}),
    ("DELETE", f"/api/catalog/products/{variant_product_id}/variants/{variant_id}",
     {"headers": admin}),
    ("POST", f"/api/quotes/{pending_id}/return",
     {"headers": manager, "json": {"reason": "Mapping probe."}}),
    ("POST", "/api/auth/portal-signup",
     {"json": {"email": "probe@mapping.example", "password": "probe-probe",
               "full_name": "Probe Person", "company_name": "Probe Industries"}}),
]

print(f"{'status':>6}  method path")
for method, path, kw in CALLS:
    res = client.request(method, path, **kw)
    flag = "" if res.status_code < 400 else "   <-- FAILED: " + res.text[:120]
    print(f"{res.status_code:>6}  {method} {path}{flag}")

sqltrace._dump()

# merge into the main trace
main = json.load(open(SP / "sqltrace.json"))
extra = json.load(open(SP / "sqltrace_extra.json"))
for key, tables in extra.items():
    slot = main.setdefault(key, {"reads": [], "writes": []})
    slot["reads"] = sorted(set(slot["reads"]) | set(tables["reads"]))
    slot["writes"] = sorted(set(slot["writes"]) | set(tables["writes"]))
json.dump(main, open(SP / "sqltrace.json", "w"), indent=1)
print("\nmerged into sqltrace.json")
