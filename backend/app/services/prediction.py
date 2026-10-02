from .decision_models import Prediction, SituationState


class BasePredictor:
    model_name = "base"
    model_version = "0.0"


class HeuristicETAPredictor(BasePredictor):
    """Transparent baseline; replaceable by a trained model without changing callers."""

    model_name = "heuristic-eta"
    model_version = "1.0"

    def predict(self, base_eta: float, situation: SituationState, risk_penalty: float = 0.0) -> Prediction:
        congestion = 1.0 + situation.telemetry.get("speed_drop", 0.0) * 0.7
        incident_penalty = 1.12 if situation.diagnosis != "no confirmed disruption" else 1.0
        value = max(1.0, base_eta * congestion * incident_penalty + risk_penalty)
        uncertainty = max(0.8, value * (0.08 + situation.telemetry.get("speed_drop", 0.0) * 0.12))
        confidence = max(0.45, min(0.96, 0.92 - uncertainty / max(value * 2, 1)))
        return Prediction("eta_minutes", value, max(0.1, value - uncertainty), value + uncertainty, confidence, uncertainty, self.model_name, self.model_version, ("base_route_eta", "speed_change", "incident_diagnosis"))