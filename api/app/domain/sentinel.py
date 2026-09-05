"""Deal health & anomaly detection.  Spec §5.5.

TIER 1 — proposals only.  Nothing here may write a monetary field or drive a
state transition (§8).  Output goes to alert/proposal tables.

Three detectors; alert only when >=2 agree, EXCEPT stalled-deal which stands
alone.  Isolation Forest is a secondary opinion only, never a sole reason.
"""

from __future__ import annotations

from datetime import date
from statistics import median

from app.domain.types import Decision, SentinelSnapshot

ENGINE_VERSION = "sentinel/1.0.0"

Z_THRESHOLD = 3.5
MIN_HISTORY_FOR_REP = 8  # below this, fall back to team history (§5.5)


def robust_z(x: float, history: list[float]) -> float:
    """Median/MAD based z-score. Resistant to the outliers we are hunting.

    0.6745 is the consistency constant making MAD a normal-sigma estimate.
    """
    if not history:
        return 0.0
    med = median(history)
    mad = median([abs(h - med) for h in history]) or 1e-9
    return 0.6745 * (x - med) / mad


def effective_history(snap: SentinelSnapshot) -> tuple[list[float], str]:
    """Small-n guard: a rep with <8 quotes is scored against the TEAM median.

    Without this, every new rep's second quote reads as an anomaly.
    """
    if len(snap.rep_discount_history) < MIN_HISTORY_FOR_REP:
        return snap.team_discount_history, "team"
    return snap.rep_discount_history, "rep"


def detect_stalled(snap: SentinelSnapshot) -> bool:
    return (snap.as_of - snap.last_activity_at).days > snap.stall_days


def detect_discount_anomaly(snap: SentinelSnapshot) -> tuple[bool, float, str]:
    history, source = effective_history(snap)
    z = robust_z(snap.discount_pct, history)
    return abs(z) > Z_THRESHOLD, z, source


def detect_delivery_slippage(snap: SentinelSnapshot) -> bool:
    if snap.promised_date is None or snap.earliest_feasible_date is None:
        return False
    return snap.promised_date < snap.earliest_feasible_date


def decide(snapshot: SentinelSnapshot) -> Decision:
    stalled = detect_stalled(snapshot)
    anomalous, z, source = detect_discount_anomaly(snapshot)
    slipping = detect_delivery_slippage(snapshot)

    # Isolation Forest is a SECONDARY signal: it can help reach the >=2
    # consensus, but can never be the sole reason for an alert.
    iforest = bool(snapshot.isolation_forest_outlier)

    primary = {"discount_anomaly": anomalous, "delivery_slippage": slipping}
    agreeing = [k for k, v in primary.items() if v]
    votes = len(agreeing) + (1 if iforest else 0)

    consensus_alert = votes >= 2 and len(agreeing) >= 1
    alert = consensus_alert or stalled

    explanation: list[str] = []
    if stalled:
        explanation.append(
            f"Stalled: no activity since {snapshot.last_activity_at} "
            f"({(snapshot.as_of - snapshot.last_activity_at).days} days "
            f"> {snapshot.stall_days}) — stands alone."
        )
    if anomalous:
        explanation.append(
            f"Discount {snapshot.discount_pct}% is robust-z {z:.2f} "
            f"against the {source} history (threshold {Z_THRESHOLD})."
        )
    if slipping:
        explanation.append(
            f"Promised {snapshot.promised_date} is before the earliest "
            f"feasible {snapshot.earliest_feasible_date}."
        )
    if iforest:
        explanation.append("Isolation Forest flags this deal (secondary signal only).")
    if not alert:
        explanation.append("No alert: fewer than two detectors agree.")

    output = {
        "alert": alert,
        "stalled": stalled,
        "discount_anomaly": anomalous,
        "robust_z": round(z, 2),
        "history_source": source,
        "delivery_slippage": slipping,
        "isolation_forest_outlier": iforest,
        "votes": votes,
        "tier": 1,
        "writes_state": False,
    }
    return Decision(
        output=output,
        engine_version=ENGINE_VERSION,
        input_hash=snapshot.input_hash(),
        explanation=explanation,
    )
