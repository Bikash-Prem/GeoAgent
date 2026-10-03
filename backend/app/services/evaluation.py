from functools import lru_cache

from .benchmark import run_benchmark

STRATEGIES = [
    {"id": "routing_only", "components": ["routing"]},
    {"id": "routing_plus_ml", "components": ["routing", "prediction_interface"]},
    {"id": "routing_uncertainty", "components": ["routing", "prediction_interface", "uncertainty"]},
    {"id": "policy_augmented", "components": ["routing", "prediction_interface", "uncertainty", "policy"]},
    {"id": "full_geoagentic", "components": ["situation", "routing", "prediction_interface", "uncertainty", "policy", "agent", "human_approval"]},
]


@lru_cache(maxsize=8)
def _cached(n: int, seed: int, target: float) -> dict:
    return run_benchmark(n, seed, target)


class EvaluationPlan:
    """Defines comparable configurations; results come ONLY from run(), which executes the real code on seeded synthetic scenarios."""

    def list(self) -> list[dict]:
        return [{**strategy, "results": None, "metrics": ["eta_error", "delay", "fleet_coverage", "decision_latency", "action_success"]} for strategy in STRATEGIES]

    def run(self, n: int = 200, seed: int = 7, response_target_min: float = 15.0) -> dict:
        return _cached(max(20, min(int(n), 2000)), int(seed), float(response_target_min))
