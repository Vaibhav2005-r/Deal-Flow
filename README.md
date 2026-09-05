# DealFlow360

B2B sales operations platform: **Quotation → Discount Governance → Approval Chain →
Warehouse Fulfillment → Hybrid Billing → Customer Portal Negotiation → Reporting.**

---

## Status

| Phase | Gate | State |
|---|---|---|
| **1 — Foundation** | `make up` works everywhere | **partial** — see *Known gaps* |
| **2 — Domain core** | `make test` green | **done** |
| **3 — The spine** | rep builds an over-ceiling quote, manager approves, in the browser | **done — driven in a real browser** |
| 4 — Second ring | fulfillment split, subscriptions, upsell | not started |
| 5 — The loop | portal counter → re-score → re-entry | not started |
| 6 — Surface | dashboards, reporting, exports | not started |

```
189 passed in 1.43s          # full suite
 60 passed in 0.03s          # tests/golden — the pre-push gate (budget: 2s)
  0.40s                      # make demo-reset (budget: 10s)
```

### The Phase 3 gate, actually executed

Not asserted at the service boundary and called done — driven through the running
UI against a live API and a seeded database:

1. Priya (rep) signs in, picks a Gold customer, opens quote #202.
2. She adds installation at **18%** against a **10%** ceiling. The builder warns
   *before* she commits: "gold / Service ceiling is 10% — this line is 8.0pp over".
   Governance is visible, not a trap sprung after the fact.
3. Adding lines leaves the quote in `DRAFT`. It leaves `DRAFT` only via Confirm (§7).
4. Confirm scores it: **BDRS 40.0**, verifier `PASS`, routed to `SALES_MANAGER`, with
   the explanation rendered verbatim —
   *"On-Site Installation & Setup: 18% given vs 10% ceiling → 8.0pp over (contributes 32.0 of 40)"*.
5. James (manager) signs in. The quote is in his queue with the breaching line
   highlighted, its ceiling and margin beside it.
6. He approves → `READY_TO_FULFILL`, queue empties.

**Driving the real UI found a bug the API tests had missed:** adding a line to a
`DRAFT` re-scored it and pushed it straight to `PENDING_MANAGER`, because
`mutate_lines` re-scored unconditionally. The state machine requires `DRAFT` leaves `DRAFT`
only on `confirm`. Fixed, with a regression test.

---

## Quickstart

```bash
make up            # postgres + api + web
make migrate-init  # generate the first migration (once, needs postgres up)
make migrate
make seed
make test
make hooks         # wire the golden-test pre-push hook
```

Running the domain tests needs no database and no Docker:

```bash
cd api && python -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
cd api && python -m pytest -q
```

---

## What is built

### `api/app/domain/` — pure, deterministic, no I/O

Only stdlib + `pydantic` + `numpy`. No SQLAlchemy, no FastAPI, no `datetime.now()`,
no `random`, no `os.environ`. Time is injected as `as_of: date`.
`tests/unit/test_domain_purity.py` walks the AST of every module here and fails the
build on violation — written early on purpose, because this is what keeps the
architecture honest at hour 19.

| Module | What it does |
|---|---|
| `types.py` | `Snapshot`/`Decision`, canonical JSON, sha256 input hashing |
| `governance.py` | BDRS + approval routing |
| `allocation.py` | exact subset solver + greedy fallback + backorders |
| `billing.py` | day-based proration, hybrid invoice partitioning |
| `sentinel.py` | robust-z, small-n guard, ≥2-detector consensus |
| `verifiers.py` | independent oracles, one per agent |
| `exceptions.py` | domain errors, mapped to HTTP in exactly one handler |

**The exact allocation solver.** Naive enumeration of integer allocations is
exponential and unnecessary. Unit cost depends only on the *warehouse*, and stock is
per `(warehouse, sku)` so SKUs never compete for a shared pool — therefore for a fixed
set of warehouses, each SKU can be filled cheapest-first independently, and that is
optimal. So we enumerate warehouse *subsets* (2^W) and fill greedily inside each. This
reproduces the spec's 337.5 optimum exactly, with the plan it names.

**The governance verifier is genuinely independent.** It recomputes the score from raw
snapshot fields with plain arithmetic and imports no aggregate helper from
`governance.py`. A copy-pasted re-check would agree with a bug; this one can disagree.

### Phase 3 — the spine

