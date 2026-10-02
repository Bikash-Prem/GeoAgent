from .decision_models import ActionEvaluation, Prediction, SituationState
from .prediction import HeuristicETAPredictor


class CounterfactualActionEngine:
    def __init__(self, predictor: HeuristicETAPredictor | None = None):
        self.predictor = predictor or HeuristicETAPredictor()

    def evaluate(self, situation: SituationState, routes: list[dict], backup_vehicle_id: str | None, backup_eta: float | None) -> list[ActionEvaluation]:
        actions: list[ActionEvaluation] = []
        for index, route in enumerate(routes):
            prediction = self.predictor.predict(float(route["eta_min"]), situation, 0.0)
            risk_score = {"low": 0.18, "medium": 0.46, "high": 0.82}.get(route["risk"], 0.5)
            actions.append(ActionEvaluation(f"action-reroute-{index + 1}", "reroute" if index else "continue", situation.vehicle_id, prediction, risk_score, route["risk"].upper(), min(0.99, risk_score + 0.15), "LOW", 0.0, [], prediction.confidence, [item.evidence_id for item in situation.evidence], route["id"]))
        if backup_vehicle_id and backup_eta is not None:
            prediction = self.predictor.predict(backup_eta, situation)
            actions.append(ActionEvaluation("action-dispatch-backup", "dispatch_backup", backup_vehicle_id, prediction, 0.16, "LOW", 0.16, "MEDIUM", -0.12, [], prediction.confidence, [item.evidence_id for item in situation.evidence]))
            if len(routes) > 1:
                combined = self.predictor.predict(min(routes[1]["eta_min"], backup_eta), situation)
                actions.append(ActionEvaluation("action-reroute-and-dispatch", "reroute_and_dispatch", situation.vehicle_id, combined, 0.12, "LOW", 0.12, "HIGH", -0.3, [], combined.confidence, [item.evidence_id for item in situation.evidence], routes[1]["id"]))
        return actions