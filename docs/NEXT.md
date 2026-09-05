# What we would build next

*Deliverable §8: a short note on what more time would buy.*

Ordered by what we would actually do first, not by size.

## 1. Run the test suite against MySQL, not only SQLite

The suite runs on SQLite for portability, and the column types are
dialect-portable so nothing under test is dialect-specific. But the
server-only surface has no test that executes against a real server: the
`decision_log` append-only triggers are installed by a migration that emits
genuinely different DDL for MySQL and PostgreSQL, and today we assert only
that the right statements are *selected*. A CI service container running the
migration and attempting an `UPDATE` on `decision_log` would close the gap
that matters most, because that trigger is the guarantee behind the audit
trail.

## 2. Real identity

Tokens are HMAC-signed and passwords are PBKDF2 with a per-user salt, but
there is no expiry, no refresh, and no revocation — signing out drops the
token client-side and the server would still accept it. Short-lived tokens
with a refresh flow and a server-side denylist is the next honest step, along
with rate-limiting `/api/auth/login`.

## 3. Admin-granted roles

Self-service registration correctly creates a rep and ignores any claimed
role. There is no screen for an admin to *promote* someone, so approver
accounts exist only because the seed created them. The capability model
already supports it; it needs a user-management screen and an audit row per
grant.

## 4. Push instead of poll

Every screen refetches on an interval and on tab focus. That is honest and
cheap, but a manager watching the approval queue still waits up to eight
seconds. Server-sent events on the `outbox` — which already records every
state change in the same transaction as the change itself — would make the
queue move the instant a quote is approved, without a second source of truth.

## 5. Archiving, not deleting

Products are referenced by historical quote lines, so deletion would either
orphan an audit trail or cascade into one. An `archived_at` column plus
filtering in the catalog query is the right answer and is not built. The same
applies to customers and warehouses.

## 6. Currency

The price-list table carries a currency column and the seeded USD list applies
a flat multiplier, but there is no FX rate anywhere — a USD price is a number
a human typed. Real multi-currency needs a rate table with effective dates,
and a decision about which rate a quotation locks to and when.

## 7. Confidence intervals on the anomaly detector

Sentinel uses robust-z with a small-n guard and requires two detectors to
agree. It reports a verdict, not a confidence. Surfacing "how sure" alongside
"what" would let a manager triage a queue of alerts rather than treat them as
equal.

## Deliberately not next

**More rules.** The discount taxonomy is small on purpose. Every rule added
raises the false-positive rate on compliant quotes, and a review queue nobody
trusts is worse than a smaller one that is always right. We removed rules
during this build for exactly that reason and would do it again before adding
any.
