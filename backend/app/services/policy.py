from .decision_models import ActionEvaluation


class BasePolicy:
    name = "base-policy"
    version = "0.0"

    def select(self, actions: list[ActionEvaluation]) -> ActionEvaluation:
        raise NotImplementedError


class RuleBasedPolicy(BasePolicy):
    """Safety-first, uncertainty-aware, explainable policy. An RL policy can implement the same interface later.

    1. Among actions that carry a route, pick the best ETA + 4 x risk (hospital arrival matters most).
       Abandoning the current route needs a real gain (switch_margin) - this avoids pointless reroutes.
    2. If even the *upper bound* of that ETA exceeds the operator's response target, the situation is not safe
       to leave to one unit: prefer the matching "route + backup" hedge when a backup exists.
    3. Otherwise do NOT spend a backup unit (it reduces regional coverage).
    """

    name = "rule-based-safety-first"
    version = "1.2"

    def __init__(self, response_target_min: float = 15.0, switch_margin: float = 1.0):
        self.response_target_min = response_target_min
        self.switch_margin = switch_margin  # minutes-equivalent gain required to leave the current route

    def select(self, actions: list[ActionEvaluation]) -> ActionEvaluation:
        if not actions:
            raise ValueError("no actions available")
        plain = [a for a in actions if a.route_id and a.action_type in ("continue", "reroute")]
        if not plain:
            return min(actions, key=lambda action: action.eta.value + action.risk_score * 4 + max(0, -action.coverage_change) * 8)
        score = lambda a: a.eta.value + a.risk_score * 4
        best = min(plain, key=score)
        current = next((a for a in plain if a.action_type == "continue"), None)
        if current and best is not current and score(current) - score(best) < self.switch_margin:
            best = current
        if best.eta.upper > self.response_target_min:
            hedge = next((a for a in actions if a.route_id == best.route_id and a.action_type.endswith("_and_dispatch")), None)
            if hedge:
                return hedge
        return best
