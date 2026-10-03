"""What-If Lab: run the REAL planner / predictor / policy on a modified copy of the live situation.

Nothing is written to the decision tables: the live state is never mutated. The result compares the baseline
recommendation with the scenario recommendation so the dispatcher can see how the decision would change.
"""
from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, Vehicle
from app.services.counterfactual import CounterfactualActionEngine
from app.services.planner import display_routes, plan_routes
from app.services.policy import RuleBasedPolicy
from app.services.situation import SituationEngine

PRESETS = {
    "accident_congestion": "A serious accident blocks the middle of the ambulance's current route.",
    "road_closure": "The road the recommended route depends on is closed.",
    "traffic_spike": "Every reported traffic jam doubles in size, and a new one forms on the current route.",
    "competing_emergencies": "A competing call takes the nearest available backup unit.",
    "clear_roads": "All reported road incidents are cleared.",
}


def _midpoint(points: list[dict], frac: float = 0.5) -> dict:
    """Point at roughly `frac` of the polyline (by segment index), on the middle of that segment."""
    if len(points) < 2:
        return points[0]
    i = min(len(points) - 2, max(0, int((len(points) - 1) * frac)))
    a, b = points[i], points[i + 1]
    return {"lat": (a["lat"] + b["lat"]) / 2, "lon": (a["lon"] + b["lon"]) / 2}


def _run(situation, incidents, vehicle_pos, backups, target):
    sit = replace(situation, incidents=incidents)
    plan = plan_routes(incidents, vehicle_pos, backups)
    actions = CounterfactualActionEngine().evaluate(sit, plan.routes, plan.backup_id, plan.backup_eta)
    policy = RuleBasedPolicy(target)
    rec = policy.select(actions)
    routes = display_routes(plan, actions)
    chosen = next((r for r in routes if r["id"] == rec.route_id), routes[0])
    return {
        "action": rec.action_type, "route_id": rec.route_id, "route_name": chosen["name"],
        "eta_min": round(rec.eta.value, 2), "eta_lower": round(rec.eta.lower, 2), "eta_upper": round(rec.eta.upper, 2),
        "risk": chosen["risk"], "risk_score": chosen["risk_score"], "delay_probability": round(rec.delay_probability, 3),
        "backup_vehicle_id": rec.backup_vehicle_id, "backup_considered": plan.backup_id, "backup_eta_min": plan.backup_eta,
        "routes": routes, "incidents": incidents,
    }


def run_whatif(db: Session, vehicle_id: str, preset: str | None, extra: list[dict] | None, target: float) -> dict:
    situation = SituationEngine(db).build(vehicle_id)
    vehicle = db.get(Vehicle, vehicle_id)
    pos = (vehicle.lat, vehicle.lon)
    backups = [(v.id, (v.lat, v.lon)) for v in db.scalars(select(Vehicle).where(Vehicle.status == "available", Vehicle.id != vehicle_id).order_by(Vehicle.id)).all()]
    base_incidents = list(situation.incidents)
    baseline = _run(situation, base_incidents, pos, backups, target)

    incidents, scen_backups, injected, removed = list(base_incidents), list(backups), [], []
    current = baseline["routes"][0]
    chosen = next(r for r in baseline["routes"] if r["id"] == baseline["route_id"])
    if preset == "accident_congestion":
        injected.append({"id": "WHATIF-ACC", "kind": "accident", "severity": "high", "radius_m": 260, **_midpoint(chosen["points"], 0.3)})
    elif preset == "road_closure":
        injected.append({"id": "WHATIF-CLS", "kind": "closure", "severity": "high", "radius_m": 200, **_midpoint(chosen["points"])})
    elif preset == "traffic_spike":
        incidents = [{**i, "severity": "high", "radius_m": i["radius_m"] * 2} if i["kind"] == "traffic" else i for i in incidents]
        injected.append({"id": "WHATIF-TRF", "kind": "traffic", "severity": "high", "radius_m": 320, **_midpoint(current["points"])})
    elif preset == "competing_emergencies":
        if baseline["backup_considered"]:
            removed.append(baseline["backup_considered"])
            scen_backups = [b for b in backups if b[0] != baseline["backup_considered"]]
    elif preset == "clear_roads":
        removed.extend(i["id"] for i in incidents)
        incidents = []
    elif preset not in (None, "custom"):
        raise ValueError(f"unknown scenario '{preset}'")
    for i, inc in enumerate(extra or []):
        injected.append({"id": inc.get("id") or f"WHATIF-{i + 1}", "kind": inc.get("kind", "accident"), "severity": inc.get("severity", "high"),
                         "radius_m": float(inc.get("radius_m", 220)), "lat": float(inc["lat"]), "lon": float(inc["lon"])})
    scenario = _run(situation, incidents + injected, pos, scen_backups, target)

    changed = scenario["action"] != baseline["action"] or scenario["route_id"] != baseline["route_id"]
    delta = round(scenario["eta_min"] - baseline["eta_min"], 2)
    summary = (f"The recommendation changes from {baseline['action'].replace('_', ' ')} on {baseline['route_name']} to "
               f"{scenario['action'].replace('_', ' ')} on {scenario['route_name']}." if changed else
               f"The recommendation holds: {baseline['action'].replace('_', ' ')} on {baseline['route_name']}.")
    if removed and preset == "competing_emergencies":
        nxt = scenario["backup_considered"]
        summary += f" Backup pool loses {removed[0]}; " + (f"next backup is {nxt} at {scenario['backup_eta_min']:.1f} min (was {baseline['backup_eta_min']:.1f} min)." if nxt else "no backup remains in the region.")
    summary += f" Expected hospital arrival {'+' if delta >= 0 else ''}{delta:.1f} min ({scenario['eta_min']:.1f} min, interval {scenario['eta_lower']:.1f}-{scenario['eta_upper']:.1f})."
    db.add(AuditEvent(vehicle_id=vehicle_id, event_type="whatif_run", payload={"preset": preset, "changed": changed, "eta_delta_min": delta}))
    db.commit()
    return {"vehicle_id": vehicle_id, "preset": preset, "description": PRESETS.get(preset or "", "Custom incidents injected by the dispatcher."),
            "baseline": baseline, "scenario": scenario, "injected": injected, "removed": removed,
            "decision_changed": changed, "eta_delta_min": delta, "summary": summary, "persisted_decision": False}
