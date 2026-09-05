# DealFlow360 — Project Context

> Read this file completely before writing any code. It contains the exact
> constants, signatures, and expected values the implementation must match.
> When this file and your instinct disagree, this file wins.

---

## 1. Mission

A B2B sales operations platform: **Quotation → Discount Governance → Approval Chain →
Warehouse Fulfillment → Hybrid Billing → Customer Portal Negotiation → Reporting.**

Built for a 24-hour hackathon by 4 developers. Judged on business logic correctness,
not UI polish.

### Non-negotiable constraints

1. **Business rules live in application logic.** Approval routing, discount governance,
   warehouse splitting and billing proration must be computed. Nothing hardcoded to a
   demo path, nothing faked with `if quote.id == 1`.
2. **The customer portal is a genuinely separate, restricted view.** Different auth
   scope, different router, different components. Not the internal screen with a flag.
3. **The system runs fully offline.** One optional LLM call exists (§9). Disabling the
   network must change nothing except one text panel.
4. **No model output ever becomes a number in the database.** This is the core
   architectural invariant. See §8.

---

## 2. Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | |
| API | FastAPI + Pydantic v2 | |
| ORM | SQLAlchemy 2.0 (declarative, typed) | |
| Migrations | Alembic | |
| DB | MySQL 8.4 | migrated from PostgreSQL 16; see §6 note on the append-only trigger |
| Frontend | React 18 + Vite + TypeScript | |
| Data fetching | TanStack Query | client generated from OpenAPI |
| Styling | Tailwind | no component library — hand-roll, it's faster than fighting one |
| ML | `mlxtend` (FP-Growth), `scikit-learn` (IsolationForest), `numpy` | |
| Tests | pytest | |
| Orchestration | Docker Compose (`postgres`, `api`, `web`) | |

```bash
make up          # docker compose up --build
make migrate     # alembic upgrade head
make seed        # python -m app.seed  (idempotent, drops and rebuilds)
make test        # pytest -q
make demo-reset  # seed + reset to demo state, MUST complete in <10s
```

---

## 3. Repo layout

```
/api
  /app
    /domain          # PURE. no sqlalchemy, no fastapi, no requests, no datetime.now()
      types.py       # Snapshot, Decision, LineSnapshot, dataclasses/pydantic models
      governance.py  # BDRS + routing
      allocation.py  # warehouse split optimizer
      billing.py     # proration, invoice partitioning
      advisor.py     # upsell ranking (reads precomputed affinity, passed in)
      sentinel.py    # anomaly detectors
      verifiers.py   # independent oracles, one per T0/T1 agent
    /models          # SQLAlchemy
    /api             # FastAPI routers — thin. build Snapshot, call domain, persist
    /services        # transaction orchestration, decision_log writes, outbox
    seed.py
  /tests
    /golden          # fixed cases with exact expected values (§10)
    /unit
/web
  /src
    /internal        # rep + manager + finance + admin
    /portal          # customer — SEPARATE router tree, separate auth scope
    /lib
```

### The domain purity rule

`app/domain/**` may import only: stdlib (except `datetime.now`, `random`, `os.environ`),
`pydantic`, `numpy`. A test asserts this by walking the AST of every file in `domain/`.
Write that test early — it is the thing that keeps the architecture honest at hour 19.

Time is injected: every domain function that needs "now" takes `as_of: date` as a
parameter. Randomness is banned outright.

---

## 4. Domain core contract

Every Tier-0 agent implements exactly this shape:

```python
class Decision(BaseModel):
    output: dict
    engine_version: str      # e.g. "governance/1.0.0" — bump on ANY rule change
    input_hash: str          # sha256 of canonical JSON of the snapshot
    explanation: list[str]   # human-readable, per-line where applicable

def decide(snapshot: Snapshot) -> Decision: ...
```

`canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)`.

Every call to any agent writes one row to `decision_log` (§6). No exceptions — this
table is the audit trail, the replay corpus, and the closing move of the demo.

---

## 5. Algorithm specifications

> These are verified. The expected values in §10 were produced by running these exact
> formulas. If your implementation disagrees with §10, your implementation is wrong.

