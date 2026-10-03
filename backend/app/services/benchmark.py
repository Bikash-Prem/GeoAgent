"""Reproducible SYNTHETIC benchmark for the GeoAgentic decision pipeline (pure Python, no DB, seeded).

What it measures (real numbers from running the real planner / predictor / policy code):
  * hospital-arrival time of 3 strategies under noisy "ground truth" the system cannot see exactly
  * ETA prediction error (RMSE / MAE) vs a free-flow-only baseline, and ETA interval coverage (+ calibrated version)
  * route-deviation detection precision / recall (segment distance vs the old nearest-vertex rule)
  * compute latency of one full decision

What it does NOT show: real-world performance. The world is a synthetic graph and the "ground truth" is our own
simulator with extra randomness (different incident strength / reach, unreported incidents, position error,
per-road noise) so the model is never graded on its own assumptions. Treat results as evidence that the logic is
sound and robust, not as a field result. Dispatcher decision-time reduction needs a user study (not simulated).
"""
from __future__ import annotations

import math
import random
import statistics
import time

from app.algorithms.astar import build_demo_graph
from app.algorithms.geometry import (DEVIATION_THRESHOLD_M, M_PER_DEG_LAT, nearest_vertex_m, point_to_polyline_m)
from app.services.counterfactual import CounterfactualActionEngine
from app.services.decision_models import SituationState
from app.services.planner import HOSPITAL_NODE, plan_routes
from app.services.policy import RuleBasedPolicy
from app.services.risk import IncidentImpact, route_metrics, to_free_flow_graph

CALIBRATION_LEVEL = 0.90


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))] if s else 0.0


def _situation(incidents: list[dict]) -> SituationState:
    return SituationState("bench", "AMB-07", {}, incidents, {"speed_drop": 0.0},
                          "incident-induced congestion" if incidents else "no confirmed disruption", 0.8, [], fleet={"available": 2})


def _make_scenario(rng: random.Random, ff) -> dict:
    nodes = sorted(ff.pos)
    while True:
        start = rng.choice(nodes)
        goal = HOSPITAL_NODE if rng.random() < 0.7 else rng.choice(nodes)
        path, _ = ff.astar(start, goal)
        if start != goal and len(path) >= 4:
            break
    edges = [(a, b) for a in ff.adj for b in (e.to for e in ff.adj[a]) if a < b]
    on_path = list(zip(path, path[1:]))
    true_incidents = []
    for i in range(rng.choice([1, 2, 2, 3])):
        a, b = rng.choice(on_path if rng.random() < 0.7 else edges)
        t = rng.uniform(0.2, 0.8)
        (la, lo), (lb, lb2) = ff.pos[a], ff.pos[b]
        true_incidents.append({"id": f"INC-{i}", "kind": rng.choices(["accident", "closure", "traffic"], [0.4, 0.3, 0.3])[0],
                               "severity": rng.choice(["high", "medium", "low"]), "radius_m": rng.uniform(120, 350),
                               "lat": la + (lb - la) * t, "lon": lo + (lb2 - lo) * t})
    observed = []
    for inc in true_incidents:
        if rng.random() < 0.10:
            continue  # incident never reported
        o = dict(inc)
        o["lat"] += rng.gauss(0, 40) / M_PER_DEG_LAT
        o["lon"] += rng.gauss(0, 40) / M_PER_DEG_LAT
        if rng.random() < 0.15:
            o["severity"] = rng.choice(["high", "medium", "low"])
        observed.append(o)
    truth = IncidentImpact(true_incidents, gain=rng.uniform(0.7, 1.5), influence=rng.uniform(1.0, 1.6)).apply(ff)
    noise = {(a, b): rng.lognormvariate(0, 0.12) for a, b in edges}
    return {"start": start, "goal": goal, "planned": path, "observed": observed, "truth": truth, "noise": noise}


def _realized(sc: dict, path: list[str]) -> float:
    return sum(sc["truth"].edge(a, b).weight * sc["noise"][tuple(sorted((a, b)))] for a, b in zip(path, path[1:]))


