"""Route planning shared by the live engine and the offline benchmark (pure Python, no DB).

planned route  = the free-flow shortest path the unit is presumably following (what it was dispatched on)
alternatives   = best routes under LIVE conditions (incident slow-downs applied)
Every route is scored under live conditions, so 'continue' is evaluated honestly instead of assumed fine.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.algorithms.astar import RoadGraph, build_demo_graph
from app.algorithms.routes import k_routes
from app.services.risk import IncidentImpact, backup_eta_minutes, risk_label, route_metrics, to_free_flow_graph

HOSPITAL_NODE = "H"  # demo-graph node that represents City General Hospital


@dataclass
class Plan:
    routes: list[dict]
    free_flow: RoadGraph
    live: RoadGraph
    impact: IncidentImpact
    start: str
    goal: str
    backup_id: str | None = None
    backup_eta: float | None = None
    baseline_min: float = 0.0
    backups_considered: list[dict] = field(default_factory=list)


def _explain(index: int, m: dict, baseline: float, planned_m: dict) -> str:
    hit = ", ".join(m["incidents_hit"])
    if index == 0:
        if hit:
            return f"Planned path crosses {hit}: +{m['extra_min']:.1f} min of live slow-down over free-flow."
        return "Planned path is clear of known incidents."
    saved = planned_m["live_min"] - m["live_min"]
    avoided = [i for i in planned_m["incidents_hit"] if i not in m["incidents_hit"]]
    parts = []
    if avoided:
        parts.append(f"avoids {', '.join(avoided)}")
    parts.append(f"{abs(saved):.1f} min {'faster' if saved >= 0 else 'slower'} than the planned path")
    if m["incidents_hit"]:
        parts.append(f"still touches {hit}")
    return "Alternative " + "; ".join(parts) + "."


def plan_routes(incidents: list[dict], vehicle_pos: tuple[float, float], backups: list[tuple[str, tuple[float, float]]],
                graph: RoadGraph | None = None, goal: str = HOSPITAL_NODE, k: int = 3, impact: IncidentImpact | None = None) -> Plan:
    free_flow = to_free_flow_graph(graph or build_demo_graph())
    impact = impact or IncidentImpact(incidents)
    live = impact.apply(free_flow)
    start = free_flow.nearest_node(*vehicle_pos)
    planned, _ = free_flow.astar(start, goal)
    if not planned:
        raise ValueError("no route to destination")
    paths = [planned]
    for cand in k_routes(live, start, goal, k + 1):
        if cand.path not in paths:
            paths.append(cand.path)
    paths = paths[: k]
    metrics = [route_metrics(free_flow, live, p, impact) for p in paths]
    routes = []
    for i, (path, m) in enumerate(zip(paths, metrics)):
        routes.append({
            "id": f"route-{i + 1}", "name": "Current route" if i == 0 else f"Alternative {i}", "path": path,
            "eta_min": m["live_min"], "incident_adjusted": True,  # input for the predictor
            "risk": risk_label(m["risk_score"]), "risk_score": m["risk_score"],
            "distance_km": round(m["distance_km"], 2), "free_flow_min": m["free_flow_min"], "extra_min": m["extra_min"],
            "incidents_hit": m["incidents_hit"],
            "points": [{"lat": free_flow.pos[n][0], "lon": free_flow.pos[n][1]} for n in path],
            "explanation": _explain(i, m, metrics[0]["free_flow_min"], metrics[0]),
        })
    considered = []
    for vid, pos in backups:
        eta = backup_eta_minutes(live, pos, vehicle_pos)
        if eta is not None:
            considered.append({"vehicle_id": vid, "eta_min": eta})
    considered.sort(key=lambda b: b["eta_min"])
    best = considered[0] if considered else None
    return Plan(routes, free_flow, live, impact, start, goal, best["vehicle_id"] if best else None,
                best["eta_min"] if best else None, metrics[0]["free_flow_min"], considered)


def display_routes(plan: Plan, actions) -> list[dict]:
    """Routes as the dispatcher sees them: ETA/uncertainty are the PREDICTED values the policy actually used."""
    by_route = {a.route_id: a for a in actions if a.route_id and a.action_type in ("continue", "reroute")}
    out = []
    for r in plan.routes:
        a = by_route[r["id"]]
        out.append({
            "id": r["id"], "name": r["name"], "eta_min": round(a.eta.value, 2),
            "delay_min": round(a.eta.value - plan.baseline_min, 2),
            "uncertainty_min": round(a.eta.uncertainty, 2),
            "eta_lower": round(a.eta.lower, 2), "eta_upper": round(a.eta.upper, 2),
            "risk": r["risk"], "risk_score": round(r["risk_score"], 3), "distance_km": r["distance_km"],
            "incidents_hit": r["incidents_hit"], "points": r["points"], "explanation": r["explanation"],
        })
    return out
