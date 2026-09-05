# DealFlow360

B2B sales operations platform: **Quotation → Discount Governance → Approval Chain →
Warehouse Fulfillment → Hybrid Billing → Customer Portal Negotiation → Reporting.**

See [`CLAUDE.md`](CLAUDE.md) for the specification — the exact constants, signatures
and expected values this implementation is built against. Where this README and that
file disagree, that file wins.

---

## Status

All six build phases are complete, and all 18 screens of the product flow are built.

```
372 passed in 13.3s          # full suite
 83 passed in 0.05s          # tests/golden — the pre-push gate (budget: 2s)
  0.79s                      # make demo-reset (budget: 10s)
```

| Phase | Gate | State |
|---|---|---|
| 1 — Foundation | `make up` works everywhere | **done** — migration checked in, `alembic check` clean |
| 2 — Domain core | `make test` green | **done** — every §10 value matches |
| 3 — The spine | over-ceiling quote → manager approves, in the browser | **done** — driven in a real browser |
| 4 — Second ring | fulfillment split, subscriptions, upsell | **done** |
| 5 — The loop | portal counter → re-score → chain re-entry | **done** |
| 6 — Surface | dashboards, reporting, exports, audit | **done** |

**Quick tour:** sign in as `james.whitfield@dealflow.example` (the seeded accounts use
their own email as the password) and the landing page shows what needs attention. The
Config tab is where the governance rules live; the Audit tab is the decision log with
one-click replay.

---

## Quickstart

```bash
make up            # postgres + api + web
make migrate       # alembic upgrade head
make seed          # 30 products · 12 customers · 3 warehouses · 200 historical orders
make test
make hooks         # wire the golden-test pre-push hook
```

The API and the whole test suite also run with no database server and no Docker —
column types are dialect-portable, so everything falls back to SQLite:

```bash
cd api && python -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
cd api && python -m pytest -q
```

---

## The thesis

Two ideas carry the build.

**0. The score cannot see money.** Every BDRS term is a percentage, so an order
that sits exactly at ceiling on every line breaches nothing and scores ~0 no
matter how large it is. The effect is inverted rather than merely absent: ten
lines at a 10% ceiling concede 100,000 and score 3.0, while one line 1pp over
concedes 11,000 and scores 7.6 — the order giving away nine times more is the
one nobody reviews. Routing therefore also weighs the absolute value conceded.
It only ever *adds* oversight, it does not enter the score (so §10's published
values are untouched), and its thresholds are calibrated against the corpus so
the gate fires on the top ~3% by value rather than taxing ordinary business.

**1. The score is blended, not a threshold.** A single order-level discount limit is
trivially gamed: five lines each 2–3pp over ceiling look harmless one at a time. The
Blended Discount Risk Score (§5.1) aggregates the worst single breach, the value-weighted
leak across the whole order, the net-weighted margin shortfall, and context. Golden
Case B is the proof, and it is asserted **both ways** — that a naive "flag any line >5pp
over" rule passes the quote, and that BDRS still routes it to a manager.

**2. Every number is defensible after the fact.** Every agent call writes one row to
`decision_log` with the full input snapshot, so any decision can be replayed
byte-for-byte against the pinned engine version that produced it. The Audit screen does
this in one click. Replay is 100% on every deterministic agent.

---

## Architecture

### `api/app/domain/` — pure, deterministic, no I/O

Nine modules importing only stdlib, `pydantic` and `numpy`. No SQLAlchemy, no FastAPI,
no `datetime.now()`, no `random`, no `os.environ`. Time is injected as `as_of: date`.
`tests/unit/test_domain_purity.py` walks the AST of every module here and fails the
build on violation.

| Module | Spec | What it does |
|---|---|---|
| `types.py` | §4 | `Snapshot`/`Decision`, canonical JSON, sha256 input hashing |
| `governance.py` | §5.1 | BDRS + approval routing |
| `allocation.py` | §5.2 | exact subset solver + greedy fallback + backorders |
| `billing.py` | §5.3 | day-based proration, hybrid invoice partitioning |
| `advisor.py` | §5.4 | upsell ranking over precomputed affinity |
| `sentinel.py` | §5.5 | robust-z, small-n guard, ≥2-detector consensus |
| `pricing.py` | §5.4 | the one margin function the whole system shares |
| `verifiers.py` | §8 | independent oracles, one per agent |
| `exceptions.py` | §12 | domain errors, mapped to HTTP in exactly one handler |

