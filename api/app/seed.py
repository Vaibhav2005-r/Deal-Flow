"""Deterministic seed.  Spec §11 Phase 3 and §12.

30 products, 12 customers, 3 warehouses, 200 historical orders — the history
matters: it feeds FP-Growth affinity and per-rep discount history, and §11 says
to generate it early, not at hour 20.

Idempotent: drops and rebuilds.  `make demo-reset` must finish in under 10s.

Determinism: one fixed-seed PRNG, threaded explicitly.  Seeding is NOT domain
code (it lives outside app/domain/), so `random` is allowed here — but the same
seed must always produce the same database, or the golden demo drifts.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import affinity
from app.models.base import Base
from app.models.enums import (
    ApprovalDecision,
    QuoteState,
    Role,
    Tier,
)
from app.models.tables import (
    ApprovalRequest,
    Config,
    Customer,
    DiscountPolicy,
    Product,
    Quotation,
    QuoteLine,
    Stock,
    SubscriptionPlan,
    User,
    Warehouse,
)
from app.settings import settings

SEED = 20260905
HISTORICAL_ORDERS = 200

CATEGORIES = ["Hardware", "Software", "Service", "Subscription"]

# --------------------------------------------------------------------------
# reference data — plausible, not "Product 2" (§12)
# --------------------------------------------------------------------------

PRODUCTS: list[tuple[str, str, str, str, str]] = [
    # (sku, name, category, list_price, unit_cost)
    ("HW-LT-14", "Meridian 14\" Business Laptop", "Hardware", "100000", "62000"),
    ("HW-LT-16", "Meridian 16\" Pro Laptop", "Hardware", "145000", "92000"),
    ("HW-WS-01", "Meridian Tower Workstation", "Hardware", "210000", "138000"),
    ("HW-MN-27", "Clarity 27\" 4K Monitor", "Hardware", "38000", "24500"),
    ("HW-MN-32", "Clarity 32\" Ultrawide Monitor", "Hardware", "62000", "41000"),
    ("HW-DK-01", "Anchor Thunderbolt Dock", "Hardware", "18500", "11200"),
    ("HW-KB-01", "Anchor Mechanical Keyboard", "Hardware", "7500", "4100"),
    ("HW-HS-01", "Clarity Noise-Cancelling Headset", "Hardware", "12500", "6900"),
    ("HW-RT-48", "Gridline 48-Port Switch", "Hardware", "88000", "57000"),
    ("HW-FW-01", "Gridline Edge Firewall", "Hardware", "125000", "78000"),
    ("HW-NAS-8", "Vault 8-Bay Storage Array", "Hardware", "165000", "104000"),
    ("HW-UPS-3", "Vault 3kVA UPS", "Hardware", "42000", "27500"),
    ("SW-OS-ENT", "Meridian OS Enterprise Licence", "Software", "24000", "3200"),
    ("SW-AV-EP", "Sentinel Endpoint Protection", "Software", "9800", "1400"),
    ("SW-BK-01", "Vault Backup Suite", "Software", "31000", "5200"),
    ("SW-VD-01", "Gridline Virtual Desktop", "Software", "45000", "8900"),
    ("SW-DB-STD", "Ledger Database Standard", "Software", "78000", "12000"),
    ("SW-DB-ENT", "Ledger Database Enterprise", "Software", "185000", "27000"),
    ("SW-BI-01", "Insight Analytics Platform", "Software", "96000", "16500"),
    ("SW-CRM-01", "Relay CRM Seat Pack", "Software", "54000", "9800"),
    ("SV-INST-01", "On-Site Installation & Setup", "Service", "20000", "12500"),
    ("SV-MIG-01", "Data Migration Engagement", "Service", "85000", "54000"),
    ("SV-TRN-01", "Administrator Training (2 days)", "Service", "36000", "21000"),
    ("SV-AUD-01", "Infrastructure Security Audit", "Service", "120000", "74000"),
    ("SV-DEP-01", "Deployment Project Management", "Service", "68000", "43000"),
    ("SV-SUP-PR", "Priority Support Retainer", "Service", "48000", "28000"),
    ("SB-MSP-BR", "Managed Services — Bronze", "Subscription", "18000", "9500"),
    ("SB-MSP-SL", "Managed Services — Silver", "Subscription", "34000", "17500"),
    ("SB-MSP-GD", "Managed Services — Gold", "Subscription", "62000", "31000"),
    ("SB-CLD-01", "Gridline Cloud Capacity Plan", "Subscription", "72000", "38000"),
]

CUSTOMERS: list[tuple[str, Tier]] = [
    ("Northwind Logistics Pvt Ltd", Tier.GOLD),
    ("Harbourline Shipping", Tier.GOLD),
    ("Calder & Voss Associates", Tier.GOLD),
    ("Peregrine Manufacturing", Tier.SILVER),
    ("Ashgrove Healthcare Group", Tier.SILVER),
    ("Tessellate Design Studio", Tier.SILVER),
    ("Brightwater Utilities", Tier.SILVER),
    ("Fenwick Retail Holdings", Tier.SILVER),
    ("Marlow Civil Engineering", Tier.BRONZE),
    ("Quill & Sparrow Publishing", Tier.BRONZE),
    ("Ironhold Security Services", Tier.BRONZE),
    ("Castellan Financial Advisory", Tier.BRONZE),
]

WAREHOUSES: list[tuple[str, str, str]] = [
    # (code, name, unit_ship_cost) — costs match the §10.2 golden shape
    ("MAIN", "Central Distribution Hub", "2.0"),
    ("EAST", "Eastern Regional Depot", "3.0"),
    ("WEST", "Western Regional Depot", "2.5"),
]

USERS: list[tuple[str, str, Role]] = [
    ("priya.raghavan@dealflow.example", "Priya Raghavan", Role.REP),
    ("daniel.okafor@dealflow.example", "Daniel Okafor", Role.REP),
    ("sofia.marchetti@dealflow.example", "Sofia Marchetti", Role.REP),
    ("james.whitfield@dealflow.example", "James Whitfield", Role.MANAGER),
    ("aisha.karim@dealflow.example", "Aisha Karim", Role.FINANCE),
    ("root@dealflow.example", "System Administrator", Role.ADMIN),
]

#: (tier, category) -> (ceiling_pct, floor_margin_pct).  UNIQUE(tier, category)
#: is what lets the Governance verifier prove a ceiling was looked up, not
#: defaulted — so every combination must exist.
POLICY: dict[tuple[Tier, str], tuple[str, str]] = {}
_CEILINGS = {
    Tier.GOLD: {"Hardware": "15", "Software": "20", "Service": "10", "Subscription": "18"},
    Tier.SILVER: {"Hardware": "12", "Software": "16", "Service": "8", "Subscription": "14"},
    Tier.BRONZE: {"Hardware": "8", "Software": "12", "Service": "5", "Subscription": "10"},
}
_FLOORS = {"Hardware": "20", "Software": "35", "Service": "20", "Subscription": "30"}
for _tier, _cats in _CEILINGS.items():
    for _cat, _ceil in _cats.items():
        POLICY[(_tier, _cat)] = (_ceil, _FLOORS[_cat])

CONFIG_DEFAULTS = {
    "large_order_threshold": "500000",
    "min_suggestion_margin_pct": "15",
    "stall_days": "7",
}


# --------------------------------------------------------------------------
# seeding
# --------------------------------------------------------------------------


def _password_hash(email: str) -> str:
    """Demo-only placeholder. Real auth is out of scope for the hackathon; no
    plaintext password is ever stored or accepted."""
    import hashlib

    return "seed$" + hashlib.sha256(f"demo::{email}".encode()).hexdigest()


def seed_reference(session: Session, rng: random.Random) -> dict:
    plans = [
        SubscriptionPlan(name="Monthly Managed Services", interval="monthly"),
        SubscriptionPlan(name="Annual Cloud Capacity", interval="annual"),
    ]
    session.add_all(plans)
    session.flush()

    users = [
        User(email=email, full_name=name, role=role, password_hash=_password_hash(email))
        for email, name, role in USERS
    ]
    session.add_all(users)
    session.flush()

    customers = []
    for idx, (name, tier) in enumerate(CUSTOMERS):
        portal_user = User(
            email=f"portal{idx + 1}@{name.split()[0].lower()}.example",
            full_name=f"{name} — portal contact",
            role=Role.PORTAL,
            password_hash=_password_hash(name),
        )
        session.add(portal_user)
        session.flush()
        customers.append(
            Customer(
                name=name,
                tier=tier,
                user_id=portal_user.id,
                # the last two customers are brand new -> "new customer +3" (§5.1)
                first_order_at=None if idx >= 10 else date(2025, 1, 1) + timedelta(days=idx * 37),
            )
        )
    session.add_all(customers)

    products = []
    for sku, name, category, price, cost in PRODUCTS:
        is_sub = category == "Subscription"
        products.append(
            Product(
                sku=sku,
                name=name,
                category=category,
                list_price=Decimal(price),
                unit_cost=Decimal(cost),
                is_subscription=is_sub,
                plan_id=plans[0].id if is_sub else None,
                is_promoted=sku in {"SW-BI-01", "SB-MSP-GD", "SV-AUD-01"},
            )
        )
    session.add_all(products)

    for (tier, category), (ceiling, floor) in POLICY.items():
        session.add(
            DiscountPolicy(
                tier=tier,
                category=category,
                ceiling_pct=Decimal(ceiling),
                floor_margin_pct=Decimal(floor),
            )
        )

    warehouses = [
        Warehouse(code=code, name=name, unit_ship_cost=Decimal(cost),
                  ship_fixed_cost=Decimal("150.00"))
        for code, name, cost in WAREHOUSES
    ]
    session.add_all(warehouses)

    for key, value in CONFIG_DEFAULTS.items():
        session.add(Config(key=key, value=value))

    session.flush()

    # stock: every product in MAIN, partial coverage elsewhere, so the
    # allocation optimizer has a real multi-warehouse decision to make
    for product in products:
        session.add(Stock(warehouse_id=warehouses[0].id, product_id=product.id,
                          qty_on_hand=rng.randint(20, 60), qty_reserved=0))
        for wh in warehouses[1:]:
            if rng.random() < 0.65:
                session.add(Stock(warehouse_id=wh.id, product_id=product.id,
                                  qty_on_hand=rng.randint(0, 25), qty_reserved=0))
    session.flush()

    return {
        "users": users,
        "customers": customers,
        "products": products,
        "warehouses": warehouses,
        "plans": plans,
    }


def seed_history(session: Session, ref: dict, rng: random.Random) -> int:
    """200 closed orders.  Feeds FP-Growth baskets and per-rep discount history
    (§5.4, §5.5) — both of which need real distributions, not uniform noise."""
    reps = [u for u in ref["users"] if u.role == Role.REP]
    customers = ref["customers"]
    products = ref["products"]
    by_category: dict[str, list[Product]] = {}
    for p in products:
        by_category.setdefault(p.category, []).append(p)

    # a few genuine affinities so FP-Growth finds real rules rather than noise
    bundles = [
        ("HW-LT-14", ["HW-DK-01", "SW-OS-ENT", "SV-INST-01"]),
        ("HW-LT-16", ["HW-MN-27", "HW-DK-01", "SW-AV-EP"]),
        ("HW-NAS-8", ["SW-BK-01", "SV-MIG-01"]),
        ("SW-DB-ENT", ["SV-MIG-01", "SV-TRN-01", "SB-MSP-GD"]),
        ("HW-FW-01", ["SW-AV-EP", "SV-AUD-01"]),
    ]
    by_sku = {p.sku: p for p in products}

    base_day = date(2026, 1, 5)
    created = 0

    for i in range(HISTORICAL_ORDERS):
        rep = reps[i % len(reps)]
        customer = customers[rng.randrange(len(customers))]
        order_day = base_day + timedelta(days=rng.randrange(0, 230))

        # basket: sometimes an anchored bundle, sometimes a random spread
        skus: list[str] = []
        if rng.random() < 0.55:
            anchor, partners = bundles[rng.randrange(len(bundles))]
            skus.append(anchor)
            for partner in partners:
                if rng.random() < 0.7:
                    skus.append(partner)
        else:
            for _ in range(rng.randint(1, 4)):
                cat = CATEGORIES[rng.randrange(len(CATEGORIES))]
                skus.append(by_category[cat][rng.randrange(len(by_category[cat]))].sku)
        skus = list(dict.fromkeys(skus))

        quote = Quotation(
            customer_id=customer.id,
            rep_id=rep.id,
            state=QuoteState.PAID,
            version=1,
            last_activity_at=datetime.combine(order_day, datetime.min.time(),
                                              tzinfo=timezone.utc),
        )
        session.add(quote)
        session.flush()

        for sku in skus:
            product = by_sku[sku]
            ceiling, floor = POLICY[(customer.tier, product.category)]
            # discounts cluster just under the ceiling, with a light tail over it
            # -> a realistic robust-z history rather than uniform noise (§5.5)
            centre = float(ceiling) * 0.72
            discount = max(0.0, min(45.0, rng.gauss(centre, 3.2)))
            if rng.random() < 0.06:
                discount = min(45.0, float(ceiling) + rng.uniform(1.0, 9.0))
            discount = round(discount, 2)

            qty = rng.randint(1, 12)
            net_unit = product.list_price * (Decimal(1) - Decimal(str(discount)) / 100)
            margin = (
                (net_unit - product.unit_cost) / net_unit * 100
                if net_unit > 0
                else Decimal(0)
            )
            session.add(
                QuoteLine(
                    quotation_id=quote.id,
                    product_id=product.id,
                    qty=qty,
                    unit_price=product.list_price,
                    discount_pct=Decimal(str(discount)),
                    ceiling_pct_applied=Decimal(ceiling),
                    margin_pct=round(margin, 2),
                    is_recurring=product.is_subscription,
                )
            )
        created += 1

    session.flush()
    return created


def seed_demo_quote(session: Session, ref: dict) -> int:
    """The demo quotation: deliberately over-ceiling, so the Phase 3 gate — a
    rep builds an over-ceiling quote and a manager approves it — has a fixture
    to start from.  Mirrors golden Case A (§10.1): BDRS 41.9 -> SALES_MANAGER.
    """
    rep = next(u for u in ref["users"] if u.role == Role.REP)
    customer = next(c for c in ref["customers"] if c.tier == Tier.GOLD)
    laptop = next(p for p in ref["products"] if p.sku == "HW-LT-14")
    setup = next(p for p in ref["products"] if p.sku == "SV-INST-01")

    quote = Quotation(
        customer_id=customer.id,
        rep_id=rep.id,
        state=QuoteState.DRAFT,
        version=1,
    )
    session.add(quote)
    session.flush()

    # Case A exactly: 100000 @ 12% (ceiling 15), 20000 @ 18% (ceiling 10)
    session.add(QuoteLine(
        quotation_id=quote.id, product_id=laptop.id, qty=1,
        unit_price=Decimal("100000"), discount_pct=Decimal("12"),
        ceiling_pct_applied=Decimal("15"), margin_pct=Decimal("30"),
        is_recurring=False,
    ))
    session.add(QuoteLine(
        quotation_id=quote.id, product_id=setup.id, qty=1,
        unit_price=Decimal("20000"), discount_pct=Decimal("18"),
        ceiling_pct_applied=Decimal("10"), margin_pct=Decimal("14"),
        is_recurring=False,
    ))
    session.flush()
    return quote.id


def seed_portal_demo_quote(session: Session, ref: dict) -> int:
    """Seed a quote already in SENT state for the customer portal demo.

    Customer 0 (Northwind Logistics, portal1@northwind.example).
    Has 2 lines (Case A) and is in SENT state awaiting customer review.
    """
    rep = next(u for u in ref["users"] if u.role == Role.REP)
    customer = next(c for c in ref["customers"] if c.tier == Tier.GOLD)
    laptop = next(p for p in ref["products"] if p.sku == "HW-LT-14")
    setup = next(p for p in ref["products"] if p.sku == "SV-INST-01")

    quote = Quotation(
        customer_id=customer.id,
        rep_id=rep.id,
        state=QuoteState.SENT,
        version=2,
        risk_score=Decimal("41.9"),
    )
    session.add(quote)
    session.flush()

    session.add(QuoteLine(
        quotation_id=quote.id, product_id=laptop.id, qty=1,
        unit_price=Decimal("100000"), discount_pct=Decimal("12"),
        ceiling_pct_applied=Decimal("15"), margin_pct=Decimal("30"),
        is_recurring=False,
    ))
    session.add(QuoteLine(
        quotation_id=quote.id, product_id=setup.id, qty=1,
        unit_price=Decimal("20000"), discount_pct=Decimal("18"),
        ceiling_pct_applied=Decimal("10"), margin_pct=Decimal("14"),
        is_recurring=False,
    ))
    session.flush()
    return quote.id


def run(database_url: str | None = None, echo: bool = False) -> dict:
    """Drop and rebuild. Idempotent by construction."""
    url = database_url or settings.database_url
    engine = create_engine(url, echo=echo, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    rng = random.Random(SEED)
    factory = sessionmaker(bind=engine, future=True)

    with factory() as session:
        ref = seed_reference(session, rng)
        orders = seed_history(session, ref, rng)
        demo_quote_id = seed_demo_quote(session, ref)
        portal_demo_quote_id = seed_portal_demo_quote(session, ref)
        # FP-Growth runs HERE, at seed time, never in a request handler (§13)
        affinity_rules = affinity.compute(session)
        session.commit()

        summary = {
            "products": len(ref["products"]),
            "customers": len(ref["customers"]),
            "warehouses": len(ref["warehouses"]),
            "users": session.scalar(select(func.count()).select_from(User)),
            "discount_policies": len(POLICY),
            "historical_orders": orders,
            "affinity_rules": affinity_rules,
            "demo_quote_id": demo_quote_id,
            "portal_demo_quote_id": portal_demo_quote_id,
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the DealFlow360 database.")
    parser.add_argument("--demo", action="store_true",
                        help="reset to demo state (same thing; kept for make demo-reset)")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--echo", action="store_true")
    args = parser.parse_args(argv)

    summary = run(args.database_url, echo=args.echo)
    for key, value in summary.items():
        print(f"  {key:<20} {value}")
    print("seed complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
