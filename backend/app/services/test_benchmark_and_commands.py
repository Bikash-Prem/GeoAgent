"""Pure tests (no DB / web server needed):  python -m unittest app.services.test_benchmark_and_commands"""
import unittest

from app.algorithms.astar import build_demo_graph
from app.algorithms.geometry import point_to_polyline_m, nearest_vertex_m
from app.services.benchmark import run_benchmark
from app.services.counterfactual import CounterfactualActionEngine
from app.services.decision_models import SituationState
from app.services.nlcommand import numbers_grounded, parse_command, respond
from app.services.planner import display_routes, plan_routes
from app.services.policy import RuleBasedPolicy
from app.services.risk import IncidentImpact, to_free_flow_graph

INCIDENTS = [
    dict(id="INC-204", kind="accident", severity="high", lat=12.9731, lon=77.5997, radius_m=220),
    dict(id="INC-205", kind="closure", severity="medium", lat=12.9718, lon=77.6012, radius_m=150),
    dict(id="INC-206", kind="traffic", severity="medium", lat=12.9705, lon=77.5988, radius_m=350),
]
BACKUPS = [("AMB-12", (12.9655, 77.5905)), ("AMB-03", (12.9780, 77.6100))]


def decide(incidents, target=15.0):
    situation = SituationState("s", "AMB-07", {}, incidents, {"speed_drop": 0.0}, "accident-induced congestion" if incidents else "no confirmed disruption", 0.8, [], fleet={"available": 2})
    plan = plan_routes(incidents, (12.9712, 77.5940), BACKUPS)
    actions = CounterfactualActionEngine().evaluate(situation, plan.routes, plan.backup_id, plan.backup_eta)
    return plan, actions, RuleBasedPolicy(target).select(actions)


class AStarOptimality(unittest.TestCase):
    def test_matches_dijkstra_on_every_pair(self):
        g = to_free_flow_graph(build_demo_graph())
        for a in g.pos:
            for b in g.pos:
                if a != b:
                    path, cost = g.astar(a, b)
                    self.assertAlmostEqual(cost, g.path_cost(path), places=6)
                    zero = to_free_flow_graph(build_demo_graph()); zero.h_scale = 0.0
                    self.assertAlmostEqual(cost, zero.astar(a, b)[1], places=6)


class PlannerAndPolicy(unittest.TestCase):
    def test_no_incident_keeps_current_route_and_spends_no_backup(self):
        _, _, rec = decide([])
        self.assertEqual(rec.action_type, "continue")

    def test_incident_on_planned_route_triggers_faster_reroute(self):
        plan, actions, rec = decide(INCIDENTS)
        routes = display_routes(plan, actions)
        self.assertEqual(rec.action_type, "reroute")
        self.assertLess(next(r for r in routes if r["id"] == rec.route_id)["eta_min"], routes[0]["eta_min"])
        self.assertIn("INC-204", routes[0]["incidents_hit"])

    def test_tight_target_adds_backup_hedge(self):
        _, _, rec = decide(INCIDENTS, target=12.0)
        self.assertEqual(rec.action_type, "reroute_and_dispatch")
        self.assertEqual(rec.backup_vehicle_id, "AMB-12")  # nearest by routed ETA, not alphabetical

    def test_incident_slowdown_never_speeds_up_a_road(self):
        ff = to_free_flow_graph(build_demo_graph()); live = IncidentImpact(INCIDENTS).apply(ff)
        for a in ff.adj:
            for e in ff.adj[a]:
                self.assertGreaterEqual(live.edge(a, e.to).weight, e.weight - 1e-9)


class Geometry(unittest.TestCase):
    def test_midpoint_of_long_segment_is_on_route(self):
        a, b = (12.9712, 77.5940), (12.9720, 77.6070)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        self.assertLess(point_to_polyline_m(*mid, [a, b]), 1.0)
        self.assertGreater(nearest_vertex_m(*mid, [a, b]), 600)  # the old rule would have called this a deviation