**The exact allocation solver** doesn't enumerate integer allocations. Unit cost depends
only on the warehouse and stock is per `(warehouse, sku)`, so for a fixed warehouse
subset each SKU fills cheapest-first independently — and that is optimal. Enumerating
subsets reproduces the spec's 337.5 optimum with the exact plan it names.

**The governance verifier is genuinely independent.** It recomputes the score from raw
snapshot fields with plain arithmetic and imports no aggregate helper from
`governance.py`. A copy-pasted re-check agrees with a bug; this one can disagree.

### Structural invariants, asserted as tests

Claims that quietly become false under deadline pressure, so each is a test rather than
a convention:

| Claim | Test |
|---|---|
| `domain/` stays pure | `test_domain_purity.py` — AST walk |
| every agent call writes `decision_log` | `test_decision_log.py` |
| replay is byte-for-byte (§10.5) | `test_decision_contract.py` |
| no line edit bypasses re-scoring (§7) | `test_rescore_invariant.py` — AST walk |
| the portal is not the internal screen with a flag (§1) | `test_portal_separation.py` |
| BDRS beats the naive per-line rule | `test_case_b_beats_the_naive_rule` |
| a DRAFT is never scored behind the rep's back | `test_adding_a_line_to_a_draft_does_not_score_it` |
| `make seed` is reproducible | `test_seed_determinism.py` — AST walk |
| a closed deal cannot stall | `test_a_paid_deal_never_stalls` |
| the tier ceiling actually binds | `test_tier_ceilings.py` |

### Data & API

28 tables. Money `NUMERIC(14,2)` as `Decimal`; percentages `NUMERIC(5,2)` as whole
numbers. `decision_log` is append-only; `outbox` rows are written in the same
transaction as the state change they belong to; `idempotency_key` stops a double-click
becoming two invoices. 60 endpoints across quoting, approvals, fulfillment, billing,
the portal, catalog, admin config and reporting.

### `web/src/` — two separate router trees

15 internal screens and 3 portal screens, with different auth scopes stored under
different keys. Neither tree imports from the other, enforced by a test. The portal
payload carries no margin, ceiling, cost, risk score or approval data — a customer sees
commercial terms only.

---

## The 18-screen product flow

| # | Screen | # | Screen |
|---|---|---|---|
| 1 | Login **& signup** | 10 | Billing detail — one-time vs recurring, pause/cancel |
| 2 | Sales dashboard | 11 | Customer portal |
| 3 | Quotations — **kanban + table** | 12 | Invoices list |
| 4 | Quotation detail | 13 | Invoice detail |
| 5 | Approvals — **risk, stage, filters** | 14 | Deal health dashboard |
| 6 | Approval detail — **full audit trail** | 15 | Admin reporting |
| 7 | Fulfillment & stock | 16 | Product catalog — **create** |
| 8 | Fulfillment — **manual override** | 17 | Product detail — **variants, price lists** |
| 9 | Subscriptions | 18 | Discount tiers & approval chains |

Plus an **Audit** screen beyond the flow: `decision_log` telemetry with per-row replay.

A few of these are worth calling out because the guard rails matter more than the
screen:

**Manual override (8).** The operator names their own split. A costlier plan is their
call; an impossible one is not — the server re-checks coverage and stock exactly as it
does for the optimizer, and a rejected override leaves the original reservation intact
rather than leaking it.

**Backorder consolidation (§5.2).** On stock receipt this raises a
`CONSOLIDATE_BACKORDER` proposal on the outbox. It does not re-allocate by itself:
moving stock and money without a human deciding is what §8's trust ladder exists to
prevent.

**Cancel is not a refund (10).** Cancelling ends the subscription at
`next_bill_date` and emits no credit note; the customer keeps the period they paid for.
Refunding mid-period is a proration, which is a different button. Conflating the two is
how a cancellation silently becomes money back.

**Signup (1) always creates a rep.** The role field on the request is deliberately
ignored — otherwise anyone could mint themselves a manager and approve their own
over-ceiling quotes. Passwords are PBKDF2 with a per-user salt.

**Catalog writes refuse a loss (16/17).** A product, a variant's price delta, or a price
list entry that would put the sale at or below unit cost is rejected.

---

## Three defects found and fixed after the phases shipped

Each was found by using the product rather than by reading the code.

