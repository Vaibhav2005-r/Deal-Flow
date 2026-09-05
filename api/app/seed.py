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
    InvoiceKind,
    InvoiceStatus,
    SubscriptionStatus,
    QuoteState,
    Role,
    Tier,
)
from app.models.tables import (
    ApprovalRequest,
    ApprovalRule,
    FulfillmentLine,
    FulfillmentPlan,
    Invoice,
    InvoiceLine,
    Payment,
    PriceList,
    PriceListItem,
    ProductVariant,
    Subscription,
    Config,
    Customer,
    DiscountPolicy,
    Product,
    Quotation,
    QuoteLine,
    Stock,
    SubscriptionPlan,
    TierPolicy,
    User,
    Warehouse,
)
from app.settings import settings

SEED = 20260905

#: Fixed "today" for seeded fixtures, so idle-day counts stay reproducible.
AS_OF = date(2026, 9, 5)
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

#: (name, tier, contact person, phone, billing address) -- the portal Profile
#: tab reads these, so they are stored rather than invented in the UI.
#: §A2 general info. Sales unit and tax rate follow the category; the
#: description is generated from the product's own name and category so every
#: row has real, specific copy rather than one repeated placeholder.
UNITS: dict[str, str] = {
    "Hardware": "Each", "Software": "Licence",
    "Service": "Engagement", "Subscription": "Month",
}
TAX_BY_CATEGORY: dict[str, str] = {
    "Hardware": "18.00", "Software": "18.00",
    "Service": "18.00", "Subscription": "12.00",
}
DESCRIPTIONS: dict[str, str] = {
    "Hardware": "Supplied with a three-year return-to-base warranty.",
    "Software": "Perpetual licence with twelve months of updates included.",
    "Service": "Delivered on site by a certified engineer; scheduling agreed at order.",
    "Subscription": "Billed on the plan schedule; cancel with effect from the next period.",
}

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

#: customer name -> (contact person, phone, billing address)
CUSTOMER_CONTACTS: dict[str, tuple[str, str, str]] = {
    "Northwind Logistics Pvt Ltd": ("Anita Deshpande", "+91 22 4188 2200",
                                    "Unit 14, Sewri Industrial Estate, Mumbai 400015"),
    "Harbourline Shipping": ("Marcus Vale", "+91 44 3377 1900",
                             "Berth 7, Harbour Road, Chennai 600001"),
    "Calder & Voss Associates": ("Rhea Calder", "+91 80 4455 8120",
                                 "5th Floor, Prestige Atrium, Bengaluru 560001"),
    "Peregrine Manufacturing": ("Sunil Bhatt", "+91 20 6611 4300",
                                "Plot 22, Chakan MIDC, Pune 410501"),
    "Ashgrove Healthcare Group": ("Dr. Leena Mathew", "+91 484 291 7700",
                                  "Ashgrove Campus, Kakkanad, Kochi 682030"),
    "Tessellate Design Studio": ("Ivan Roy", "+91 33 4008 5512",
                                 "9B Camac Street, Kolkata 700016"),
    "Brightwater Utilities": ("Nadia Qureshi", "+91 79 2755 6640",
                              "Brightwater House, Ashram Road, Ahmedabad 380009"),
    "Fenwick Retail Holdings": ("Tom Fenwick", "+91 124 488 9010",
                                "Tower B, Cyber Hub, Gurugram 122002"),
    "Marlow Civil Engineering": ("Priyanka Sen", "+91 33 2288 4471",
                                 "Marlow Yard, Salt Lake Sector V, Kolkata 700091"),
    "Quill & Sparrow Publishing": ("Edward Sparrow", "+91 11 4106 3388",
                                   "22 Daryaganj, New Delhi 110002"),
    "Ironhold Security Services": ("Vikram Rao", "+91 40 2355 9014",
                                   "Ironhold House, Banjara Hills, Hyderabad 500034"),
    "Castellan Financial Advisory": ("Meera Iyer", "+91 22 6720 1188",
                                     "Level 9, BKC One, Mumbai 400051"),
}

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

#: tier -> the cap that tier may never exceed, whatever the category.
#: From the product flow's "Discount tiers and approval chains" screen.
TIER_CEILINGS: dict[Tier, str] = {
    Tier.GOLD: "15",
    Tier.SILVER: "10",
    Tier.BRONZE: "5",
}

