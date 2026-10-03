from .decision_models import ActionEvaluation, Prediction, SituationState
from .prediction import HeuristicETAPredictor


class CounterfactualActionEngine:
    def __init__(self, predictor: HeuristicETAPredictor | None = None):
        self.predictor = predictor or HeuristicETAPredictor()

    def evaluate(self, situation: SituationState, routes: list[dict], backup_vehicle_id: str | None, backup_eta: float | None) -> list[ActionEvaluation]:
        actions: list[ActionEvaluation] = []
        total = max(int((situation.fleet or {}).get("total", 0)), 1)
        available = int((situation.fleet or {}).get("available", 0))
        for index, route in enumerate(routes):
            risk_score = float(route.get("risk_score", {"low": 0.18, "medium": 0.46, "high": 0.82}.get(str(route.get("risk", "medium")).lower(), 0.46)))
            prediction = self.predictor.predict(float(route["eta_min"]), situation, risk_score * 0.8)
            delay_probability = float(route.get("delay_probability", 0.2))
            resource_impact = "LOW"
            actions.append(ActionEvaluation(
                f"action-reroute-{index + 1}", "reroute" if index else "continue", situation.vehicle_id,
                prediction, risk_score, route["risk"].upper(), delay_probability, resource_impact, 0.0,
                [], prediction.confidence, [item.evidence_id for item in situation.evidence], route["id"],
            ))
        if backup_vehicle_id and backup_eta is not None:
            prediction = self.predictor.predict(backup_eta, situation, 0.0)
            remaining_coverage = max(0, available - 1) / total
            coverage_change = -1 / total
            impact = "HIGH" if remaining_coverage < 0.25 else "MEDIUM" if remaining_coverage < 0.5 else "LOW"
            actions.append(ActionEvaluation(
                "action-dispatch-backup", "dispatch_backup", backup_vehicle_id, prediction,
                min(0.99, 0.18 + situation.diagnosis_confidence * 0.15), "LOW", 0.12,
                impact, coverage_change, [], prediction.confidence, [item.evidence_id for item in situation.evidence], None,
            ))
            if len(routes) > 1:
                combined_route = routes[1]
                combined = self.predictor.predict(min(float(combined_route["eta_min"]), backup_eta), situation, float(combined_route.get("risk_score", 0.2)) * 0.6)
                actions.append(ActionEvaluation(
                    "action-reroute-and-dispatch", "reroute_and_dispatch", situation.vehicle_id, combined,
                    min(0.99, float(combined_route.get("risk_score", 0.2)) * 0.8), combined_route["risk"].upper(),
                    float(combined_route.get("delay_probability", 0.15)), impact, coverage_change, [], combined.confidence,
                    [item.evidence_id for item in situation.evidence], combined_route["id"],
                ))
        return actions