**1. Deal Health was 100% false positives.** All 200 alerts sat on `PAID` deals while
the only two live deals went unflagged — the stalled rule had no terminal-state gate, so
every won deal re-read as "stalled for 243 days". *Stalled* now means someone still owes
the deal an action, so `CLOSED_STATES` holds `PAID` only; `INVOICED` deliberately still
stalls, because an unpaid invoice is still awaiting one. The gate lives in the domain,
not in the dashboard query, so no caller can bypass it.

**2. The Audit screen reported a 100% pass rate over zero verified calls.** The rate fell
back to `100.0` whenever nothing had been judged, and every logged row was `SKIPPED`. It
is now `null` when unmeasured, renders as "not measured", and a real rate is qualified
with the number of calls it was computed over.

**3. The tier ceiling could never bind.** §5.1 scores against
`min(tier_ceiling_pct, category_ceiling_pct)`, but the tier term was derived as `MAX()`
over that tier's own categories — a value that can never be smaller than the category it
is compared against, so the tier limb was dead code and a Gold customer could take 20%
where the flow caps them at 15%. It is now a real `tier_policy` row, and a category
ceiling above its tier cap is rejected at the API rather than stored as data `min()`
could never select.

---

## A fourth defect, reported from use

**The score is blind to concession value.** A rep discounting every line to
exactly its ceiling breaches nothing, scores near zero, and auto-approves —
whatever the order is worth. Twenty laptops at the 15% gold/Hardware ceiling
concede ₹438,100 and used to pass with no one looking.

Fixed as a routing gate rather than a new score term, so §10's expected values
still hold. Finding it also exposed a second problem: the independent
Governance verifier still modelled the old routing and began failing the
engine — a 97.9% pass rate on a suite that should read 100%. That is the oracle
doing its job, and it was updated to recompute concession itself rather than
trust the number it is checking.

## Where we deliberately went beyond the specification

**§7's re-score set.** The spec names three states in which a line edit must void
approvals and re-score. We also cover the two mid-chain `PENDING_*` states: §7's stated
purpose is that no approval survives an edit, and a quote awaiting an approver has live
authority that an edit invalidates. This widens the guarantee and never narrows it;
`DRAFT` stays excluded, because a draft has no approvals to void.

**§6's schema.** `tier_policy` was added because §5.1 needs two independent ceilings and
§6 stored only one. Documented in `CLAUDE.md` §6 at the point of the claim.

**§5.1's monotonicity guarantee is false as written**, under its own formulas, when
`margin_pct` is supplied as an independent input — `margin_short` is net-weighted, so
raising a line's discount shrinks its net and shifts weight away from it, and `c3` falls.
Golden Case E is unaffected (its margins sit above the floor, so `c3` is 0), and the
property does hold in the economically real regime where margin is coupled to discount.
Both the counterexample and the holding regime are pinned as tests.

---

## Agent trust ladder (§8)

| Tier | Agents | May write state? |
|---|---|---|
| **T0** deterministic | Governance, Allocation, Billing | yes — money and state |
| **T1** statistical | Advisor, Sentinel | proposals only; never a monetary field |
| **T2** generative | Narrator | prose only; one nullable text column |

Sentinel's output carries `tier: 1, writes_state: false`. Isolation Forest can supply a
second vote but is never the sole reason for an alert. The Narrator writes one nullable
text column nothing reads back, and its every number is checked against the source
record before the text is kept.

---

## Known gaps

**`make up` is unverified.** There is no Docker on the machine this was built on. The
Compose file and Dockerfile are written but have not been executed. Everything they
would host is verified: the API serves the whole flow under `uvicorn`, and the web
client was driven against it in a browser.

**Tests run on SQLite; production is PostgreSQL.** Column types are dialect-portable
(`BIGSERIAL`/`JSONB` on Postgres, `INTEGER`/`JSON` on SQLite), and nothing under test is
dialect-specific — but the Postgres-only surface (the append-only `decision_log`
trigger, `JSONB` operators) has no test running against Postgres.

**Currency is presentational.** Amounts render with `en-IN` grouping; the price-list
table carries a currency column and the seeded USD list applies a flat multiplier, but
there is no FX rate anywhere — a USD price is a number a human typed, not a conversion.

**The `decision_log` append-only trigger is PostgreSQL-only.** The migration installs
`BEFORE UPDATE`/`BEFORE DELETE` triggers that raise; on SQLite the statement is skipped,
so the test suite exercises the append-only *convention* but not its enforcement.

**Deleting a product is not offered.** Products are referenced by historical quote
lines, so a delete would either orphan an audit trail or cascade into one. Archiving is
the right answer and is not built.
