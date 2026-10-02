import unittest

from app.services.counterfactual import CounterfactualActionEngine
from app.services.decision_models import EvidenceItem, SituationState
from app.services.policy import RuleBasedPolicy


class DecisionComponentTests(unittest.TestCase):
    def setUp(self):
        self.situation = SituationState(
            situation_id="sit-test",
            vehicle_id="AMB-07",
            vehicle={"speed_kmh": 20},
            incidents=[{"id": "INC-1", "kind": "accident"}],
            telemetry={"speed_drop": 0.5},
            diagnosis="accident-induced congestion",
            diagnosis_confidence=0.8,
            evidence=[EvidenceItem("ev-1", "test", "incident", "INC-1", 0.9, 0.8, "test evidence")],
        )

    def test_action_engine_exposes_route_and_backup_counterfactuals(self):
        actions = CounterfactualActionEngine().evaluate(self.situation, [
            {"id": "route-1", "eta_min": 17.0, "risk": "high"},
            {"id": "route-2", "eta_min": 11.0, "risk": "low"},
        ], "AMB-12", 6.0)
        self.assertEqual({"continue", "reroute", "dispatch_backup", "reroute_and_dispatch"}, {item.action_type for item in actions})
        self.assertTrue(all(item.eta.lower <= item.eta.value <= item.eta.upper for item in actions))

    def test_policy_prefers_lower_risk_route_when_eta_is_close(self):
        actions = CounterfactualActionEngine().evaluate(self.situation, [
            {"id": "route-1", "eta_min": 10.0, "risk": "high"},
            {"id": "route-2", "eta_min": 11.0, "risk": "low"},
        ], None, None)
        self.assertEqual("reroute", RuleBasedPolicy().select(actions).action_type)


if __name__ == "__main__":
    unittest.main()