### 5.1 Blended Discount Risk Score (BDRS)

```python
CAP_WORST   = 10.0   # percentage points
CAP_LEAK    = 5.0    # percentage points
CAP_MARGIN  = 10.0   # percentage points

W_WORST     = 40.0
W_BLEND     = 30.0
W_MARGIN    = 20.0
W_CTX       = 10.0

HARD_STOP_EXCESS_PP = 15.0   # any single line over this → Finance, regardless of score
ROUTE_MANAGER_MIN   = 20.0
ROUTE_FINANCE_MIN   = 50.0
```

Per line `i`:

```
ceiling_i = min(tier_ceiling_pct, category_ceiling_pct)
excess_i  = max(0, discount_pct_i - ceiling_i)
net_i     = list_value_i * (1 - discount_pct_i / 100)
shortfall_i = max(0, floor_margin_pct_i - margin_pct_i)
```

Aggregates:

```
worst        = max(excess_i)
leak_pct     = 100 * Σ(excess_i/100 * list_value_i) / Σ list_value_i
margin_short = Σ(shortfall_i * net_i) / Σ net_i
```

Components, each capped at its weight:

```
c1 = min(W_WORST,  W_WORST  * worst        / CAP_WORST)
c2 = min(W_BLEND,  W_BLEND  * leak_pct     / CAP_LEAK)
c3 = min(W_MARGIN, W_MARGIN * margin_short / CAP_MARGIN)
c4 = min(W_CTX, context_points)
score = round(c1 + c2 + c3 + c4, 1)
```

`context_points` (max 10, additive): new customer +3 · order value above
`config.large_order_threshold` +3 · subscription term > 12 months +2 · rep discount
robust-z > 3.5 +2.

Routing:

```
if any(excess_i > HARD_STOP_EXCESS_PP) or any(margin_pct_i < floor_margin_pct_i - 10):
    → ["SALES_MANAGER", "FINANCE"]           # hard stop
elif score < ROUTE_MANAGER_MIN:  → []        # auto-approve
elif score < ROUTE_FINANCE_MIN:  → ["SALES_MANAGER"]
else:                            → ["SALES_MANAGER", "FINANCE"]
```

**CONCESSION GATE (added after §10 was written).** Every term above is a
percentage, so none of them can see how much money an order actually gives
away. An order sitting exactly at ceiling on every line breaches nothing and
scores ~0 no matter how large it is — and the effect is inverted, not merely
absent: ten lines at a 10% ceiling concede 100,000 and score 3.0, while one
line 1pp over concedes 11,000 and scores 7.6. The order giving away nine times
more is the one nobody reviews.

So routing also considers `concession = Σ(list_value_i − net_i)`:

```
if concession > config.concession_finance_threshold:  → ["SALES_MANAGER", "FINANCE"]
elif concession > config.concession_review_threshold and chain == []:
                                                      → ["SALES_MANAGER"]
```

Concession may only **add** oversight, never remove it. It adjusts routing
only and does **not** enter the score, so every expected value in §10 is
unchanged — this measures a different axis from policy breach, exactly as the
single-line hard stop already does. It is not §13's banned "single order-level
discount threshold" replacing per-line ceilings: the ceilings still do all the
scoring, and this catches what percentages structurally cannot.

Thresholds are config-driven, because a currency amount is a business policy
rather than an engine constant. The defaults (250,000 / 1,000,000) are
calibrated against the seeded corpus — median concession ~64k, p90 ~189k — so
the review gate fires on roughly the top 3% by value conceded rather than
becoming a tax on ordinary business.

`explanation` must name each breaching line and its contribution, e.g.
`"Setup Service: 18% given vs 10% ceiling → 8.0pp over (contributes 32.0 of 40)"`.

**Guaranteed properties** (assert as tests): score is monotonically non-decreasing in
any line's discount; score is 0 iff every line is within ceiling and above floor margin.

