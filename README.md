# DealFlow360

B2B sales operations platform: **Quotation → Discount Governance → Approval Chain →
Warehouse Fulfillment → Hybrid Billing → Customer Portal Negotiation → Reporting.**

See [`CLAUDE.md`](CLAUDE.md) for the full specification. It is the source of truth;
where this README and that file disagree, that file wins.

---

## Status

| Phase | Gate | State |
|---|---|---|
| **1 — Foundation** | `make up` works everywhere | **partial** — see *Known gaps* |
| **2 — Domain core** | `make test` green | **done** — 122 passing in 0.28s |
| 3 — The spine | rep builds an over-ceiling quote, manager approves, in the browser | not started |
| 4 — Second ring | fulfillment split, subscriptions, upsell | not started |
| 5 — The loop | portal counter → re-score → re-entry | not started |
| 6 — Surface | dashboards, reporting, exports | not started |

Phase 2 is complete and verified against every exact expected value in spec §10.

```
122 passed in 0.28s          # full suite
 60 passed in 0.03s          # tests/golden — the pre-push gate (budget: 2s)
```

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

| Module | Spec | What it does |
|---|---|---|
| `types.py` | §4 | `Snapshot`/`Decision`, canonical JSON, sha256 input hashing |
| `governance.py` | §5.1 | BDRS + approval routing |
| `allocation.py` | §5.2 | exact subset solver + greedy fallback + backorders |
| `billing.py` | §5.3 | day-based proration, hybrid invoice partitioning |
| `sentinel.py` | §5.5 | robust-z, small-n guard, ≥2-detector consensus |
| `verifiers.py` | §8 | independent oracles, one per agent |
| `exceptions.py` | §12 | domain errors, mapped to HTTP in exactly one handler |

**The exact allocation solver.** Naive enumeration of integer allocations is
exponential and unnecessary. Unit cost depends only on the *warehouse*, and stock is
per `(warehouse, sku)` so SKUs never compete for a shared pool — therefore for a fixed
set of warehouses, each SKU can be filled cheapest-first independently, and that is
optimal. So we enumerate warehouse *subsets* (2^W) and fill greedily inside each. This
reproduces the spec's 337.5 optimum exactly, with the plan it names.

**The governance verifier is genuinely independent.** It recomputes the score from raw
snapshot fields with plain arithmetic and imports no aggregate helper from
`governance.py`. A copy-pasted re-check would agree with a bug; this one can disagree.

### Structural invariants, asserted as tests

These are claims the spec makes that quietly become false under deadline pressure, so
each is a test rather than a convention:

| Claim | Test |
|---|---|
| domain/ stays pure | `test_domain_purity.py` — AST walk |
| every agent call writes `decision_log` | `test_decision_log.py` |
| replay is byte-for-byte (§10.5) | `test_decision_contract.py` |
| no line edit bypasses re-scoring (§7) | `test_rescore_invariant.py` — AST walk |
| the portal is not the internal screen with a flag (§1) | `test_portal_separation.py` |
| BDRS beats the naive per-line rule | `test_case_b_beats_the_naive_rule` |

### `api/app/models/` — 27 tables (§6)

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
Dockerfile are written but have not been executed. The API itself is verified to boot —
`/health` and `/api/engines` respond 200 under `TestClient`.

**3. Phases 3–6 are not started.** No routers beyond `/health` and `/api/engines`, no
seed script, no UI beyond route placeholders.

---

## A correction to the spec

**§5.1's monotonicity guarantee is false as written**, under §5.1's own formulas.

The spec asserts: *"score is monotonically non-decreasing in any line's discount."*
It is not, when `margin_pct` is supplied as an independent input — because
`margin_short` is **net-weighted**:

```
margin_short = Σ(shortfall_i · net_i) / Σ net_i
```

Raising line *i*'s discount shrinks `net_i`, which shifts weight *away* from line *i*.
If line *i* is the one carrying the margin shortfall, `c3` **falls**. When line *i* is
also inside its ceiling, `c1` and `c2` do not rise to compensate, so the total score
falls. A 61-point sweep produces 56 decreases.

This is a property bug, not an implementation bug — the formulas are implemented
exactly as specified and every §10 expected value matches. Two things follow:

- **Golden Case E is unaffected.** Its margins sit above the floor, so `c3` is 0
  throughout; the case passes as specified and reaches 70.0 at 30%.
- **The property does hold in the economically real regime.** When unit cost is fixed,
  margin *falls* as discount rises, shortfall rises with it, and the sweep is monotone.
  `test_monotonicity_holds_when_margin_is_coupled_to_discount` asserts this.

Both facts are pinned as tests, including
`test_monotonicity_is_NOT_guaranteed_for_independent_margin`, which fails if someone
changes the weighting without reading §5.1. Deciding whether to *change* the formula
(e.g. weighting `margin_short` by list value rather than net) is a spec decision, so
the implementation follows the spec and documents the deviation rather than silently
divering from §10.

---

## Agent trust ladder (§8)

| Tier | Agents | May write state? |
|---|---|---|
| **T0** deterministic | Governance, Allocation, Billing | yes — money and state |
| **T1** statistical | Advisor, Sentinel | proposals only; never a monetary field |
| **T2** generative | Narrator | prose only; one nullable text column |

Sentinel's output carries `tier: 1, writes_state: false` and is asserted in tests.
Isolation Forest can supply a second vote but is never the sole reason for an alert.
