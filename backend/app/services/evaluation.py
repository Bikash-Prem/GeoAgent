STRATEGIES = [
    {"id": "routing_only", "components": ["routing"]},
    {"id": "routing_plus_ml", "components": ["routing", "prediction_interface"]},
    {"id": "routing_uncertainty", "components": ["routing", "prediction_interface", "uncertainty"]},
    {"id": "policy_augmented", "components": ["routing", "prediction_interface", "uncertainty", "policy"]},
    {"id": "full_geoagentic", "components": ["situation", "routing", "prediction_interface", "uncertainty", "policy", "agent", "human_approval"]},
]


class EvaluationPlan:
    """Defines comparable configurations; it intentionally stores no invented results."""

    def list(self) -> list[dict]:
        return [{**strategy, "results": None, "metrics": ["eta_error", "delay", "fleet_coverage", "decision_latency", "action_success"]} for strategy in STRATEGIES]