> **IMPLEMENTATION NOTE (added after building §10).** The monotonicity guarantee above
> is **false as written**, under these same formulas, when `margin_pct` is supplied as
> an independent input — because `margin_short` is net-weighted. Raising line *i*'s
> discount shrinks `net_i` and shifts weight away from line *i*; if line *i* carries the
> shortfall, `c3` falls, and when line *i* is inside its ceiling `c1`/`c2` do not rise to
> compensate. Golden Case E is unaffected (its margins are above floor, so `c3` is 0),
> and the property does hold when margin is coupled to discount, which is the
> economically real case. Both the counterexample and the holding regime are pinned as
> tests in `tests/golden/test_governance.py`. See the README for the full write-up.

### 5.2 Warehouse allocation

Objective:

```
cost(plan) = (count of distinct warehouses used) * SHIP_FIXED_COST
           + Σ over allocations: qty * unit_ship_cost[warehouse]
```

`SHIP_FIXED_COST` is what expresses "minimize number of shipments" — keep it large
relative to unit costs (seed it at 150.0 with unit costs 2.0–3.0).

**Exact solver** when `len(skus) * len(warehouses) <= 24`: enumerate integer allocations
per SKU bounded by `qty_on_hand - qty_reserved`, take the min-cost full-coverage plan.

**Greedy fallback** otherwise: rank warehouses by descending order coverage
(`Σ min(demand_s, stock_ws)`), tie-break by ascending unit cost, drain in order.

**Backorders:** any residual after all warehouses are drained becomes
`fulfillment_line(is_backorder=True, warehouse=None)`. On stock receipt, re-run the
optimizer over open backorders for that SKU and raise a
`CONSOLIDATE_BACKORDER` proposal.

### 5.3 Proration

Day-based. Do not use month fractions.

```python
def prorate(period_start: date, period_end: date, change_date: date,
            old_amount: Decimal, new_amount: Decimal) -> Proration:
    total     = (period_end - period_start).days
    remaining = (period_end - change_date).days
    assert 0 <= remaining <= total
    credit = round(old_amount * remaining / total, 2)
    charge = round(new_amount * remaining / total, 2)
    return Proration(credit=credit, charge=charge, delta=charge - credit)
```

Negative delta emits a `credit_note`, never a negative invoice line.

**Hybrid billing:** one-time and recurring lines live on the **same** `quotation`. The
invoice generator partitions by `quote_line.is_recurring`: one-time lines produce an
invoice immediately on confirmation; recurring lines create a `subscription` with
`next_bill_date` and generate invoices on schedule.

Use `Decimal` for all money. Never `float`. Store as `NUMERIC(14,2)`.

### 5.4 Advisor (upsell / cross-sell)

Precomputed at seed time — **not** at request time.

```python
from mlxtend.frequent_patterns import fpgrowth, association_rules
# one-hot basket matrix from historical orders
# min_support=0.02, metric="confidence", min_threshold=0.3
# persist to product_affinity(antecedent_id, consequent_id, support, confidence, lift)
```

At quote time, one indexed query then rank:

```
score = lift * (1 + promo_boost) * margin_gate
margin_gate = 0.0 if adding this line would push order margin below
              config.min_suggestion_margin_pct else 1.0
promo_boost = 0.5 if product.is_promoted else 0.0
```

Return top 3 with `margin_delta_if_added`, computed by the **same** margin function the
governance engine uses. Target latency < 10ms.

### 5.5 Sentinel (deal health & anomaly)

Three detectors. **Alert only when ≥2 agree**, except stalled-deal which stands alone.

```python
def robust_z(x: float, history: list[float]) -> float:
    med = median(history)
    mad = median([abs(h - med) for h in history]) or 1e-9
    return 0.6745 * (x - med) / mad
```

| Detector | Rule |
|---|---|
| Stalled | `(as_of - last_activity_at).days > config.stall_days` (seed: 7) |
| Discount anomaly | `abs(robust_z(discount, rep_history)) > 3.5` |
| Delivery slippage | promised date < earliest feasible date from `fulfillment_plan` |

**Small-n guard:** if the rep has fewer than 8 historical quotes, use the *team* median
history instead of the rep's. Without this, every new rep's second quote is an anomaly.