def _eta_block(n: int, seed: int, target: float) -> dict:
    rng = random.Random(seed)
    ff = to_free_flow_graph(build_demo_graph())
    engine, policy = CounterfactualActionEngine(), RuleBasedPolicy(target)
    names = ("static_shortest", "incident_aware_routing", "geoagentic_policy")
    real = {k: [] for k in names}
    risk = {k: [] for k in names}
    errs, free_errs, cover, widths, rel_resid, intervals = [], [], [], [], [], []
    disrupted, harmful, rerouted, hedged, regrets, latencies = [], 0, 0, 0, [], []
    for _ in range(n):
        sc = _make_scenario(rng, ff)
        pos = ff.pos[sc["start"]]
        backups = [("AMB-A", ff.pos[rng.choice(sorted(ff.pos))]), ("AMB-B", ff.pos[rng.choice(sorted(ff.pos))])]
        t0 = time.perf_counter()
        plan = plan_routes(sc["observed"], pos, backups, goal=sc["goal"])
        acts = engine.evaluate(_situation(sc["observed"]), plan.routes, plan.backup_id, plan.backup_eta)
        rec = policy.select(acts)
        latencies.append((time.perf_counter() - t0) * 1000)
        by_id = {r["id"]: r for r in plan.routes}
        s_static = _realized(sc, sc["planned"])
        s_aware = _realized(sc, min(plan.routes, key=lambda r: r["eta_min"])["path"])
        chosen = by_id[rec.route_id]
        s_geo = _realized(sc, chosen["path"])
        paths = (sc["planned"], min(plan.routes, key=lambda r: r["eta_min"])["path"], chosen["path"])
        for k, v, pth in zip(names, (s_static, s_aware, s_geo), paths):
            real[k].append(v)
            risk[k].append(route_metrics(ff, sc["truth"], pth)["risk_score"])
        if s_static >= 1.2 * plan.baseline_min:
            disrupted.append((s_static, s_aware, s_geo, s_static / plan.baseline_min))
        if chosen["path"] != sc["planned"]:
            rerouted += 1
            harmful += s_geo > s_static + 0.5
        hedged += rec.action_type.endswith("_and_dispatch")
        regrets.append(s_geo - min(_realized(sc, r["path"]) for r in plan.routes))
        errs.append(rec.eta.value - s_geo)
        free_errs.append(plan.baseline_min if chosen["path"] == sc["planned"] else chosen["free_flow_min"])
        free_errs[-1] -= s_geo
        cover.append(rec.eta.lower <= s_geo <= rec.eta.upper)
        widths.append(rec.eta.upper - rec.eta.lower)
        rel_resid.append(abs(s_geo - rec.eta.value) / rec.eta.value)
        intervals.append((rec.eta.value, rec.eta.lower, rec.eta.upper, s_geo))
    half = n // 2
    q_n = min(1.0, math.ceil((half + 1) * CALIBRATION_LEVEL) / half) if half else 1.0
    q = _pct(rel_resid[:half], q_n) if half else 0.0
    test = intervals[half:]
    cal_cover = statistics.mean(abs(real_t - v) <= q * v for v, _, _, real_t in test) if test else 0.0
    raw_cover_test = statistics.mean(lo <= real_t <= hi for _, lo, hi, real_t in test) if test else 0.0
    rmse = lambda e: math.sqrt(statistics.mean(x * x for x in e))
    mean_static = statistics.mean(real["static_shortest"])
    summary = {}
    for k in names:
        v = real[k]
        summary[k] = {"mean_min": round(statistics.mean(v), 2), "median_min": round(statistics.median(v), 2), "p90_min": round(_pct(v, 0.9), 2),
                      "mean_reduction_vs_static_pct": round(100 * (mean_static - statistics.mean(v)) / mean_static, 1),
                      "mean_route_risk": round(statistics.mean(risk[k]), 3),
                      "late_over_target_pct": round(100 * statistics.mean(x > target for x in v), 1)}
    d_static = statistics.mean(x[0] for x in disrupted) if disrupted else 0.0
    d_aware = statistics.mean(x[1] for x in disrupted) if disrupted else 0.0
    d_geo = statistics.mean(x[2] for x in disrupted) if disrupted else 0.0
    buckets = {}
    for label, lo, hi in (("1.2x-1.5x slower", 1.2, 1.5), ("1.5x+ slower", 1.5, 99)):
        rows = [x for x in disrupted if lo <= x[3] < hi]
        if rows:
            st, ge = statistics.mean(x[0] for x in rows), statistics.mean(x[2] for x in rows)
            buckets[label] = {"scenarios": len(rows), "improvement_pct": round(100 * (st - ge) / st, 1)}
    return {
        "scenarios": n, "disrupted_scenarios": len(disrupted), "strategies": summary, "target_min": target,
        "disrupted_subset": {"static_mean_min": round(d_static, 2), "geoagentic_mean_min": round(d_geo, 2),
                             "incident_aware_mean_min": round(d_aware, 2),
                             "improvement_pct": round(100 * (d_static - d_geo) / d_static, 1) if d_static else 0.0,
                             "by_severity": buckets},
        "reroute_rate_pct": round(100 * rerouted / n, 1), "harmful_reroute_rate_pct": round(100 * harmful / n, 1),
        "backup_hedge_rate_pct": round(100 * hedged / n, 1), "mean_regret_vs_best_candidate_min": round(statistics.mean(regrets), 2),
        "eta": {"rmse_min": round(rmse(errs), 2), "mae_min": round(statistics.mean(abs(e) for e in errs), 2),
                "baseline_free_flow_rmse_min": round(rmse(free_errs), 2),
                "interval_coverage_pct": round(100 * statistics.mean(cover), 1), "interval_mean_width_min": round(statistics.mean(widths), 2),
                "calibration": {"level_pct": 90, "relative_half_width": round(q, 3), "test_coverage_raw_interval_pct": round(100 * raw_cover_test, 1),
                                "test_coverage_calibrated_interval_pct": round(100 * cal_cover, 1)}},
        "latency_ms": {"p50": round(_pct(latencies, 0.5), 2), "p95": round(_pct(latencies, 0.95), 2)},
    }


