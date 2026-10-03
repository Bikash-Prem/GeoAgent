"""Deterministic local mission lifecycle used by the company demo.

The mission clock is accelerated for demonstration: one control-loop tick advances
roughly one mission minute. This keeps the UI genuinely stateful without pretending
that a local demo is receiving real ambulance GPS.
"""
from __future__ import annotations

from datetime import datetime
from math import atan2, degrees
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.algorithms.geometry import metres
from app.models.entities import AuditEvent, Incident, Vehicle
from app.models.operations import DispatchAssignment, HospitalAlert, Hospital
from app.services.operations import deactivate_corridor, current_corridor

DEMO_MINUTES_PER_TICK = 1.0
PROGRESS_PER_TICK = 0.08
HOSPITAL_UPDATE_AFTER_MIN = 5.0


def _interpolate(points: list[dict], progress: float) -> tuple[float, float, float]:
    if not points:
        return 0.0, 0.0, 0.0
    if len(points) == 1:
        return points[0]["lat"], points[0]["lon"], 0.0
    lengths = [metres(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(points, points[1:])]
    total = sum(lengths) or 1.0
    target = max(0.0, min(1.0, progress)) * total
    walked = 0.0
    for idx, length in enumerate(lengths):
        if walked + length >= target:
            f = (target - walked) / max(length, 1.0)
            a, b = points[idx], points[idx + 1]
            lat = a["lat"] + (b["lat"] - a["lat"]) * f
            lon = a["lon"] + (b["lon"] - a["lon"]) * f
            heading = degrees(atan2(b["lon"] - a["lon"], b["lat"] - a["lat"])) % 360
            return lat, lon, heading
        walked += length
    a, b = points[-2], points[-1]
    return b["lat"], b["lon"], degrees(atan2(b["lon"] - a["lon"], b["lat"] - a["lat"])) % 360


def mission_state(db: Session, assignment: DispatchAssignment | None) -> dict | None:
    if assignment is None:
        return None
    plan = assignment.plan or {}
    progress = float(plan.get("progress", 0.0))
    phase = plan.get("phase", "dispatched")
    vehicle = db.get(Vehicle, assignment.vehicle_id)
    incident = db.get(Incident, assignment.incident_id)
    hospital = db.get(Hospital, assignment.hospital_id) if assignment.hospital_id else None
    return {
        "assignment_id": assignment.id,
        "incident_id": assignment.incident_id,
        "vehicle_id": assignment.vehicle_id,
        "vehicle_name": vehicle.name if vehicle else assignment.vehicle_id,
        "hospital_id": assignment.hospital_id,
        "hospital_name": hospital.name if hospital else None,
        "status": assignment.status,
        "phase": phase,
        "progress": round(progress * 100, 1),
        "mission_elapsed_min": round(float(plan.get("elapsed_min", 0.0)), 1),
        "eta_min": round(max(0.0, float(plan.get("eta_min", 0.0)) * (1.0 - progress)), 1),
        "route_points": plan.get("route_points", []),
        "incident": {"id": incident.id, "title": incident.title, "lat": incident.lat, "lon": incident.lon} if incident else None,
        "updated_at": plan.get("updated_at"),
    }


def active_assignment(db: Session) -> DispatchAssignment | None:
    return db.scalars(select(DispatchAssignment).where(DispatchAssignment.status == "assigned").order_by(DispatchAssignment.created_at.desc())).first()


def advance(db: Session) -> dict | None:
    assignment = active_assignment(db)
    if assignment is None:
        return None
    plan = dict(assignment.plan or {})
    old_phase = plan.get("phase", "dispatched")
    progress = min(1.0, float(plan.get("progress", 0.0)) + PROGRESS_PER_TICK)
    elapsed = float(plan.get("elapsed_min", 0.0)) + DEMO_MINUTES_PER_TICK
    phase = "en_route" if progress < 0.32 else "on_scene" if progress < 0.40 else "transporting" if progress < 0.92 else "arriving"
    if progress >= 1.0:
        phase = "arrived"

    points = plan.get("route_points", [])
    vehicle = db.get(Vehicle, assignment.vehicle_id)
    if vehicle and points:
        lat, lon, heading = _interpolate(points, progress)
        speed = 42.0 if phase not in ("on_scene", "arrived") else 8.0
        vehicle.lat, vehicle.lon, vehicle.heading, vehicle.speed_kmh, vehicle.updated_at = lat, lon, heading, speed, datetime.utcnow()

    plan.update({"progress": progress, "elapsed_min": elapsed, "phase": phase, "updated_at": datetime.utcnow().isoformat()})
    assignment.plan = plan

    if old_phase != phase:
        db.add(AuditEvent(vehicle_id=assignment.vehicle_id, event_type="mission_phase_changed", payload={"assignment_id": assignment.id, "from": old_phase, "to": phase, "elapsed_min": elapsed}))

    # Hospital alert #2 is genuinely automatic in the accelerated demo clock.
    if elapsed >= HOSPITAL_UPDATE_AFTER_MIN and not plan.get("en_route_alert_sent") and assignment.hospital_id:
        db.add(HospitalAlert(hospital_id=assignment.hospital_id, vehicle_id=assignment.vehicle_id, incident_id=assignment.incident_id,
                             stage="en_route", priority=plan.get("priority", "high"), condition=plan.get("condition", "unknown"),
                             eta_min=round(max(1.0, float(plan.get("eta_min", 0.0)) * (1.0 - progress)), 1),
                             note="Automated en-route update: patient transport is active."))
        db.add(AuditEvent(vehicle_id=assignment.vehicle_id, event_type="hospital_en_route_alert_auto", payload={"assignment_id": assignment.id, "hospital_id": assignment.hospital_id, "elapsed_min": elapsed}))
        plan["en_route_alert_sent"] = True

    if progress >= 1.0:
        assignment.status = "completed"
        if vehicle:
            vehicle.status = "available"
            vehicle.hospital = None
        incident = db.get(Incident, assignment.incident_id)
        if incident:
            incident.active = False
        if assignment.hospital_id:
            db.add(HospitalAlert(hospital_id=assignment.hospital_id, vehicle_id=assignment.vehicle_id, incident_id=assignment.incident_id,
                                 stage="arrived", priority=plan.get("priority", "high"), condition=plan.get("condition", "unknown"), eta_min=0,
                                 note="Ambulance arrived at receiving hospital."))
        corridor = current_corridor(assignment.vehicle_id)
        if corridor:
            deactivate_corridor(db, corridor["id"])
        db.add(AuditEvent(vehicle_id=assignment.vehicle_id, event_type="mission_completed", payload={"assignment_id": assignment.id, "incident_id": assignment.incident_id}))
    db.commit()
    db.refresh(assignment)
    return mission_state(db, assignment)