Isolation Forest (`sklearn.ensemble.IsolationForest`, `n_estimators=100`,
`contamination='auto'`) is the multivariate second opinion on
`[order_value, avg_discount, line_count, customer_tier_encoded]`. It is a *secondary*
signal only — never the sole reason for an alert.

---

## 6. Data model

Money: `NUMERIC(14,2)`. Percentages: `NUMERIC(5,2)` as whole numbers (15.00 = 15%).
All tables get `id BIGSERIAL PRIMARY KEY`, `created_at`, `updated_at`.

**Config & identity**
- `user(email, password_hash, role)` — role ∈ `rep | manager | finance | admin | portal`
- `customer(name, tier, user_id)` — tier ∈ `bronze | silver | gold`
- `product(sku, name, category, list_price, unit_cost, is_subscription, plan_id, is_promoted)`
- `product_variant(product_id, attribute, value, extra_price)`
- `price_list(name, currency)` / `price_list_item(price_list_id, product_id, price)`
- `tier_policy(tier, ceiling_pct)` — **unique(tier)**. The cap a tier may never
  exceed, whatever the category (Bronze 5 / Silver 10 / Gold 15). Added after
  §6 was written: §5.1 scores against `min(tier_ceiling_pct, category_ceiling_pct)`,
  which needs two independent ceilings, and §6 originally stored only one row
  per (tier, category). The tier term was therefore derived as MAX over that
  tier's own categories — a value that by construction can never be smaller
  than the category it is compared against, so `min()` always returned the
  category ceiling and the tier limb of the formula was dead. Every
  `discount_policy.ceiling_pct` must be **≤** its tier cap, or it is data
  `min()` can never select.
- `discount_policy(tier, category, ceiling_pct, floor_margin_pct)` — **unique(tier, category)**
- `approval_rule(min_score, max_score, steps JSONB)` — ordered role list
- `warehouse(code, name, ship_fixed_cost, unit_ship_cost)`
- `stock(warehouse_id, product_id, qty_on_hand, qty_reserved)` — **unique(warehouse_id, product_id)**
- `subscription_plan(name, interval, proration_policy, cancellation_policy)`

**Transactional**
- `quotation(customer_id, rep_id, state, risk_score, risk_input_hash, version, last_activity_at)`
- `quote_line(quotation_id, product_id, qty, unit_price, discount_pct, ceiling_pct_applied, margin_pct, is_recurring)`
- `approval_request(quotation_id, step_index, approver_role, decision, reason, decided_by, decided_at)`
- `fulfillment_plan(quotation_id, total_cost, shipment_count)` / `fulfillment_line(plan_id, product_id, warehouse_id NULL, qty, is_backorder)`
- `subscription(quotation_id, plan_id, start_date, next_bill_date, status)`
- `invoice(quotation_id, kind, total, status)` / `invoice_line` / `credit_note(invoice_id, amount, reason)`
- `payment(invoice_id, amount, method, paid_at)`
- `portal_message(quotation_id, quote_line_id NULL, author_id, body, counter_discount_pct NULL)`

**Governance**

```sql
CREATE TABLE decision_log (
  id BIGSERIAL PRIMARY KEY,
  agent TEXT NOT NULL,              -- governance | allocation | billing | advisor | sentinel | narrator
  engine_version TEXT NOT NULL,
  quotation_id BIGINT NULL,
  input_hash TEXT NOT NULL,
  input_json JSONB NOT NULL,        -- full snapshot, so replay needs no other table
  output_json JSONB NOT NULL,
  verifier_verdict TEXT NOT NULL,   -- PASS | FAIL | SKIPPED
  latency_ms INT NOT NULL,
  actor_id BIGINT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Append-only. No UPDATE, no DELETE — enforce with a trigger if there's time.

> Enforced. `alembic/versions/9c4d1a7f52b0` installs BEFORE UPDATE / BEFORE
> DELETE triggers. The DDL differs by dialect and is not interchangeable:
> PostgreSQL raises from a PL/pgSQL function, MySQL signals inline with
> `SIGNAL SQLSTATE '45000'` and has no `CREATE OR REPLACE TRIGGER`, so each
> trigger is dropped first. SQLite installs nothing — the test suite's portable
> path exercises the convention, not its enforcement.

- `outbox(topic, payload, status, attempts, created_at)` — written in the same
  transaction as the state change it belongs to, drained by a worker.

---

## 7. State machine

```
DRAFT → RISK_SCORED → (READY_TO_FULFILL | PENDING_MANAGER → PENDING_FINANCE)
      → SENT → UNDER_NEGOTIATION → (back to RISK_SCORED)
      → CONFIRMED → FULFILLING → INVOICED → PAID
