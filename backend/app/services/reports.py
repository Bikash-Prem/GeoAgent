"""Shift report and exports, computed from the persisted decision trace and audit log (nothing simulated)."""
from __future__ import annotations

import csv
import io
import statistics
from collections import Counter

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, Incident
from app.models.intelligence import DecisionRecord, DecisionTraceRecord
from app.models.operations import DispatchAssignment, HospitalAlert
from app.services.operations import recent_cutoff


def _approval_seconds(db: Session, decision: DecisionRecord) -> float | None:
    """Time from the decision being generated to the dispatcher's approve/reject: measured, not estimated."""
    event = db.scalars(select(DecisionTraceRecord).where(DecisionTraceRecord.decision_id == decision.id,
                                                         DecisionTraceRecord.event_type == "human_approval").order_by(DecisionTraceRecord.created_at)).first()
    if event is None or decision.created_at is None:
        return None
    return max(0.0, (event.created_at - decision.created_at).total_seconds())


def list_decisions(db: Session, limit: int = 25) -> list[dict]:
    rows = db.scalars(select(DecisionRecord).order_by(desc(DecisionRecord.created_at)).limit(limit)).all()
    out = []
    for d in rows:
        ra = d.recommended_action or {}
        eta = ra.get("eta_uncertainty") or {}
        out.append({"decision_id": d.id, "vehicle_id": d.vehicle_id, "status": d.status, "action": ra.get("action"),
                    "eta_min": ra.get("expected_eta_minutes"), "eta_lower": eta.get("lower"), "eta_upper": eta.get("upper"),
                    "risk": (ra.get("risk") or {}).get("level"), "reasoning": d.reasoning, "created_at": d.created_at.isoformat(),
                    "time_to_decision_s": _approval_seconds(db, d)})
    return out


def shift_report(db: Session, hours: float = 12.0) -> dict:
    since = recent_cutoff(hours)
    decisions = db.scalars(select(DecisionRecord).where(DecisionRecord.created_at >= since)).all()
    status = Counter(d.status for d in decisions)
    reviewed = [d for d in decisions if d.status in ("approved", "rejected")]
    ttd = [t for t in (_approval_seconds(db, d) for d in reviewed) if t is not None]
    actions = Counter((d.recommended_action or {}).get("action", "unknown") for d in decisions)
    etas = [(d.recommended_action or {}).get("expected_eta_minutes") for d in decisions]
    etas = [e for e in etas if isinstance(e, (int, float))]
    events = Counter(e.event_type for e in db.scalars(select(AuditEvent).where(AuditEvent.created_at >= since)).all())
    alerts = db.scalars(select(HospitalAlert).where(HospitalAlert.created_at >= since)).all()
    ack = [(a.acknowledged_at - a.created_at).total_seconds() for a in alerts if a.acknowledged_at]
    incidents_new = db.scalars(select(Incident).where(Incident.created_at >= since)).all()
    return {
        "window_hours": hours, "since": since.isoformat(),
        "decisions": {"total": len(decisions), "approved": status.get("approved", 0), "rejected": status.get("rejected", 0), "pending": status.get("pending", 0),
                      "approval_rate_pct": round(100 * status.get("approved", 0) / len(reviewed), 1) if reviewed else None,
                      "median_time_to_decision_s": round(statistics.median(ttd), 1) if ttd else None,
                      "by_action": dict(actions), "mean_predicted_eta_min": round(statistics.mean(etas), 2) if etas else None},
        "incidents": {"logged": len(incidents_new), "resolved": events.get("incident_resolved", 0), "active": sum(i.active for i in incidents_new)},
        "operations": {"dispatches": len(db.scalars(select(DispatchAssignment).where(DispatchAssignment.created_at >= since)).all()),
                       "green_corridors": events.get("green_corridor_activated", 0), "air_rescues": events.get("air_rescue_activated", 0),
                       "what_if_runs": events.get("whatif_run", 0)},
        "hospital_alerts": {"sent": len(alerts), "acknowledged": len(ack), "median_ack_s": round(statistics.median(ack), 1) if ack else None},
        "note": "Every figure is computed from this deployment's own decision trace and audit log.",
    }


def decisions_csv(db: Session, limit: int = 500) -> str:
    buf = io.StringIO()
    rows = list_decisions(db, limit)
    fields = ["decision_id", "vehicle_id", "created_at", "action", "eta_min", "eta_lower", "eta_upper", "risk", "status", "time_to_decision_s", "reasoning"]
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
