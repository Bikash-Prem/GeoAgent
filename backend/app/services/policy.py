from .decision_models import ActionEvaluation


class BasePolicy:
    name = "base-policy"
    version = "0.0"

    def select(self, actions: list[ActionEvaluation]) -> ActionEvaluation:
        raise NotImplementedError


class RuleBasedPolicy(BasePolicy):
    """Safety-first deterministic policy; an RL policy can implement the same interface later."""

    name = "rule-based-safety-first"
    version = "1.0"

    def select(self, actions: list[ActionEvaluation]) -> ActionEvaluation:
        if not actions:
            raise ValueError("no actions available")
        return min(actions, key=lambda action: action.eta.value + action.risk_score * 4 + max(0, -action.coverage_change) * 8)