```

| From | Event | To | Guard |
|---|---|---|---|
| DRAFT | `confirm` | RISK_SCORED | ≥1 line |
| RISK_SCORED | auto | READY_TO_FULFILL | `chain == []` |
| RISK_SCORED | auto | PENDING_MANAGER | `chain != []` |
| PENDING_MANAGER | `approve` | PENDING_FINANCE \| READY_TO_FULFILL | next step in chain |
| PENDING_MANAGER \| PENDING_FINANCE | `reject` | DRAFT | reason required |
| PENDING_* | `return_for_revision` | DRAFT | reason required |
| READY_TO_FULFILL | `send_to_portal` | SENT | |
| SENT | `customer_counter` | UNDER_NEGOTIATION | |
| UNDER_NEGOTIATION | `rep_accepts_counter` | RISK_SCORED | **re-scores, may re-enter chain** |
| SENT \| UNDER_NEGOTIATION | `customer_confirm` | CONFIRMED | score unchanged since approval |
| CONFIRMED | `plan_fulfillment` | FULFILLING | |
| FULFILLING | `generate_invoices` | INVOICED | |
| INVOICED | `record_payment` | PAID | fully paid |

### The invariant that makes it "self-governing"

Any mutation to a `quote_line` on a quotation in `READY_TO_FULFILL`, `SENT`, or
`UNDER_NEGOTIATION`:

1. voids all existing `approval_request` rows (`decision = 'VOIDED_BY_EDIT'`)
2. re-runs the Governance agent
3. transitions to `RISK_SCORED`, which re-enters the chain if the new score crosses a
   boundary

Implement this as a single service function that **every** line-mutating path calls.
There must be no code path that edits a line without going through it.

---

## 8. Agent trust ladder — this is a code review rule

| Tier | Agents | May write state? |
|---|---|---|
| **T0 deterministic** | Governance, Allocation, Billing | Yes — money and state |
| **T1 statistical** | Advisor, Sentinel | **Proposals only.** Writes to `proposal`/alert tables. Never a monetary field, never a state transition |
| **T2 generative** | Narrator | **Prose only.** One nullable text column. Never a number, never a decision |

**Reject any PR that lets a T1 or T2 output reach a monetary column or a state
transition.** No exceptions, no "just for the demo."

### Verifiers (`domain/verifiers.py`)

Independent oracles — deterministic re-checks, **not** a second model call. Each runs
after its agent, before the result is persisted or shown.

| Agent | Verifier asserts | On FAIL |
|---|---|---|
| Governance | score recomputed by an independently written second path is equal; every line's ceiling was actually looked up (no defaults); routing monotone in score | block transition, escalate to Finance |
| Allocation | `Σ allocated + backorder == demand` per SKU; no warehouse over-allocated vs available; `cost <= single_warehouse_greedy_cost` | reject plan, fall back to greedy, surface manual override |
| Billing | `Σ invoices + Σ credit_notes == order total`; proration symmetry; no duplicate `(subscription_id, period_key)` | block invoice, raise for Finance |
| Advisor | suggestion passes margin gate; product has stock somewhere | drop the suggestion silently |
| Narrator | **every number appearing in the generated text also appears in the source record** | discard, use template |

Write `verifier_verdict` to `decision_log` on every call.

### Failure containment

- **Idempotency:** every state-transition endpoint accepts an `Idempotency-Key` header;
  a replay returns the original response. Prevents double invoices from a double-click.
- **Optimistic concurrency:** `quotation.version` checked on every write; mismatch → 409.
- **Outbox:** side effects are rows written in the same transaction, drained by a worker.
- **Circuit breaker on T2:** 3 failures in 60s opens for 5 minutes.

---

## 9. The one LLM call

```
POST /api/quotes/{id}/narrate
  1. feature flag off?          → template, return
  2. cache hit on content hash? → cached, return
  3. cloud call, 800ms timeout, 1 retry
  4. numeric-consistency scan   → fail → template
  5. store { text, source: "llm"|"template", model_version, prompt_hash }
