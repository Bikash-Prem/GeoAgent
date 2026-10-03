from .decision_models import Prediction, SituationState


class BasePredictor:
    model_name = "base"
    model_version = "0.0"


class HeuristicETAPredictor(BasePredictor):
    """Transparent baseline; replaceable by a trained model without changing callers."""

    model_name = "heuristic-eta"
    model_version = "1.1"

    def predict(self, base_eta: float, situation: SituationState, risk_penalty: float = 0.0,
                incident_adjusted: bool = False, risk_score: float = 0.0) -> Prediction:
        """base_eta: minutes. If incident_adjusted, base_eta already includes incident slow-down
        (from services.risk), so the generic incident penalty is NOT applied a second time.
        risk_score (0-1) widens the uncertainty interval: risky corridors are less predictable."""
        speed_drop = situation.telemetry.get("speed_drop", 0.0)
        congestion = 1.0 + speed_drop * 0.7
        incident_penalty = 1.0 if incident_adjusted or situation.diagnosis == "no confirmed disruption" else 1.12
        value = max(1.0, base_eta * congestion * incident_penalty + risk_penalty)
        uncertainty = max(0.8, value * (0.08 + speed_drop * 0.12 + 0.10 * risk_score))
        confidence = max(0.45, min(0.96, 0.92 - uncertainty / max(value * 2, 1)))
        return Prediction("eta_minutes", value, max(0.1, value - uncertainty), value + uncertainty, confidence, uncertainty, self.model_name, self.model_version, ("base_route_eta", "speed_change", "incident_diagnosis", "route_risk"))
