from .decision_models import ActionEvaluation, SituationState
from .prediction import HeuristicETAPredictor

LEGACY_RISK = {"low": 0.18, "medium": 0.46, "high": 0.82}


class CounterfactualActionEngine:
    """Evaluates what happens under each possible action (continue / reroute / backup / both)."""

    def __init__(self, predictor: HeuristicETAPredictor | None = None):
        self.predictor = predictor or HeuristicETAPredictor()

    def evaluate(self, situation: SituationState, routes: list[dict], backup_vehicle_id: str | None, backup_eta: float | None) -> list[ActionEvaluation]:
        actions: list[ActionEvaluation] = []
        evidence_ids = [item.evidence_id for item in situation.evidence]
        available = max(1, (situation.fleet or {}).get("available", 1))
        coverage_change = round(-1.0 / available, 3)  # one fewer ready unit in the region
        for index, route in enumerate(routes):
            has_score = "risk_score" in route
            risk_score = route["risk_score"] if has_score else LEGACY_RISK.get(route["risk"], 0.5)
            prediction = self.predictor.predict(float(route["eta_min"]), situation, 0.0, incident_adjusted=route.get("incident_adjusted", False), risk_score=risk_score if has_score else 0.0)
            actions.append(ActionEvaluation(f"action-reroute-{index + 1}", "reroute" if index else "continue", situation.vehicle_id, prediction, risk_score, route["risk"].upper(), min(0.99, risk_score + 0.15), "LOW", 0.0, [], prediction.confidence, evidence_ids, route["id"]))
        if backup_vehicle_id and backup_eta is not None:
            prediction = self.predictor.predict(backup_eta, situation, 0.0, incident_adjusted=True)
            actions.append(ActionEvaluation("action-dispatch-backup", "dispatch_backup", backup_vehicle_id, prediction, 0.16, "LOW", 0.16, "MEDIUM", coverage_change, [], prediction.confidence, evidence_ids, None, backup_vehicle_id))
            if actions:
                # Hedge: keep the best route AND send the backup. Same hospital ETA as that route, but the
                # chance the mission is still delayed is halved because a second unit is already moving.
                route_actions = [a for a in actions if a.route_id]
                best = min(route_actions, key=lambda a: a.eta.value + 4 * a.risk_score)
                is_alt = best.action_type == "reroute"
                actions.append(ActionEvaluation("action-reroute-and-dispatch" if is_alt else "action-continue-and-dispatch", "reroute_and_dispatch" if is_alt else "continue_and_dispatch", situation.vehicle_id, best.eta, best.risk_score, best.risk_level, round(best.delay_probability * 0.5, 3), "HIGH", coverage_change, [], best.confidence, evidence_ids, best.route_id, backup_vehicle_id))
        return actions
