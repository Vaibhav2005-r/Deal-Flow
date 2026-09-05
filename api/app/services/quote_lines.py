"""The self-governing invariant.  Spec §7.

Any mutation to a quote_line on a quotation in READY_TO_FULFILL, SENT or
UNDER_NEGOTIATION must:
  1. void all existing approval_request rows (decision = VOIDED_BY_EDIT)
  2. re-run the Governance agent
  3. transition to RISK_SCORED, re-entering the chain if the score moved

This is implemented ONCE, here.  Spec §13 lists "letting a rep edit an approved
quote without re-scoring" as an anti-pattern, and §7 says the self-governing
claim is false if the invariant can be bypassed — so there must be no code path
that edits a line without going through ``mutate_lines``.
``tests/unit/test_rescore_invariant.py`` asserts that structurally.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.types import GovernanceSnapshot
from app.models.enums import ApprovalDecision, REQUIRES_RESCORE_ON_EDIT
from app.models.tables import ApprovalRequest, Product, Quotation, QuoteLine


class ConcurrencyError(Exception):
    """quotation.version mismatch — the caller should return HTTP 409 (§8)."""


# --------------------------------------------------------------------------
# line primitives
#
# These live HERE, not in the router, so that no other module ever constructs,
# edits or deletes a QuoteLine.  That keeps the §7 guarantee checkable by
# inspection: `tests/unit/test_rescore_invariant.py` asserts no module outside
# this one touches a line, and a router that cannot touch a line cannot bypass
# the re-score.  It also keeps routers thin (§12).
# --------------------------------------------------------------------------


def append_line(
    session: Session,
    quotation: Quotation,
    product: Product,
    qty: int,
    discount_pct: Decimal,
    unit_price: Decimal | None = None,
) -> QuoteLine:
    """Add a line. Unit price defaults to the product's list price."""
    line = QuoteLine(
        quotation_id=quotation.id,
        product_id=product.id,
        qty=qty,
        unit_price=unit_price if unit_price is not None else product.list_price,
        discount_pct=Decimal(discount_pct),
        is_recurring=product.is_subscription,
    )
    session.add(line)
    return line


def apply_line_update(
    line: QuoteLine,
    qty: int | None = None,
    discount_pct: Decimal | None = None,
) -> QuoteLine:
    """Edit the commercial terms of a line."""
    if qty is not None:
        line.qty = qty
    if discount_pct is not None:
        line.discount_pct = Decimal(discount_pct)
    return line


def remove_line(session: Session, line: QuoteLine) -> None:
    session.delete(line)


#: Rows representing LIVE authority over the current commercial terms. An edit
#: invalidates both: a PENDING step was queued against the old score, and an
#: APPROVED step granted authority for terms that no longer exist. §7 says
#: "voids all existing approval_request rows" — leaving an APPROVED row intact
#: would let an edited quote look approved against a score nobody computed.
#: REJECTED / RETURNED / VOIDED_BY_EDIT rows belong to closed cycles and are
#: history; they are never rewritten.
LIVE_AUTHORITY = (ApprovalDecision.PENDING, ApprovalDecision.APPROVED)


def void_approvals(session: Session, quotation_id: int) -> int:
    """Void every row that still confers authority over this quotation."""
    rows = session.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.quotation_id == quotation_id,
            ApprovalRequest.decision.in_(LIVE_AUTHORITY),
        )
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.decision = ApprovalDecision.VOIDED_BY_EDIT
        row.decided_at = now

    # Flush before returning. The session runs autoflush=False, so without this
    # the next SELECT still reads these rows as PENDING — and the re-score's
    # "clear out stale pending steps" pass would DELETE the very rows we just
    # voided, erasing the audit trail the void exists to create.
    session.flush()
    return len(rows)


def rescore(
    session: Session,
    quotation: Quotation,
    snapshot: GovernanceSnapshot,
    actor_id: int | None = None,
) -> tuple[Decimal, list[str]]:
    """Re-run Governance and re-enter the approval chain.

    Delegates to `services.scoring.score_quotation` so there is exactly ONE
    scoring implementation shared with the confirm route.  Returns
    (score, chain) for callers that only need the headline.
    """
    from app.services.scoring import score_quotation

    result = score_quotation(session, quotation, actor_id=actor_id, snapshot=snapshot)
    return Decimal(str(result.score)), result.approval_chain


def mutate_lines(
    session: Session,
    quotation: Quotation,
    expected_version: int,
    mutate: Callable[[Quotation], None],
    build_snapshot: Callable[[Quotation], GovernanceSnapshot],
    actor_id: int | None = None,
) -> tuple[Decimal, list[str]]:
    """THE single line-mutating path.  Every caller goes through here.

    Applies ``mutate``, then — if the quotation was in a post-approval state —
    voids approvals and re-scores.  Bumps ``version`` for optimistic
    concurrency (§8).
    """
    if quotation.version != expected_version:
        raise ConcurrencyError(
            f"quotation {quotation.id} is at version {quotation.version}, "
            f"caller held {expected_version}"
        )

    needs_rescore = quotation.state in REQUIRES_RESCORE_ON_EDIT

    mutate(quotation)
    # Flush before the snapshot is built. The session runs with autoflush=False,
    # so an added or deleted line would otherwise still be invisible/visible to
    # build_snapshot's SELECT, and the re-score would run against the terms as
    # they were BEFORE the edit — silently scoring the wrong quote.
    session.flush()

    quotation.version += 1
    quotation.last_activity_at = datetime.now(timezone.utc)

    if not needs_rescore:
        # A DRAFT has no approvals to void and no score to invalidate. §7's
        # transition table says DRAFT leaves DRAFT only via `confirm`, so
        # scoring here would move the quote out of DRAFT behind the rep's back.
        return (quotation.risk_score or Decimal(0)), []

    void_approvals(session, quotation.id)
    return rescore(session, quotation, build_snapshot(quotation), actor_id)