```

Writes one nullable text column on `quotation`. Nothing reads it back. Deleting the
value changes no behaviour. Build the template path **first** and the cloud path last —
if you run out of time, the template path is a complete feature.

---

## 10. Golden tests — exact expected values

Put these in `tests/golden/`. They must run in under 2 seconds and be wired to a
pre-push hook. When someone edits a constant at hour 19, this is what saves the demo.

### 10.1 BDRS

**Case A — the brief's own example.** Gold customer. Laptop (Hardware), list 100000,
12% given / 15% ceiling, margin 30%, floor 20%. Setup Service (Service), list 20000,
18% given / 10% ceiling, margin 14%, floor 20%.

```
worst = 8.0   leak_pct = 1.33   margin_short = 0.94
components = [32.0, 8.0, 1.9, 0.0]
score = 41.9  →  ["SALES_MANAGER"]
```

**Case B — death by a thousand cuts.** Five lines, list 40000 each, margin 18%, floor 20%:
`(ceiling 15, given 17)`, `(15, 18)`, `(10, 12)`, `(15, 18)`, `(10, 12)`.

```
worst = 3.0   leak_pct = 2.40   margin_short = 2.00
components = [12.0, 14.4, 4.0, 0.0]
score = 30.4  →  ["SALES_MANAGER"]
```

> A naive rule ("flag if any line is >5pp over") **passes** this case. Assert both:
> that BDRS routes it to a manager, and that the naive comparison does not. This is the
> demo's key moment — make it a test so it cannot silently break.

**Case C — compliant.** All lines within ceilings and above floor margin.

```
score = 0.0  →  []  (auto-approve)
```

**Case D — catastrophic line.** Line 1: list 50000, 40% given / 15% ceiling, margin 2%,
floor 20%. Line 2: list 50000, 5% given / 15% ceiling, margin 30%.

```
worst = 25.0  leak_pct = 12.50  margin_short = 6.97
components = [40.0, 30.0, 13.9, 0.0]
score = 83.9  →  ["SALES_MANAGER", "FINANCE"]   (hard stop: worst > 15pp)
```

**Case E — monotonicity.** Two lines, ceiling 10 each. Sweep line 1's discount from 10%
to 30%. Score must never decrease. At 30% it reaches 70.0.

### 10.2 Allocation

Demand `{A: 10, B: 5, C: 3}`. `SHIP_FIXED_COST = 150.0`.

| Warehouse | A | B | C | unit_ship |
|---|---|---|---|---|
| MAIN | 10 | 2 | 3 | 2.0 |
| EAST | 6 | 5 | 0 | 3.0 |
| WEST | 2 | 5 | 3 | 2.5 |

```
exact optimum  = 337.5   (MAIN: A×10, B×2, C×3;  WEST: B×3)
greedy         = 339.0   (gap 0.4%)
both fully fulfil, zero backorder
```

Assert: exact ≤ greedy; both cover demand; neither exceeds available stock.

### 10.3 Proration

Period 2026-09-01 → 2026-10-01 (30 days), change on 2026-09-16 (15 days remaining).

| Scenario | credit | charge | delta |
|---|---|---|---|
| Upgrade 2→5 seats @1000 (2000 → 5000) | 1000.00 | 2500.00 | +1500.00 |
| Downgrade 5→2 seats (5000 → 2000) | 2500.00 | 1000.00 | −1500.00 |
| Change on period start | 2000.00 | 5000.00 | +3000.00 |
| Change on period end | 0.00 | 0.00 | 0.00 |

Assert the symmetry invariant: `upgrade_delta + downgrade_delta == 0`.

### 10.4 Anomaly

History `[8, 9, 7, 10, 8, 9, 11, 8, 7, 9, 10, 8]`:

```
robust_z(9)  =  0.67   → normal
robust_z(14) =  7.42   → anomaly
robust_z(22) = 18.21   → anomaly
```

Assert the small-n guard: with a 3-element history, the rep's own median is **not** used.

### 10.5 Replay

For every row in `decision_log`, re-running the pinned `engine_version` on `input_json`
must produce `output_json` byte-for-byte. **Target: 100%.** One failure is a bug, not a
tolerance.

---

## 11. Build order

Do not start a phase before the previous phase's gate is green.

**Phase 1 — Foundation.** Docker Compose up on all machines. Models + first migration.
`Snapshot`/`Decision` types. OpenAPI surface stubbed so the frontend can generate a
client and mock against it. *Gate: `make up` works everywhere.*

**Phase 2 — Domain core.** `governance.py` with Cases A–E green. `allocation.py` with
§10.2 green. Pure functions only, no API yet. *Gate: `make test` green.*

**Phase 3 — The spine.** Quote CRUD → confirm → score → route → approve, through the
real UI. Seed script producing 30 products, 12 customers, 3 warehouses, **200 historical
orders** (these feed FP-Growth and rep discount history — generate them early, not at
hour 20). *Gate: a rep builds an over-ceiling quote and a manager approves it, in the
browser.*

**Phase 4 — Second ring.** Fulfillment split + backorders. Subscriptions + proration +
invoices + credit notes. Upsell panel. Approval screen with per-line breach explanation.

**Phase 5 — The loop.** Portal (separate router, separate auth scope): line comments,
counter-discount, submit. Re-scoring and automatic re-entry into the approval chain.
*Gate: all eight steps of the brief's §9 test flow, run twice on a clean database.*

**Phase 6 — Surface.** Deal health dashboard, anomaly alerts with quote deep links,
reporting filters (period / rep / approval status / category), PDF + XLS export,
reliability panel over `decision_log`.

### Cut list, in order

Cut from the top when time runs short: XLS export → product variants → multi-currency →
Narrator → reliability panel → deal health dashboard → warehouse split → hybrid billing.

**Never cut:** quote builder, BDRS, approval chain, `decision_log`, portal re-entry.

---

## 12. Conventions

- **Money is `Decimal`.** A `float` in a monetary path is a bug. Configure SQLAlchemy to
  return `Decimal` for `NUMERIC`.
- **Percentages are whole numbers.** 15.00 means 15%, never 0.15. Be consistent or the
  BDRS will be silently wrong by two orders of magnitude.
- Routers are thin: build a `Snapshot`, call the domain, persist the `Decision`, write
  `decision_log`, return. Business logic in a router is a review rejection.
- Errors: raise domain exceptions from `domain/`, map to HTTP in one exception handler.
  Never raise `HTTPException` from `domain/`.
- Every migration is checked in. Nobody edits the database by hand.
- Seed data must look real — plausible company names, plausible prices. Judges notice
  `Customer 1`, `Product 2`.
- `main` must be demoable from the end of Phase 3 onward. Feature branches, small PRs.

## 13. Anti-patterns — do not do these

- ❌ A single order-level discount threshold. The whole point is per-line ceilings that
  aggregate. §5.1 is the differentiator; do not simplify it.
- ❌ Approval status as a mutable enum with no `approval_request` history rows.
- ❌ Letting a rep edit an approved quote without re-scoring. §7's invariant is the
  "self-governing" claim — if it can be bypassed, the claim is false.
- ❌ The portal as the internal screen with `?portal=true`. §1 constraint 2.
- ❌ Running FP-Growth or Isolation Forest inside a request handler. Precompute at seed.
- ❌ An LLM call anywhere in the critical path, or any LLM output parsed into a number.
- ❌ `datetime.now()` inside `domain/`. Inject `as_of`.
- ❌ Skipping the golden tests because "it's a hackathon." They run in 2 seconds and
  they are the only thing standing between an hour-19 constant change and a dead demo.
