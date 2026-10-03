"""Real-road routing: provider route candidates (Google Routes / Mapbox) re-scored by GeoAgentic's incident model.

Provider ETAs are already traffic-aware, so only registry events a map provider may not know yet (accidents and
closures logged by dispatchers or imported from TomTom) add slow-down here; congestion is not counted twice.
The result has the same shape as the demo-graph plan, so prediction, counterfactuals, policy and UI are unchanged.
"""
from __future__ import annotations

import time
from math import inf

from app.algorithms.geometry import metres
from app.services.planner import Plan
from app.services.providers.sync import run_sync
from app.services.risk import TURNOUT_MIN, IncidentImpact, risk_label

BASE_RISK = 0.1
CACHE_TTL_S = 60.0
_cache: dict[tuple, tuple[float, object]] = {}


def _key(provider, a, b):
    return (type(provider).__name__, round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3))  # ~100 m buckets


def fetch_routes(provider, origin, destination):
    """Provider call with a short TTL cache so the control loop does not spend an API call every tick."""
    k = _key(provider, origin, destination)
    hit = _cache.get(k)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1]
    obs = run_sync(provider.routes(origin, destination))
    if obs.routes:
        _cache[k] = (time.time(), obs)
    return obs


def score_polyline(points: list[dict], provider_eta: float, impact: IncidentImpact) -> dict:
    segs = list(zip(points, points[1:]))
    lengths = [metres(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in segs]
    total = sum(lengths) or 1.0
    live, risk_mean, risk_max, hits = 0.0, 0.0, BASE_RISK, {}
    for (a, b), length in zip(segs, lengths):
        share = length / total
        fx = impact.edge_effect((a["lat"], a["lon"]), (b["lat"], b["lon"]))
        live += provider_eta * share * fx.multiplier
        r = min(1.0, BASE_RISK + fx.risk_add)
        risk_mean += r * share
        risk_max = max(risk_max, r)
        for inc_id, e in fx.exposures.items():
            hits[inc_id] = max(hits.get(inc_id, 0.0), e)
    if not segs:
        live = provider_eta
    return {"live_min": live, "risk_score": min(0.99, 0.6 * risk_mean + 0.4 * risk_max), "incidents_hit": sorted(i for i, e in hits.items() if e >= 0.15)}


def provider_plan(provider, incidents: list[dict], vehicle_pos, destination, backups: list[tuple[str, tuple[float, float]]], k: int = 3):
    """Returns (Plan | None, observation). None means the provider gave nothing usable and the caller should fall back."""
    obs = fetch_routes(provider, vehicle_pos, destination)
    if not obs.routes:
        return None, obs
    impact = IncidentImpact([i for i in incidents if i.get("kind") in ("accident", "closure")])
    routes = []
    for i, r in enumerate(obs.routes[:k]):
        m = score_polyline(r["points"], float(r["eta_min"]), impact)
        extra = m["live_min"] - float(r["eta_min"])
        parts = [f"{obs.provider.title()} ETA {r['eta_min']:.1f} min"]
        if r.get("traffic_delay_min"):
            parts.append(f"includes {r['traffic_delay_min']:.1f} min live traffic")
        if m["incidents_hit"]:
            parts.append(f"+{extra:.1f} min for {', '.join(m['incidents_hit'])} from the incident registry")
        routes.append({
            "id": f"route-{i + 1}", "name": "Current route" if i == 0 else f"Alternative {i}", "path": [],
            "eta_min": m["live_min"], "incident_adjusted": True, "risk": risk_label(m["risk_score"]), "risk_score": m["risk_score"],
            "distance_km": round(float(r["distance_km"]), 2), "free_flow_min": float(r.get("static_eta_min") or r["eta_min"]), "extra_min": extra,
            "incidents_hit": m["incidents_hit"], "points": r["points"], "explanation": "; ".join(parts) + ".", "provider": obs.provider,
        })
    considered = []
    for vid, pos in sorted(backups, key=lambda b: metres(*b[1], *vehicle_pos))[:3]:
        b_obs = fetch_routes(provider, pos, vehicle_pos)
        if b_obs.routes:
            considered.append({"vehicle_id": vid, "eta_min": round(TURNOUT_MIN + min(float(x["eta_min"]) for x in b_obs.routes), 2)})
    considered.sort(key=lambda b: b["eta_min"])
    best = considered[0] if considered else None
    baseline = min((r["free_flow_min"] for r in routes), default=inf)
    plan = Plan(routes, None, None, impact, "origin", "destination", best["vehicle_id"] if best else None, best["eta_min"] if best else None, baseline, considered)
    return plan, obs
