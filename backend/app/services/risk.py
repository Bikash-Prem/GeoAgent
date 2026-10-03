"""Incident-aware travel-time and risk model.

Pure Python (no DB / web imports) so the same code powers the live engine AND the offline benchmark.

Modelling assumptions (all explicit, all tunable):
  * The demo road graph is a small synthetic corridor. CITY_SCALE says it stands in for a real route that is
    CITY_SCALE x longer, so ETAs/distances land in a realistic range (~10 min, ~6 km) instead of ~2 min, ~1.5 km.
  * Free-flow speed is FREE_FLOW_KMH. Incidents only ever SLOW edges down (multiplier >= 1), which keeps the
    straight-line heuristic admissible.
  * An incident affects an edge in proportion to how much of the edge lies inside its influence zone
    (radius_m * influence), decaying linearly from the centre.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.algorithms.astar import RoadGraph
from app.algorithms.geometry import metres

CITY_SCALE = 4.0
FREE_FLOW_KMH = 40.0
M_PER_MIN_FREE_FLOW = FREE_FLOW_KMH * 1000 / 60 / CITY_SCALE  # real-world metres of demo geometry per minute
TURNOUT_MIN = 1.0

SEVERITY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}
KIND_SLOWDOWN = {"accident": 2.4, "closure": 3.0, "traffic": 1.2}  # extra multiplier at the centre, severity = 1
KIND_RISK = {"accident": 0.55, "closure": 0.35, "traffic": 0.2}
MAX_MULTIPLIER = 4.0
HIT_EXPOSURE = 0.15  # an incident counts as "on the route" above this exposure


def to_free_flow_graph(base: RoadGraph) -> RoadGraph:
    """Re-weight the demo graph so edge weight == free-flow minutes (from real geometry)."""
    g = RoadGraph()
    for node, (lat, lon) in base.pos.items():
        g.add_node(node, lat, lon)
    for a, edges in base.adj.items():
        for e in edges:
            if a < e.to:
                minutes = metres(*base.pos[a], *base.pos[e.to]) / M_PER_MIN_FREE_FLOW
                g.add_edge(a, e.to, minutes, e.risk)
    g.h_scale = 1.0 / M_PER_MIN_FREE_FLOW  # straight line at free-flow speed: admissible lower bound
    return g


@dataclass
class EdgeEffect:
    multiplier: float
    risk_add: float
    exposures: dict[str, float]


class IncidentImpact:
    """Turns a list of incident dicts into per-edge slow-down and risk."""

    def __init__(self, incidents: list[dict], gain: float = 1.0, influence: float = 1.25):
        self.gain, self.influence = gain, influence
        self.incidents = [i for i in incidents if all(k in i for k in ("lat", "lon", "radius_m"))]

    def _exposure(self, a: tuple[float, float], b: tuple[float, float], inc: dict) -> float:
        reach = max(1.0, inc["radius_m"] * self.influence)
        total, samples = 0.0, 7
        for s in range(samples):
            t = s / (samples - 1)
            lat, lon = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            total += max(0.0, 1.0 - metres(lat, lon, inc["lat"], inc["lon"]) / reach)
        return total / samples

    def edge_effect(self, a: tuple[float, float], b: tuple[float, float]) -> EdgeEffect:
        mult, risk_add, hits = 1.0, 0.0, {}
        for inc in self.incidents:
            if inc.get("kind") not in KIND_SLOWDOWN:
                continue  # e.g. a medical call: needs an ambulance but does not slow traffic
            e = self._exposure(a, b, inc)
            if e <= 0:
                continue
            sev = SEVERITY_WEIGHT.get(inc.get("severity"), 0.5)
            mult += self.gain * sev * KIND_SLOWDOWN.get(inc.get("kind"), 1.0) * e
            risk_add += sev * KIND_RISK.get(inc.get("kind"), 0.2) * e
            hits[inc.get("id", "?")] = e
        return EdgeEffect(min(MAX_MULTIPLIER, mult), min(1.0, risk_add), hits)

    def apply(self, free_flow: RoadGraph) -> RoadGraph:
        live = RoadGraph()
        for node, (lat, lon) in free_flow.pos.items():
            live.add_node(node, lat, lon)
        for a, edges in free_flow.adj.items():
            for e in edges:
                if a < e.to:
                    fx = self.edge_effect(free_flow.pos[a], free_flow.pos[e.to])
                    live.add_edge(a, e.to, e.weight * fx.multiplier, min(1.0, e.risk + fx.risk_add))
        live.h_scale = free_flow.h_scale
        return live


def route_metrics(free_flow: RoadGraph, live: RoadGraph, path: list[str], impact: IncidentImpact | None = None) -> dict:
    """Free-flow time, live time, risk, distance and the incidents a route actually touches."""
    pairs = list(zip(path, path[1:]))
    free = sum(free_flow.edge(a, b).weight for a, b in pairs)
    now = sum(live.edge(a, b).weight for a, b in pairs)
    risks = [live.edge(a, b).risk for a, b in pairs] or [0.0]
    weights = [free_flow.edge(a, b).weight for a, b in pairs] or [1.0]
    mean_risk = sum(r * w for r, w in zip(risks, weights)) / sum(weights)
    hits: dict[str, float] = {}
    if impact:
        for a, b in pairs:
            for inc_id, e in impact.edge_effect(free_flow.pos[a], free_flow.pos[b]).exposures.items():
                hits[inc_id] = max(hits.get(inc_id, 0.0), e)
    distance_km = sum(metres(*free_flow.pos[a], *free_flow.pos[b]) for a, b in pairs) * CITY_SCALE / 1000
    return {
        "free_flow_min": free,
        "live_min": now,
        "extra_min": now - free,
        "risk_score": min(0.99, 0.6 * mean_risk + 0.4 * max(risks)),
        "distance_km": distance_km,
        "incidents_hit": sorted(i for i, e in hits.items() if e >= HIT_EXPOSURE),
    }


def risk_label(score: float) -> str:
    return "high" if score >= 0.65 else "medium" if score >= 0.3 else "low"


def backup_eta_minutes(live: RoadGraph, backup_pos: tuple[float, float], target_pos: tuple[float, float]) -> float | None:
    """Turn-out time + routed travel time (live conditions) from a backup unit to a target position."""
    start, goal = live.nearest_node(*backup_pos), live.nearest_node(*target_pos)
    if start == goal:
        return round(TURNOUT_MIN + 0.5, 2)
    path, cost = live.astar(start, goal)
    return round(TURNOUT_MIN + cost, 2) if path else None