def _offset(lat: float, lon: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    return lat + dy_m / M_PER_DEG_LAT, lon + dx_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


def _deviation_block(trials: int, seed: int) -> dict:
    """Truth = TRUE offset from the road before GPS noise: >= 300 m is deviating, ~on-road is not. Noise is added after."""
    rng = random.Random(seed + 1)
    ff = to_free_flow_graph(build_demo_graph())
    path, _ = ff.astar("A", HOSPITAL_NODE)
    poly = [ff.pos[n] for n in path]
    results = {"segment_distance": [0, 0, 0, 0], "nearest_vertex": [0, 0, 0, 0]}  # tp, fp, fn, tn
    done = 0
    while done < trials:
        deviating = done % 2 == 0
        a, b = rng.choice(list(zip(poly, poly[1:])))
        t = rng.random()
        lat, lon = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        if deviating:
            dx, dy = (b[1] - a[1]) * M_PER_DEG_LAT * math.cos(math.radians(lat)), (b[0] - a[0]) * M_PER_DEG_LAT
            length = math.hypot(dx, dy) or 1.0
            d = rng.uniform(300, 700) * rng.choice((-1, 1))
            lat, lon = _offset(lat, lon, -dy / length * d, dx / length * d)
            if point_to_polyline_m(lat, lon, poly) < 300:
                continue  # perpendicular step landed near another road segment: not a clean deviation, resample
        sigma = 120 if rng.random() < 0.05 else 25  # 5% GPS outliers
        lat, lon = _offset(lat, lon, rng.gauss(0, sigma), rng.gauss(0, sigma))
        for name, dist in (("segment_distance", point_to_polyline_m(lat, lon, poly)), ("nearest_vertex", nearest_vertex_m(lat, lon, poly))):
            flagged = dist > DEVIATION_THRESHOLD_M
            idx = (0 if deviating else 1) if flagged else (2 if deviating else 3)
            results[name][idx] += 1
        done += 1
    out = {}
    for name, (tp, fp, fn, tn) in results.items():
        p, r = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
        out[name] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn, "tn": tn}
    out["threshold_m"], out["trials"] = DEVIATION_THRESHOLD_M, trials
    return out


def run_benchmark(n: int = 200, seed: int = 7, response_target_min: float = 15.0) -> dict:
    n = max(20, min(int(n), 2000))
    eta = _eta_block(n, seed, response_target_min)
    dev = _deviation_block(max(200, n * 2), seed)
    d = dev["segment_distance"]
    targets = [
        {"metric": "Deviation detection (precision / recall)", "target": ">= 0.85", "value": f"{d['precision']} / {d['recall']}", "status": "met" if min(d["precision"], d["recall"]) >= 0.85 else "not_met"},
        {"metric": "ETA prediction error (RMSE)", "target": "<= 4.0 min", "value": f"{eta['eta']['rmse_min']} min", "status": "met" if eta["eta"]["rmse_min"] <= 4.0 else "not_met"},
        {"metric": "Route improvement when the planned path is disrupted", "target": ">= 20%", "value": f"{eta['disrupted_subset']['improvement_pct']}%", "status": "met" if eta["disrupted_subset"]["improvement_pct"] >= 20 else "not_met"},
        {"metric": "Decision computation time", "target": "<= 30 s", "value": f"p95 {eta['latency_ms']['p95']} ms (compute only)", "status": "met" if eta["latency_ms"]["p95"] <= 30000 else "not_met"},
        {"metric": "Dispatcher decision-time reduction", "target": ">= 30%", "value": "not measured", "status": "not_measured"},
    ]
    return {"synthetic": True, "seed": seed, "response_target_min": response_target_min, "targets": targets, "routing": eta, "deviation_detection": dev,
            "caveats": ["Synthetic graph and simulator; not a real-world result.",
                        "Ground truth uses randomised incident strength/reach, 10% unreported incidents, 40 m position error and per-road noise.",
                        "Latency excludes database and network time.",
                        "Decision-time reduction requires a user study with dispatchers or trained proxies."]}
