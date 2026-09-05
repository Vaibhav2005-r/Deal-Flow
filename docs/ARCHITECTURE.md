# DealFlow360 — Architecture

*Deliverable §8: one page, the data model and how the modules connect.*

---

## The shape of it

```
┌──────────────────────── WEB (React + Vite) ────────────────────────┐
│                                                                    │
│  src/internal/  15 screens          src/portal/  4 screens         │
│  rep · manager · finance · admin    customer only                  │
│         │                                   │                      │
│         └──── scope: "internal" ────┐  ┌──── scope: "portal" ──────┘
│                                     │  │                            │
│  Neither tree imports the other. Different token keys. Enforced by  │
│  tests/unit/test_portal_separation.py — §1's "genuinely separate".  │
└─────────────────────────────────────┼──┼────────────────────────────┘
                                      ▼  ▼
┌──────────────────────── API (FastAPI) ─────────────────────────────┐
│  app/api/*  — THIN. Build a Snapshot, call the domain, persist,     │
│               write decision_log, return. Logic here is a review    │
│               rejection (§12).                                      │
│                                                                     │
│  Guards: scope (internal vs portal) → role → capability             │
│          app/domain/capabilities.py is the single definition, served│
│          by /api/me so UI and API cannot disagree.                  │
└─────────────────────────────────┬───────────────────────────────────┘
                                  ▼
┌──────────────────── SERVICES (orchestration) ──────────────────────┐
│  scoring · quote_lines · fulfillment · billing · advisor · sentinel │
│  snapshots (ORM → pure types) · decision_log (EVERY agent call)     │
│                                                                     │
│  quote_lines.mutate_lines is the ONLY path that edits a line.       │
│  Every edit voids approvals and re-scores (§7). AST-enforced.       │
└─────────────────────────────────┬───────────────────────────────────┘
                                  ▼
┌──────────────── DOMAIN (pure: stdlib + pydantic + numpy) ──────────┐
│  governance  BDRS + routing        allocation  exact + greedy       │
│  billing     proration             advisor     upsell ranking       │
│  sentinel    anomaly               pricing     the ONE margin fn    │
│  verifiers   independent oracles   capabilities  role → permissions │
│                                                                     │
│  No SQLAlchemy, no FastAPI, no datetime.now(), no random, no env.   │
│  Time is injected as `as_of`. AST-enforced by test_domain_purity.   │
└─────────────────────────────────┬───────────────────────────────────┘
                                  ▼
                         MySQL 8.4 · 28 tables
```

## Data model — the spine

```
customer ──< quotation >── user (rep)
                 │
                 ├──< quote_line >── product ──< product_variant
                 │                      └─────< price_list_item >── price_list
                 │
                 ├──< approval_request        (history rows, never a mutable enum)
                 ├──< portal_message          (customer negotiation thread)
                 ├──< fulfillment_plan ──< fulfillment_line >── warehouse
                 │                                    └──────── stock
                 ├──< subscription ── subscription_plan
                 └──< invoice ──< invoice_line
                        ├──< credit_note
                        └──< payment

governance:  tier_policy · discount_policy · approval_rule
             decision_log (append-only, trigger-enforced) · outbox
             product_affinity (FP-Growth, computed at seed)
```

## How a quote moves

```
DRAFT ──confirm──► RISK_SCORED ──┬─ chain == [] ──► READY_TO_FULFILL
                                 └─ chain != [] ──► PENDING_MANAGER
                                                      │ approve
                                                      ▼
                                                 PENDING_FINANCE
                                                      │ approve
                                                      ▼
  READY_TO_FULFILL ──send──► SENT ──counter──► UNDER_NEGOTIATION
                               │                      │ rep accepts
                               │ customer confirms    └──► re-scores, may
                               ▼                            re-enter the chain
                          CONFIRMED ──► FULFILLING ──► INVOICED ──► PAID
```

**The self-governing part.** Any line edit in `READY_TO_FULFILL`, `SENT`,
`UNDER_NEGOTIATION` or either `PENDING_*` state voids every live approval and
re-scores. There is exactly one code path that edits a line, and a test walks
the AST to prove no other module does.

## Scoring, in one paragraph

Each line is scored against `min(tier_ceiling, category_ceiling)`. The blended
score combines the worst single breach (40), value-weighted leakage across the
order (30), net-weighted margin shortfall (20) and context (10). Routing adds
two things the score cannot see: a single line more than 15pp over its ceiling
goes straight to Finance, and an order conceding more than the configured
value needs review even when every line is inside its ceiling — because every
score term is a percentage, so absolute giveaway is otherwise invisible.

## The trust ladder

| Tier | Agents | May write |
|---|---|---|
| T0 deterministic | Governance, Allocation, Billing | money and state |
| T1 statistical | Advisor, Sentinel | proposals only |
| T2 generative | Narrator | one nullable text column |

Every agent call goes through `run_agent`, which runs the agent, runs its
independent verifier, and writes one `decision_log` row — all three or none.
That table is append-only and replays byte-for-byte against the pinned engine
version, which is what makes any number on screen defensible after the fact.
