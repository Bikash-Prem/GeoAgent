"""Response operations layer (merged from the GeoAgentic control plane, rebuilt on the incident-aware road graph).

Everything here is computed from the same live graph the decision engine uses, so a new incident, a resolved
incident or a dispatched unit changes dispatch, hospital choice, corridor and coverage consistently.

Explicit assumptions (tunable, surfaced to the UI):
  * Signal controller is SIMULATED. No physical traffic light is controlled.
  * Hospital capacity comes from the hospital desk endpoint (seeded demo values until a hospital updates them).
  * Golden-hour budget = 60 min from call to definitive care; on-scene time defaults to ON_SCENE_MIN.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.algorithms.astar import RoadGraph, build_demo_graph
from app.algorithms.geometry import metres, point_to_polyline_m
from app.models.entities import AuditEvent, Incident, Vehicle
from app.models.operations import DispatchAssignment, Hospital, HospitalAlert
from app.services.risk import M_PER_MIN_FREE_FLOW, IncidentImpact, backup_eta_minutes, to_free_flow_graph

ROAD_KINDS = {"accident", "closure", "traffic"}        # change travel times
DISPATCH_KINDS = {"accident", "medical"}               # need an ambulance
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
GOLDEN_HOUR_MIN = 60.0
ON_SCENE_MIN = 10.0
SIGNAL_WAIT_MIN = 0.5            # assumed mean red-light wait avoided per corridor intersection
SPECIALTY_FOR_KIND = {"accident": "trauma", "medical": "cardiac"}

# Demo junction names for the demo-graph nodes (node H is City General Hospital, not a signal).
JUNCTIONS = {
    "A": "Hudson Circle", "B": "Kasturba Rd", "C": "Cubbon Rd", "D": "Vittal Mallya Rd", "E": "Residency Rd",
    "F": "Richmond Rd", "G": "Brigade Rd", "I": "MG Road", "J": "Queens Rd", "K": "Lalbagh Rd", "L": "Double Rd",
}

HOSPITAL_SEED = [
    dict(id="HOSP-01", name="City General Hospital", lat=12.9720, lon=77.6070, icu_load=0.46, er_load=0.38, oxygen_load=0.24,
         specialties=["trauma", "cardiac", "stroke"], helipad=True),
    dict(id="HOSP-02", name="Cubbon Trauma Centre", lat=12.9765, lon=77.6008, icu_load=0.71, er_load=0.64, oxygen_load=0.35,
         specialties=["trauma", "burns"], helipad=False),
    dict(id="HOSP-03", name="Richmond Heart Institute", lat=12.9645, lon=77.6045, icu_load=0.33, er_load=0.29, oxygen_load=0.2,
         specialties=["cardiac", "stroke"], helipad=False),
    dict(id="HOSP-04", name="Lalbagh Women & Children", lat=12.9645, lon=77.5955, icu_load=0.52, er_load=0.41, oxygen_load=0.28,
         specialties=["paediatric", "maternity"], helipad=False),
]

_corridors: dict[str, dict] = {}


# ───────────────────────────── shared graph helpers ─────────────────────────────
def road_incidents(db: Session) -> list[dict]:
    rows = db.scalars(select(Incident).where(Incident.active.is_(True))).all()
    return [{"id": i.id, "kind": i.kind, "severity": i.severity, "lat": i.lat, "lon": i.lon, "radius_m": i.radius_m}
            for i in rows if i.kind in ROAD_KINDS]


def live_graph(db: Session) -> tuple[RoadGraph, RoadGraph]:
    free = to_free_flow_graph(build_demo_graph())
    return free, IncidentImpact(road_incidents(db)).apply(free)


def travel_minutes(live: RoadGraph, a: tuple[float, float], b: tuple[float, float]) -> float | None:
    """Routed minutes between two arbitrary points: access legs to the nearest graph nodes + live graph path."""
    na, nb = live.nearest_node(*a), live.nearest_node(*b)
    access = (metres(*a, *live.pos[na]) + metres(*b, *live.pos[nb])) / M_PER_MIN_FREE_FLOW
    if na == nb:
        return round(access, 2)
    path, cost = live.astar(na, nb)
    return round(cost + access, 2) if path else None


# ───────────────────────────── hospitals ─────────────────────────────
def seed_hospitals(db: Session) -> None:
    if db.scalar(select(Hospital).limit(1)) is None:
        db.add_all(Hospital(**h) for h in HOSPITAL_SEED)
        db.commit()


def readiness(h: Hospital) -> str:
    if not h.accepting or h.icu_load >= 0.85:
        return "DIVERT"
    return "LIMITED" if h.icu_load >= 0.6 or h.er_load >= 0.75 else "READY"


def hospital_dict(h: Hospital, db: Session | None = None) -> dict:
    out = {"id": h.id, "name": h.name, "lat": h.lat, "lon": h.lon, "icu": round(h.icu_load, 2), "er": round(h.er_load, 2),
           "oxygen": round(h.oxygen_load, 2), "specialties": h.specialties or [], "helipad": h.helipad, "accepting": h.accepting,
           "status": readiness(h), "source": h.source, "updated_at": h.updated_at.isoformat() if h.updated_at else None}
    if db is not None:
        out["inbound"] = db.scalar(select(HospitalAlert.id).where(HospitalAlert.hospital_id == h.id, HospitalAlert.acknowledged.is_(False)).limit(1)) is not None
    return out


def list_hospitals(db: Session) -> list[dict]:
    return [hospital_dict(h, db) for h in db.scalars(select(Hospital).order_by(Hospital.id)).all()]


def update_hospital(db: Session, hospital_id: str, changes: dict) -> dict:
    h = db.get(Hospital, hospital_id)
    if h is None:
        raise ValueError("hospital not found")
    for key, attr in (("icu", "icu_load"), ("er", "er_load"), ("oxygen", "oxygen_load")):
        if changes.get(key) is not None:
            setattr(h, attr, max(0.0, min(1.0, float(changes[key]))))
    if changes.get("accepting") is not None:
        h.accepting = bool(changes["accepting"])
    h.source, h.updated_at = "hospital_desk", datetime.utcnow()
    db.add(AuditEvent(vehicle_id=None, event_type="hospital_capacity_updated", payload={"hospital_id": h.id, **{k: v for k, v in changes.items() if v is not None}}))
    db.commit()
    return hospital_dict(h, db)


def rank_hospitals(db: Session, live: RoadGraph, origin: tuple[float, float], specialty: str | None) -> list[dict]:
    """Transport time + capacity penalty - specialty bonus. Diverting hospitals are listed but never chosen."""
    ranked = []
    for h in db.scalars(select(Hospital)).all():
        minutes = travel_minutes(live, origin, (h.lat, h.lon))
        if minutes is None:
            continue
        status = readiness(h)
        penalty = round(8.0 * max(0.0, h.icu_load - 0.4) ** 2 * 4, 2)  # grows quickly past 40% ICU load
        bonus = 2.0 if specialty and specialty in (h.specialties or []) else 0.0
        reasons = [f"{minutes:.1f} min transport", f"ICU {round(h.icu_load * 100)}% in use"]
        if bonus:
            reasons.append(f"{specialty} capable")
        ranked.append({**hospital_dict(h), "transport_min": minutes, "score": round(minutes + penalty - bonus + (999 if status == "DIVERT" else 0), 2), "reasons": reasons})
    ranked.sort(key=lambda x: x["score"])
    return ranked


# ───────────────────────────── signals & green corridor ─────────────────────────────
def list_signals(vehicle_id: str | None = None) -> list[dict]:
    free = to_free_flow_graph(build_demo_graph())
    corridor = current_corridor(vehicle_id)
    on_path = set(corridor["nodes"]) if corridor else set()
    phase = int(time.time() // 20)
    out = []
    for idx, (node, name) in enumerate(sorted(JUNCTIONS.items())):
        lat, lon = free.pos[node]
        override = node in on_path
        state = "GREEN" if override else ("RED", "GREEN", "AMBER")[(phase + idx) % 3]
        out.append({"id": f"SIG-{node}", "node": node, "name": name, "lat": lat, "lon": lon, "state": state, "overridden": override, "controller": "simulated"})
    return out


def current_corridor(vehicle_id: str | None = None) -> dict | None:
    active = [c for c in _corridors.values() if c["active"] and (vehicle_id is None or c["vehicle_id"] == vehicle_id)]
    return active[-1] if active else None


def activate_corridor(db: Session, vehicle_id: str, recommendation: dict) -> dict:
    route_id = recommendation.get("recommended_route_id") or recommendation["routes"][0]["id"]
    route = next(r for r in recommendation["routes"] if r["id"] == route_id)
    free = to_free_flow_graph(build_demo_graph())
    line = [(p["lat"], p["lon"]) for p in route["points"]]
    # junctions within 60 m of the route line: works for demo-graph routes and real-road provider polylines alike
    nodes = [n for n, (la, lo) in free.pos.items() if point_to_polyline_m(la, lo, line) <= 60]
    junctions = [n for n in nodes if n in JUNCTIONS]
    data = {"id": f"COR-{vehicle_id}", "vehicle_id": vehicle_id, "route_id": route_id, "route_name": route["name"], "decision_id": recommendation.get("decision_id"),
            "active": True, "activated_at": datetime.utcnow().isoformat(), "eta_min": route["eta_min"], "points": route["points"], "nodes": nodes,
            "intersections": len(junctions), "est_wait_avoided_min": round(len(junctions) * SIGNAL_WAIT_MIN, 1),
            "assumption": f"{SIGNAL_WAIT_MIN * 60:.0f} s mean red-light wait per intersection", "controller": "simulated"}
    _corridors[data["id"]] = data
    db.add(AuditEvent(vehicle_id=vehicle_id, event_type="green_corridor_activated", payload={k: v for k, v in data.items() if k != "points"}))
    db.commit()
    return data


def deactivate_corridor(db: Session, corridor_id: str) -> dict:
    data = _corridors.get(corridor_id)
    if not data:
        raise ValueError("corridor not found")
    data.update(active=False, deactivated_at=datetime.utcnow().isoformat())
    db.add(AuditEvent(vehicle_id=data["vehicle_id"], event_type="green_corridor_deactivated", payload={"id": corridor_id}))
    db.commit()
    return data


# ───────────────────────────── coverage ─────────────────────────────
def coverage(db: Session, target_min: float, exclude: set[str] | None = None, live: RoadGraph | None = None, grid: int = 9) -> dict:
    """Share of the service area an AVAILABLE unit can reach within target_min (grid of demand points)."""
    free, live2 = live_graph(db) if live is None else (None, live)
    exclude = exclude or set()
    units = [v for v in db.scalars(select(Vehicle).where(Vehicle.status == "available")).all() if v.id not in exclude]
    lats = [p[0] for p in live2.pos.values()]
    lons = [p[1] for p in live2.pos.values()]
    pad_lat, pad_lon = 0.0015, 0.0015
    lo_lat, hi_lat, lo_lon, hi_lon = min(lats) - pad_lat, max(lats) + pad_lat, min(lons) - pad_lon, max(lons) + pad_lon
    step_lat, step_lon = (hi_lat - lo_lat) / grid, (hi_lon - lo_lon) / grid
    cells, covered = [], 0
    for r in range(grid):
        for c in range(grid):
            lat, lon = lo_lat + (r + 0.5) * step_lat, lo_lon + (c + 0.5) * step_lon
            best, best_unit = None, None
            for u in units:
                t = travel_minutes(live2, (u.lat, u.lon), (lat, lon))
                if t is not None and (best is None or t < best):
                    best, best_unit = t, u.id
            ok = best is not None and best <= target_min
            covered += ok
            cells.append({"lat": round(lat, 6), "lon": round(lon, 6), "eta_min": best, "unit": best_unit, "covered": ok,
                          "bounds": [[lo_lat + r * step_lat, lo_lon + c * step_lon], [lo_lat + (r + 1) * step_lat, lo_lon + (c + 1) * step_lon]]})
    etas = [x["eta_min"] for x in cells if x["eta_min"] is not None]
    return {"target_min": target_min, "available_units": [u.id for u in units], "coverage_pct": round(100 * covered / len(cells), 1),
            "mean_eta_min": round(sum(etas) / len(etas), 2) if etas else None, "worst_eta_min": max(etas) if etas else None, "cells": cells}


def coverage_impact(db: Session, target_min: float) -> list[dict]:
    """What happens to coverage if each available unit is committed: used to protect the region before dispatching."""
    _, live = live_graph(db)
    base = coverage(db, target_min, live=live)
    out = []
    for vid in base["available_units"]:
        after = coverage(db, target_min, exclude={vid}, live=live)
        out.append({"vehicle_id": vid, "coverage_after_pct": after["coverage_pct"], "drop_pct": round(base["coverage_pct"] - after["coverage_pct"], 1),
                    "worst_eta_after_min": after["worst_eta_min"]})
    return out


# ───────────────────────────── mission route ─────────────────────────────
def mission_route_points(db: Session, origin: tuple[float, float], incident: tuple[float, float], hospital: tuple[float, float] | None) -> list[dict]:
    """Build a deterministic road-graph polyline for the local mission simulator."""
    _, live = live_graph(db)
    def leg(a, b):
        na, nb = live.nearest_node(*a), live.nearest_node(*b)
        path, _ = live.astar(na, nb)
        pts = [live.pos[n] for n in (path or [na, nb])]
        return [{"lat": p[0], "lon": p[1]} for p in pts]
    first = leg(origin, incident)
    second = leg(incident, hospital) if hospital else []
    merged = first + (second[1:] if second else [])
    return merged or [{"lat": origin[0], "lon": origin[1]}, {"lat": incident[0], "lon": incident[1]}]


# ───────────────────────────── dispatch ─────────────────────────────
def _pick_incident(db: Session, incident_id: str | None) -> Incident:
    if incident_id:
        inc = db.get(Incident, incident_id)
        if inc is None or not inc.active:
            raise ValueError("incident not found or already resolved")
        return inc
    assigned = {a.incident_id for a in db.scalars(select(DispatchAssignment).where(DispatchAssignment.status == "assigned")).all()}
    open_calls = [i for i in db.scalars(select(Incident).where(Incident.active.is_(True))).all() if i.kind in DISPATCH_KINDS and i.id not in assigned]
    if not open_calls:
        raise ValueError("no open emergency call needs a unit")
    return sorted(open_calls, key=lambda i: (-SEVERITY_RANK.get(i.severity, 0), -(i.created_at or datetime.min).timestamp()))[0]


def dispatch_plan(db: Session, incident_id: str | None = None, coverage_target_min: float = 8.0) -> dict:
    incident = _pick_incident(db, incident_id)
    _, live = live_graph(db)
    units = db.scalars(select(Vehicle).where(Vehicle.status == "available")).all()
    if not units:
        raise ValueError("no available ambulance")
    impact = {x["vehicle_id"]: x for x in coverage_impact(db, coverage_target_min)}
    options = []
    for u in units:
        eta = travel_minutes(live, (u.lat, u.lon), (incident.lat, incident.lon))
        if eta is None:
            continue
        eta += 1.0  # turn-out allowance, same as the decision engine
        drop = impact.get(u.id, {}).get("drop_pct", 0.0)
        options.append({"vehicle_id": u.id, "name": u.name, "eta_min": round(eta, 2), "coverage_drop_pct": drop,
                        "score": round(eta + 0.05 * drop, 2)})  # small tie-breaker that protects coverage
    if not options:
        raise ValueError("no ambulance can reach the incident")
    options.sort(key=lambda o: o["score"])
    chosen = options[0]
    specialty = SPECIALTY_FOR_KIND.get(incident.kind)
    hospitals = rank_hospitals(db, live, (incident.lat, incident.lon), specialty)
    hospital = hospitals[0] if hospitals else None
    transport = hospital["transport_min"] if hospital else 0.0
    total = chosen["eta_min"] + ON_SCENE_MIN + transport
    margin = round(options[1]["eta_min"] - chosen["eta_min"], 2) if len(options) > 1 else None
    return {
        "incident": {"id": incident.id, "title": incident.title, "kind": incident.kind, "severity": incident.severity, "lat": incident.lat, "lon": incident.lon},
        "ambulance": {"id": chosen["vehicle_id"], "name": chosen["name"]}, "unit_options": options,
        "hospital": hospital, "hospital_options": hospitals[:4], "required_specialty": specialty,
        "response_eta_min": chosen["eta_min"], "transport_min": transport, "on_scene_min": ON_SCENE_MIN,
        "call_to_care_min": round(total, 1), "golden_hour_remaining_min": round(GOLDEN_HOUR_MIN - total, 1),
        "decision_margin_min": margin, "coverage_after_pct": impact.get(chosen["vehicle_id"], {}).get("coverage_after_pct"),
        "model": "routed ETA on the incident-aware graph + capacity-weighted hospital choice (deterministic)",
        "requires_human_approval": True,
    }


def execute_dispatch(db: Session, incident_id: str | None, actor: str = "dispatcher") -> dict:
    plan = dispatch_plan(db, incident_id)
    vehicle = db.get(Vehicle, plan["ambulance"]["id"])
    incident = db.get(Incident, plan["incident"]["id"])
    hospital = db.get(Hospital, plan["hospital"]["id"]) if plan.get("hospital") else None
    vehicle.status = "active"
    vehicle.hospital = hospital.name if hospital else None
    vehicle.updated_at = datetime.utcnow()
    route_points = mission_route_points(db, (vehicle.lat, vehicle.lon), (incident.lat, incident.lon), (hospital.lat, hospital.lon) if hospital else None)
    assignment = DispatchAssignment(id=f"DSP-{uuid4().hex[:8].upper()}", incident_id=plan["incident"]["id"], vehicle_id=vehicle.id,
                                    hospital_id=hospital.id if hospital else None, plan={**plan, "route_points": route_points, "progress": 0.0, "elapsed_min": 0.0,
                                    "phase": "dispatched", "eta_min": plan["call_to_care_min"], "priority": plan["incident"]["severity"], "condition": plan["incident"]["kind"]})
    db.add(assignment)
    db.add(AuditEvent(vehicle_id=vehicle.id, event_type="dispatch_executed", payload={"assignment_id": assignment.id, "incident_id": plan["incident"]["id"], "hospital": vehicle.hospital, "eta_min": plan["response_eta_min"], "actor": actor}))
    if hospital:
        db.add(HospitalAlert(hospital_id=hospital.id, vehicle_id=vehicle.id, incident_id=plan["incident"]["id"], stage="pre_alert",
                             priority=plan["incident"]["severity"], condition=plan["incident"]["kind"],
                             eta_min=round(plan["call_to_care_min"], 1), note=f"{plan['incident']['title']} · {vehicle.name} assigned"))
    db.commit()
    # Dispatch automatically establishes the simulated green corridor.
    try:
        from app.services.engine import GeoAgentEngine
        rec = GeoAgentEngine(db).recommendation(vehicle.id)
        corridor = activate_corridor(db, vehicle.id, rec)
        corridor = {**corridor, "signals": list_signals(vehicle.id)}
    except Exception:
        corridor = None
    from app.services.mission import mission_state
    return {**plan, "assignment_id": assignment.id, "status": "assigned", "mission": mission_state(db, assignment), "corridor": corridor}

def list_assignments(db: Session) -> list[dict]:
    rows = db.scalars(select(DispatchAssignment).order_by(desc(DispatchAssignment.created_at)).limit(20)).all()
    return [{"id": a.id, "incident_id": a.incident_id, "vehicle_id": a.vehicle_id, "hospital_id": a.hospital_id, "status": a.status,
             "response_eta_min": a.plan.get("response_eta_min"), "created_at": a.created_at.isoformat()} for a in rows]


def complete_assignment(db: Session, assignment_id: str) -> dict:
    a = db.get(DispatchAssignment, assignment_id)
    if a is None:
        raise ValueError("assignment not found")
    a.status = "completed"
    v = db.get(Vehicle, a.vehicle_id)
    if v:
        v.status, v.hospital = "available", None
    db.add(AuditEvent(vehicle_id=a.vehicle_id, event_type="assignment_completed", payload={"assignment_id": a.id}))
    db.commit()
    return {"id": a.id, "status": a.status}


# ───────────────────────────── hospital alerts ─────────────────────────────
def alert_dict(a: HospitalAlert) -> dict:
    return {"id": a.id, "hospital_id": a.hospital_id, "vehicle_id": a.vehicle_id, "incident_id": a.incident_id, "stage": a.stage, "priority": a.priority,
            "condition": a.condition, "eta_min": a.eta_min, "note": a.note, "acknowledged": a.acknowledged, "acknowledged_by": a.acknowledged_by,
            "created_at": a.created_at.isoformat(), "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None}


def send_alert(db: Session, payload: dict) -> dict:
    if db.get(Hospital, payload.get("hospital_id")) is None:
        raise ValueError("hospital not found")
    a = HospitalAlert(hospital_id=payload["hospital_id"], vehicle_id=payload.get("vehicle_id"), incident_id=payload.get("incident_id"),
                      stage=payload.get("stage", "en_route"), priority=payload.get("priority", "high"), condition=payload.get("condition", "unknown"),
                      eta_min=payload.get("eta_min"), note=payload.get("note"))
    db.add(a)
    db.add(AuditEvent(vehicle_id=a.vehicle_id, event_type="hospital_alert_sent", payload={"hospital_id": a.hospital_id, "stage": a.stage, "eta_min": a.eta_min}))
    db.commit()
    return alert_dict(a)


def list_alerts(db: Session, hospital_id: str | None = None) -> list[dict]:
    q = select(HospitalAlert).order_by(desc(HospitalAlert.created_at)).limit(30)
    if hospital_id:
        q = q.where(HospitalAlert.hospital_id == hospital_id)
    return [alert_dict(a) for a in db.scalars(q).all()]


def acknowledge_alert(db: Session, alert_id: int, actor: str) -> dict:
    a = db.get(HospitalAlert, alert_id)
    if a is None:
        raise ValueError("alert not found")
    a.acknowledged, a.acknowledged_by, a.acknowledged_at = True, actor, datetime.utcnow()
    db.add(AuditEvent(vehicle_id=a.vehicle_id, event_type="hospital_alert_acknowledged", payload={"alert_id": a.id, "hospital_id": a.hospital_id, "by": actor}))
    db.commit()
    return alert_dict(a)


def recent_cutoff(hours: float) -> datetime:
    return datetime.utcnow() - timedelta(hours=hours)