#: (tier, category) -> (ceiling_pct, floor_margin_pct).  UNIQUE(tier, category)
#: is what lets the Governance verifier prove a ceiling was looked up, not
#: defaulted — so every combination must exist.
#:
#: Every value here is <= its tier cap in TIER_CEILINGS. A category ceiling
#: above the tier cap would be dead data: min() could never select it, so the
#: policy screen would advertise a discount the engine refuses to allow.
#: `test_no_category_ceiling_exceeds_its_tier_cap` enforces that.
POLICY: dict[tuple[Tier, str], tuple[str, str]] = {}
_CEILINGS = {
    Tier.GOLD: {"Hardware": "15", "Software": "15", "Service": "10", "Subscription": "12"},
    Tier.SILVER: {"Hardware": "10", "Software": "10", "Service": "8", "Subscription": "9"},
    Tier.BRONZE: {"Hardware": "5", "Software": "5", "Service": "4", "Subscription": "5"},
}
_FLOORS = {"Hardware": "20", "Software": "35", "Service": "20", "Subscription": "30"}
for _tier, _cats in _CEILINGS.items():
    for _cat, _ceil in _cats.items():
        POLICY[(_tier, _cat)] = (_ceil, _FLOORS[_cat])

CONFIG_DEFAULTS = {
    "large_order_threshold": "500000",
    # Value conceded above which a human must look regardless of score.
    # ~97th percentile of the seeded corpus; see GovernanceSnapshot.
    "concession_review_threshold": "250000",
    "concession_finance_threshold": "1000000",
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
        contact = CUSTOMER_CONTACTS.get(name)
        customers.append(
            Customer(
                name=name,
                tier=tier,
                user_id=portal_user.id,
                contact_name=contact[0] if contact else None,
                contact_phone=contact[1] if contact else None,
                billing_address=contact[2] if contact else None,
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
                unit=UNITS.get(category, "Each"),
                tax_pct=Decimal(TAX_BY_CATEGORY.get(category, "18.00")),
                description=f"{name}. {DESCRIPTIONS.get(category, '')}".strip(),
            )
        )
    session.add_all(products)

    for tier, ceiling in TIER_CEILINGS.items():
        session.add(TierPolicy(tier=tier, ceiling_pct=Decimal(ceiling)))

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
        # Set explicitly. Left to the column's server_default this is
        # wall-clock now(), which makes `make seed` non-reproducible — and
        # last_activity_at feeds the stalled detector, so it is not a
        # cosmetic field.
        last_activity_at=datetime.combine(
            AS_OF, datetime.min.time(), tzinfo=timezone.utc
        ),
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
        # Explicit, for the same reason as the other demo quote: the column's
        # server_default is wall-clock now().
        last_activity_at=datetime.combine(
            AS_OF, datetime.min.time(), tzinfo=timezone.utc
        ),
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


#: Product variants (screen 17). attribute -> values, with a price delta.
VARIANTS: dict[str, list[tuple[str, str, str]]] = {
    "HW-LT-14": [("Colour", "Slate", "0"), ("Colour", "Graphite", "0"),
                 ("RAM", "16GB", "0"), ("RAM", "32GB", "18000")],
    "HW-LT-16": [("RAM", "16GB", "0"), ("RAM", "32GB", "22000"),
                 ("Storage", "512GB", "0"), ("Storage", "1TB", "14000")],
    "HW-MN-27": [("Stand", "Fixed", "0"), ("Stand", "Height-adjustable", "4500")],
    "HW-WS-01": [("GPU", "Integrated", "0"), ("GPU", "Discrete", "45000")],
    "SB-MSP-GD": [("Term", "12 months", "0"), ("Term", "24 months", "-6000")],
}

#: Price lists (screen 17). name -> (currency, rule label, multiplier)
PRICE_LISTS: list[tuple[str, str, str, str]] = [
    ("Standard", "INR", "List price, no adjustment", "1.00"),
    ("Gold Partner", "INR", "List price minus 10 percent", "0.90"),
    ("Export (USD)", "USD", "List price minus 5 percent", "0.95"),
]

#: Approval chains by blended-score band (screen 18). Mirrors §5.1's routing
#: thresholds — this table is what the admin screen edits.
APPROVAL_RULES: list[tuple[str, str, list[str]]] = [
    ("0", "20", []),
    ("20", "50", ["SALES_MANAGER"]),
    ("50", "100", ["SALES_MANAGER", "FINANCE"]),
]

#: Deals deliberately left idle so the Deal Health dashboard has real signal.
#: (state, days_idle, discount_pct, sku, label)
STALLED_FIXTURES: list[tuple[str, int, str, str, str]] = [
    (QuoteState.SENT, 12, "6", "HW-LT-16", "sent, gone quiet"),
    (QuoteState.UNDER_NEGOTIATION, 21, "34", "HW-WS-01", "negotiating, deep discount"),
    # 18% against the gold/Software effective ceiling of 15% is a 3pp breach,
    # which scores 30.0 and routes to a single SALES_MANAGER step — coherent
    # with the pending approval row this fixture creates. A within-ceiling
    # discount here would sit in PENDING_MANAGER having breached nothing.
    (QuoteState.PENDING_MANAGER, 9, "18", "SW-BI-01", "waiting on an approver"),
]


def seed_stalled_deals(session: Session, ref: dict, as_of: date) -> list[int]:
    """A few OPEN deals that are genuinely idle.

    The stalled detector ignores closed deals (a PAID order cannot stall), so
    without these the dashboard is correctly but uselessly empty: every
    historical order is PAID. These give it truthful content — deals that
    really are waiting on someone.
    """
    reps = [u for u in ref["users"] if u.role == Role.REP]
    by_sku = {p.sku: p for p in ref["products"]}
    created: list[int] = []

    for idx, (state, idle_days, discount, sku, _label) in enumerate(STALLED_FIXTURES):
        customer = ref["customers"][idx % 10]      # never the two brand-new ones
        rep = reps[idx % len(reps)]
        product = by_sku[sku]
        last_active = as_of - timedelta(days=idle_days)

        quote = Quotation(
            customer_id=customer.id,
            rep_id=rep.id,
            state=state,
            version=1,
            last_activity_at=datetime.combine(
                last_active, datetime.min.time(), tzinfo=timezone.utc
            ),
        )
        session.add(quote)
        session.flush()

        ceiling, floor = POLICY[(customer.tier, product.category)]
        net = product.list_price * (Decimal(1) - Decimal(discount) / 100)
        margin = (net - product.unit_cost) / net * 100 if net > 0 else Decimal(0)
        session.add(QuoteLine(
            quotation_id=quote.id,
            product_id=product.id,
            qty=2,
            unit_price=product.list_price,
            discount_pct=Decimal(discount),
            ceiling_pct_applied=Decimal(ceiling),
            margin_pct=round(margin, 2),
            is_recurring=product.is_subscription,
        ))

        if state == QuoteState.PENDING_MANAGER:
            quote.risk_score = Decimal("30.0")
            session.add(ApprovalRequest(
                quotation_id=quote.id,
                step_index=0,
                approver_role="SALES_MANAGER",
                decision=ApprovalDecision.PENDING,
            ))

        created.append(quote.id)

    session.flush()
    return created


def seed_catalog_detail(session: Session, ref: dict) -> tuple[int, int]:
    """Variants and price lists — the catalog depth screens 16/17 render."""
    by_sku = {p.sku: p for p in ref["products"]}

    variants = 0
    for sku, rows in VARIANTS.items():
        product = by_sku.get(sku)
        if product is None:
            continue
        for attribute, value, extra in rows:
            session.add(ProductVariant(
                product_id=product.id, attribute=attribute,
                value=value, extra_price=Decimal(extra),
            ))
            variants += 1

    items = 0
    for name, currency, _rule, multiplier in PRICE_LISTS:
        price_list = PriceList(name=name, currency=currency)
        session.add(price_list)
        session.flush()
        for product in ref["products"]:
            session.add(PriceListItem(
                price_list_id=price_list.id,
                product_id=product.id,
                price=(product.list_price * Decimal(multiplier)).quantize(Decimal("0.01")),
            ))
            items += 1

    session.flush()
    return variants, items


def seed_approval_rules(session: Session) -> int:
    for min_score, max_score, steps in APPROVAL_RULES:
        session.add(ApprovalRule(
            min_score=Decimal(min_score), max_score=Decimal(max_score), steps=steps
        ))
    session.flush()
    return len(APPROVAL_RULES)


def seed_operational_records(
    session: Session, ref: dict, as_of: date
) -> dict[str, int]:
    """Fulfillment plans, invoices, subscriptions and payments for a slice of
    the closed history.

    Screens 7, 9, 12 and 13 are list/detail views over these tables, and
    without rows they render correctly but empty. Built directly rather than
    by driving the state machine, because this is bulk fixture data, not a
    demonstration of the flow.
    """
    warehouses = ref["warehouses"]
    plans = subs = invoices = payments = 0

    closed = session.scalars(
        select(Quotation)
        .where(Quotation.state == QuoteState.PAID)
        .order_by(Quotation.id)
        .limit(14)
    ).all()

    for idx, quote in enumerate(closed):
        lines = session.scalars(
            select(QuoteLine).where(QuoteLine.quotation_id == quote.id)
        ).all()
        if not lines:
            continue

        # --- fulfillment: alternate single-site and split shipments --------
        shippable = [ln for ln in lines if not ln.is_recurring]
        if shippable:
            split = idx % 3 == 0 and len(shippable) > 1
            used = warehouses[:2] if split else warehouses[:1]
            unit_cost = sum((w.unit_ship_cost for w in used), Decimal(0)) / len(used)
            qty_total = sum(ln.qty for ln in shippable)
            plan = FulfillmentPlan(
                quotation_id=quote.id,
                total_cost=(
                    Decimal(len(used)) * Decimal("150.00")
                    + Decimal(qty_total) * unit_cost
                ),
                shipment_count=len(used),
            )
            session.add(plan)
            session.flush()
            plans += 1
            for i, ln in enumerate(shippable):
                backorder = idx % 7 == 0 and i == len(shippable) - 1
                session.add(FulfillmentLine(
                    plan_id=plan.id,
                    product_id=ln.product_id,
                    warehouse_id=None if backorder else used[i % len(used)].id,
                    qty=ln.qty,
                    is_backorder=backorder,
                ))

        # --- billing -------------------------------------------------------
        one_time = [ln for ln in lines if not ln.is_recurring]
        recurring = [ln for ln in lines if ln.is_recurring]

        def total_of(rows: list) -> Decimal:
            return sum(
                (
                    (r.unit_price * Decimal(r.qty)
                     * (Decimal(1) - r.discount_pct / Decimal(100)))
                    for r in rows
                ),
                Decimal(0),
            ).quantize(Decimal("0.01"))

        # spread across ~8 months so the revenue trend has real periods
        issued_on = as_of - timedelta(days=25 + idx * 17)
        subscription = None
        if recurring:
            subscription = Subscription(
                quotation_id=quote.id,
                plan_id=ref["plans"][0].id,
                start_date=issued_on,
                next_bill_date=issued_on + timedelta(days=30),
                status=SubscriptionStatus.ACTIVE
                if idx % 5 else SubscriptionStatus.PAUSED,
            )
            session.add(subscription)
            session.flush()
            subs += 1

        for kind, rows, sub in (
            (InvoiceKind.ONE_TIME, one_time, None),
            (InvoiceKind.RECURRING, recurring, subscription),
        ):
            if not rows:
                continue
            # leave roughly a third outstanding so the Unpaid filter has rows
            paid = idx % 3 != 0
            invoice = Invoice(
                quotation_id=quote.id,
                subscription_id=sub.id if sub else None,
                period_key=issued_on.strftime("%Y-%m") if sub else None,
                kind=kind,
                total=total_of(rows),
                status=InvoiceStatus.PAID if paid else InvoiceStatus.ISSUED,
                # Set explicitly. Left to the column default this is wall-clock
                # now(), which both breaks seed reproducibility and collapses
                # the revenue trend into a single bucket -- every invoice would
                # appear to have been issued the moment the demo was seeded.
                created_at=datetime.combine(
                    issued_on, datetime.min.time(), tzinfo=timezone.utc
                ),
            )
            session.add(invoice)
            session.flush()
            invoices += 1
            for r in rows:
                product = session.get(Product, r.product_id)
                amount = (
                    r.unit_price * Decimal(r.qty)
                    * (Decimal(1) - r.discount_pct / Decimal(100))
                ).quantize(Decimal("0.01"))
                session.add(InvoiceLine(
                    invoice_id=invoice.id,
                    description=product.name if product else f"line {r.id}",
                    qty=r.qty, unit_price=r.unit_price, amount=amount,
                ))
            if paid:
                session.add(Payment(
                    invoice_id=invoice.id,
                    amount=invoice.total,
                    method="bank_transfer" if idx % 2 else "card",
                    paid_at=datetime.combine(
                        issued_on + timedelta(days=5), datetime.min.time(),
                        tzinfo=timezone.utc,
                    ),
                ))
                payments += 1

    session.flush()
    return {
        "fulfillment_plans": plans, "subscriptions": subs,
        "invoices": invoices, "payments": payments,
    }


def seed_pending_fulfillment(session: Session, ref: dict, as_of: date) -> int:
    """A couple of confirmed orders still awaiting fulfillment, so screen 7's
    "Orders Pending Fulfillment" list is not empty.

    Given recent activity on purpose: these are live deals, and leaving them
    idle would add noise to the Deal Health story rather than signal.
    """
    reps = [u for u in ref["users"] if u.role == Role.REP]
    by_sku = {p.sku: p for p in ref["products"]}
    created = 0

    for idx, (sku, qty) in enumerate((("HW-MN-32", 4), ("HW-RT-48", 2))):
        customer = ref["customers"][idx + 3]
        product = by_sku[sku]
        quote = Quotation(
            customer_id=customer.id,
            rep_id=reps[idx % len(reps)].id,
            state=QuoteState.CONFIRMED if idx == 0 else QuoteState.FULFILLING,
            version=3,
            risk_score=Decimal("0.0"),
            last_activity_at=datetime.combine(
                as_of - timedelta(days=idx + 1), datetime.min.time(),
                tzinfo=timezone.utc,
            ),
        )
        session.add(quote)
        session.flush()
        ceiling, _floor = POLICY[(customer.tier, product.category)]
        net = product.list_price * (Decimal(1) - Decimal("4") / 100)
        session.add(QuoteLine(
            quotation_id=quote.id, product_id=product.id, qty=qty,
            unit_price=product.list_price, discount_pct=Decimal("4"),
            ceiling_pct_applied=Decimal(ceiling),
            margin_pct=round((net - product.unit_cost) / net * 100, 2),
            is_recurring=product.is_subscription,
        ))

        # The FULFILLING order has an allocated plan and therefore RESERVED
        # stock. `services.fulfillment.plan_fulfillment` reserves rather than
        # decrementing on-hand — the goods have not shipped yet — so seeded
        # plans must do the same, or the stock screen shows plans that
        # reserved nothing. The CONFIRMED order is deliberately left unplanned
        # so both sides of that distinction are visible.
        if quote.state == QuoteState.FULFILLING:
            warehouse = ref["warehouses"][0]
            plan = FulfillmentPlan(
                quotation_id=quote.id,
                total_cost=Decimal("150.00") + Decimal(qty) * warehouse.unit_ship_cost,
                shipment_count=1,
            )
            session.add(plan)
            session.flush()
            session.add(FulfillmentLine(
                plan_id=plan.id, product_id=product.id,
                warehouse_id=warehouse.id, qty=qty, is_backorder=False,
            ))
            stock = session.scalar(
                select(Stock).where(
                    Stock.warehouse_id == warehouse.id,
                    Stock.product_id == product.id,
                )
            )
            if stock is not None:
                stock.qty_reserved += qty

        created += 1

    session.flush()
    return created


def run(database_url: str | None = None, echo: bool = False) -> dict:
    """Drop and rebuild. Idempotent by construction."""
    url = database_url or settings.database_url
    engine = create_engine(url, echo=echo, future=True)
    if "mysql" in str(url):
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            conn.commit()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
            conn.commit()
    else:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    rng = random.Random(SEED)
    factory = sessionmaker(bind=engine, future=True)

    with factory() as session:
        ref = seed_reference(session, rng)
        orders = seed_history(session, ref, rng)
        demo_quote_id = seed_demo_quote(session, ref)
        portal_demo_quote_id = seed_portal_demo_quote(session, ref)
        stalled_ids = seed_stalled_deals(session, ref, AS_OF)
        variants, price_items = seed_catalog_detail(session, ref)
        rules = seed_approval_rules(session)
        pending = seed_pending_fulfillment(session, ref, AS_OF)
        ops = seed_operational_records(session, ref, AS_OF)
        # FP-Growth runs HERE, at seed time, never in a request handler (§13)
        affinity_rules = affinity.compute(session)
        session.commit()

        summary = {
            "products": len(ref["products"]),
            "customers": len(ref["customers"]),
            "warehouses": len(ref["warehouses"]),
            "users": session.scalar(select(func.count()).select_from(User)),
            "tier_policies": len(TIER_CEILINGS),
            "discount_policies": len(POLICY),
            "historical_orders": orders,
            "affinity_rules": affinity_rules,
            "demo_quote_id": demo_quote_id,
            "portal_demo_quote_id": portal_demo_quote_id,
            "stalled_demo_deals": len(stalled_ids),
            "product_variants": variants,
            "price_list_items": price_items,
            "approval_rules": rules,
            "pending_fulfillment": pending,
            **ops,
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