class Benchmark(unittest.TestCase):
    def test_reproducible_and_honest(self):
        strip = lambda r: {k: v for k, v in r.items() if k != "targets"} | {"routing": {k: v for k, v in r["routing"].items() if k != "latency_ms"}}
        a, b = run_benchmark(60, 3), run_benchmark(60, 3)
        self.assertEqual(strip(a), strip(b))
        self.assertTrue(a["synthetic"])
        self.assertEqual(a["targets"][-1]["status"], "not_measured")  # decision-time reduction is never faked
        self.assertLess(a["routing"]["strategies"]["geoagentic_policy"]["mean_min"], a["routing"]["strategies"]["static_shortest"]["mean_min"])


class Commands(unittest.TestCase):
    def rec(self, incidents=INCIDENTS, target=15.0):
        plan, actions, rec = decide(incidents, target)
        routes = display_routes(plan, actions)
        backup = next((a for a in actions if a.action_type == "dispatch_backup"), None)
        decision = {"recommended_action": rec.as_dict(), "reasoning": "because", "evidence": [{"evidence_id": "incident-nearest"}]}
        return {"vehicle_id": "AMB-07", "routes": routes, "cause": "accident-induced congestion", "confidence": 0.8, "evidence": ["Accident is 100m away."],
                "backup_vehicle_id": backup.vehicle_id if backup else None, "backup_eta_min": round(backup.eta.value, 2) if backup else None, "decision_id": "dec-x", "decision": decision}

    def test_parse(self):
        self.assertEqual(parse_command("Show the best alternative route for AMB-07").intent, "best_route")
        self.assertEqual(parse_command("show best route for amb 7").vehicle_id, "AMB-07")
        self.assertEqual(parse_command("why is it delayed?").intent, "explain")
        self.assertEqual(parse_command("is there a nearby backup ambulance").intent, "backup")
        self.assertEqual(parse_command("approve the reroute").intent, "approve")
        self.assertEqual(parse_command("banana").intent, "unknown")

    def test_chat_cannot_approve_and_nonsense_needs_no_analysis(self):
        from app.services.nlcommand import needs_analysis
        out = respond(parse_command("approve the reroute now"), None)
        self.assertIn("can't approve", out["answer"]); self.assertTrue(out["requires_human_approval"]); self.assertIsNone(out["decision_id"])
        self.assertFalse(needs_analysis(parse_command("approve it"))); self.assertFalse(needs_analysis(parse_command("banana")))
        self.assertTrue(needs_analysis(parse_command("best route for AMB-07")))
        self.assertIn("Try:", respond(parse_command("banana"), None)["answer"])

    def test_answers_contain_engine_numbers(self):
        rec = self.rec()
        out = respond(parse_command("show best alternative route for AMB-07"), rec)
        self.assertIn(f"{rec['routes'][1]['eta_min']:.1f}", out["answer"]); self.assertEqual(out["mode"], "deterministic")

    def test_llm_output_with_invented_numbers_is_rejected(self):
        rec = self.rec()
        good = lambda answer, facts, *_: "Take the alternative route; it is faster."
        bad = lambda answer, facts, *_: "Take the alternative route, it saves 99.9 minutes."
        self.assertEqual(respond(parse_command("best route"), rec, True, "k", "m", _llm=good)["mode"], "llm-rephrased (numbers verified)")
        rejected = respond(parse_command("best route"), rec, True, "k", "m", _llm=bad)
        self.assertEqual(rejected["mode"], "deterministic")
        self.assertNotIn("99.9", rejected["answer"])
        self.assertEqual(respond(parse_command("best route"), rec, True, "", "m", _llm=good)["mode"], "deterministic")  # no key -> no LLM

    def test_number_guard(self):
        self.assertFalse(numbers_grounded("saves 99.9 minutes", {"a": "12.1 min"}))
        self.assertTrue(numbers_grounded("about 12 minutes", {"a": "12.1 min"}))


if __name__ == "__main__":
    unittest.main()
