"""FP-Growth affinity precompute.  Spec §5.4.

Runs at SEED time and writes `product_affinity`. §13 lists "running FP-Growth
or Isolation Forest inside a request handler" as an anti-pattern, so this is
deliberately a batch job: the request path does one indexed query and a pass of
arithmetic (`app/domain/advisor.py`).

Deliberately NOT in app/domain/: it imports pandas/mlxtend and is therefore not
pure. The domain only ever sees the persisted numbers, passed in.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import QuoteState
from app.models.tables import ProductAffinity, Quotation, QuoteLine

MIN_SUPPORT = 0.02
MIN_CONFIDENCE = 0.3
CLOSED_STATES = (QuoteState.PAID, QuoteState.INVOICED, QuoteState.CONFIRMED)


def historical_baskets(session: Session) -> list[set[int]]:
    """One basket per closed order — the corpus FP-Growth mines."""
    rows = session.execute(
        select(QuoteLine.quotation_id, QuoteLine.product_id)
        .join(Quotation, QuoteLine.quotation_id == Quotation.id)
        .where(Quotation.state.in_(CLOSED_STATES))
        .order_by(QuoteLine.quotation_id, QuoteLine.product_id)
    ).all()

    baskets: dict[int, set[int]] = {}
    for quotation_id, product_id in rows:
        baskets.setdefault(quotation_id, set()).add(product_id)
    return [b for b in baskets.values() if len(b) >= 2]


def compute(session: Session) -> int:
    """Mine association rules and persist them. Returns the row count written.

    Degrades honestly: if mlxtend/pandas are unavailable, or the corpus is too
    thin to produce rules, it writes nothing and the Advisor simply has no
    candidates — it never falls back to invented numbers.
    """
    baskets = historical_baskets(session)
    if len(baskets) < 10:
        return 0

    try:
        import pandas as pd
        from mlxtend.frequent_patterns import association_rules, fpgrowth
    except ImportError:
        return 0

    products = sorted({p for b in baskets for p in b})
    matrix = pd.DataFrame(
        [[p in basket for p in products] for basket in baskets],
        columns=products,
    )

    frequent = fpgrowth(matrix, min_support=MIN_SUPPORT, use_colnames=True)
    if frequent.empty:
        return 0

    rules = association_rules(
        frequent, metric="confidence", min_threshold=MIN_CONFIDENCE
    )
    if rules.empty:
        return 0

    session.query(ProductAffinity).delete()
    session.flush()

    written = 0
    seen: set[tuple[int, int]] = set()
    for row in rules.itertuples():
        # keep 1->1 edges: the request-time lookup is "given this line, what
        # else?", which is a single-antecedent question
        if len(row.antecedents) != 1 or len(row.consequents) != 1:
            continue
        antecedent = int(next(iter(row.antecedents)))
        consequent = int(next(iter(row.consequents)))
        if antecedent == consequent or (antecedent, consequent) in seen:
            continue
        seen.add((antecedent, consequent))
        session.add(
            ProductAffinity(
                antecedent_id=antecedent,
                consequent_id=consequent,
                support=Decimal(str(round(float(row.support), 4))),
                confidence=Decimal(str(round(float(row.confidence), 4))),
                lift=Decimal(str(round(float(row.lift), 4))),
            )
        )
        written += 1

    session.flush()
    return written