| Piece | Notes |
|---|---|
| `services/state_machine.py` | State transition table as **data**, not branching in routers |
| `services/scoring.py` | one scoring implementation, shared by `confirm` and the re-score path |
| `services/snapshots.py` | ORM → pure domain; resolves every ceiling from `discount_policy` |
| `services/quote_lines.py` | the only module that may create, edit or delete a line |
| `app/api/` | thin routers: build a Snapshot, call the domain, persist, return |
| `app/seed.py` | 30 products · 12 customers · 3 warehouses · 200 historical orders |

The seed is deterministic (fixed-seed PRNG, verified by fingerprint across runs) and
its discount history is shaped to be *usable*: a typical discount scores robust-z ≈ 0
against its rep's history while a 40% outlier scores ≈ +6.9, so the anomaly detector has
a real distribution to work against rather than uniform noise.

### Structural invariants, asserted as tests

These are claims the specification makes that quietly become false under deadline pressure, so
each is a test rather than a convention:

| Claim | Test |
|---|---|
| domain/ stays pure | `test_domain_purity.py` — AST walk |
| every agent call writes `decision_log` | `test_decision_log.py` |
| replay is byte-for-byte | `test_decision_contract.py` |
| no line edit bypasses re-scoring | `test_rescore_invariant.py` — AST walk |
| the portal is not the internal screen with a flag | `test_portal_separation.py` |
| BDRS beats the naive per-line rule | `test_case_b_beats_the_naive_rule` |
| a DRAFT is never scored behind the rep's back | `test_adding_a_line_to_a_draft_does_not_score_it` |
| an edit mid-chain re-scores too | `test_editing_a_quote_awaiting_approval_rescores_it` |
| idempotency, optimistic concurrency, outbox | `tests/spine/test_self_governing.py` |

### `api/app/models/` — 27 tables

Money `NUMERIC(14,2)` as `Decimal`; percentages `NUMERIC(5,2)` as whole numbers.
`decision_log` is append-only. `outbox` is written in the same transaction as the state
change it belongs to. `idempotency_key` stops a double-click becoming two invoices.

### `web/src/` — two separate router trees

`internal/` and `portal/` have different auth scopes stored under different keys, and
neither imports from the other. Enforced by `test_portal_separation.py`.

---

## Known gaps

**1. No initial Alembic migration is checked in.** Autogenerate diffs the models
against a live database, and there is no Docker or Postgres on the machine this was
built on. The scaffolding (`alembic.ini`, `env.py` wired to `Base.metadata`) is in
place; `make migrate-init` produces the migration in one command once Postgres is up.
A hand-written 27-table migration that had never been executed would have been worse
than an honest gap — it would drift from the models silently.

**2. `make up` is unverified.** Same reason: no Docker locally. The Compose file and
Dockerfile are written but have not been executed. Everything they would host *is*
verified: the API serves the full spine under `uvicorn`, and the web client was driven
against it in a browser.

**3. Tests run on SQLite, production is PostgreSQL.** The column types are
dialect-portable (`app/models/base.py`): `BIGSERIAL`/`JSONB` on Postgres, `INTEGER`/
`JSON` on SQLite. Nothing under test is dialect-specific, so the spine tests exercise
the real code path — but the Postgres-only surface (the `decision_log` append-only
trigger, `JSONB` operators) is not yet covered by a test that runs against Postgres.

**4. Phases 4–6 are not started.** No fulfillment, billing, advisor, sentinel wiring,
portal UI, or reporting. The portal *router tree and auth scope* exist and are enforced
(a portal token gets 403 on every internal route), but its screens are placeholders.

---

## Agent trust ladder

| Tier | Agents | May write state? |
|---|---|---|
| **T0** deterministic | Governance, Allocation, Billing | yes — money and state |
| **T1** statistical | Advisor, Sentinel | proposals only; never a monetary field |
| **T2** generative | Narrator | prose only; one nullable text column |

Sentinel's output carries `tier: 1, writes_state: false` and is asserted in tests.
Isolation Forest can supply a second vote but is never the sole reason for an alert.

## One place we deliberately went beyond the specification

The state machine lists three states in which a line edit must void approvals and re-score:
`READY_TO_FULFILL`, `SENT`, `UNDER_NEGOTIATION` — the states *after* the chain
completes. We also cover the two mid-chain states, `PENDING_MANAGER` and
`PENDING_FINANCE`.

The reason: the stated purpose is that no approval survives an edit. A quote sitting
in `PENDING_MANAGER` has a live pending step, so editing it without re-scoring would
let an approver sign off terms that changed under them — the same hole this exists to
close. This **widens** the guarantee and never narrows it; `DRAFT` remains excluded,
because a draft has no approvals to void.
