from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.algorithms.astar import build_demo_graph
from app.algorithms.routes import k_routes
from app.models.entities import AuditEvent, Vehicle
from app.models.intelligence import ActionEvaluationRecord, DecisionEvidence, DecisionRecord, DecisionTraceRecord, PredictionRecord, RouteRecord, SituationSnapshot
from .counterfactual import CounterfactualActionEngine
from .decision_models import DecisionResult
from .policy import RuleBasedPolicy
from .prediction import HeuristicETAPredictor
from .situation import SituationEngine


class GeoAgentEngine:
    """Decision composition root used by both legacy and versioned API routes."""

    def __init__(self, db: Session):
        self.db = db
        self.graph = build_demo_graph()
        self.predictor = HeuristicETAPredictor()
        self.policy = RuleBasedPolicy()
        self.actions = CounterfactualActionEngine(self.predictor)

    def analyze(self, vehicle_id: str) -> DecisionResult:
        situation = SituationEngine(self.db).build(vehicle_id)
        vehicle = self.db.get(Vehicle, vehicle_id)
        candidates = k_routes(self.graph, "A", "H", 3)
        backup = self.db.scalars(select(Vehicle).where(Vehicle.status == "available", Vehicle.id != vehicle_id).order_by(Vehicle.id)).first()
        backup_eta = self._backup_eta(vehicle, backup)
        routes = []
        for index, candidate in enumerate(candidates):
            risk = (0.78, 0.18, 0.38)[index] if situation.incidents else (0.22, 0.12, 0.2)[index]
            risk_level = "high" if risk >= 0.65 else "medium" if risk >= 0.3 else "low"
            base_eta = max(5.0, candidate.cost * 3.4)
            prediction = self.predictor.predict(base_eta, situation, risk * 1.2)
            routes.append({"id": f"route-{index + 1}", "name": "Current Route (Delayed)" if index == 0 else f"Alternative {index}", "eta_min": round(prediction.value, 2), "delay_min": round(prediction.value - 11.4, 2), "uncertainty_min": round(prediction.uncertainty, 2), "risk": risk_level, "distance_km": round(candidate.cost, 2), "points": [{"lat": self.graph.pos[node][0], "lon": self.graph.pos[node][1]} for node in candidate.path], "explanation": "Avoids the active incident corridor." if index == 1 else "Evaluated against current road risk and traffic evidence."})
        action_evaluations = self.actions.evaluate(situation, routes, backup.id if backup else None, backup_eta)
        if action_evaluations:
            situation.prediction = action_evaluations[0].eta.as_dict()
        recommendation = self.policy.select(action_evaluations)
        reason = self._reason(recommendation, situation)
        result = DecisionResult(f"dec-{uuid4().hex[:12]}", situation, action_evaluations, recommendation, reason, self.policy.name, self.policy.version)
        self._persist(result)
        return result

    def recommendation(self, vehicle_id: str) -> dict:
        result = self.analyze(vehicle_id)
        legacy_routes = self._legacy_routes(result.situation)
        current = legacy_routes[0] if legacy_routes else {"eta_min": 17.2, "delay_min": 6.8}
        payload = result.as_dict()
        return {"vehicle_id": vehicle_id, "current_eta_min": current["eta_min"], "delay_min": current["delay_min"], "cause": result.situation.diagnosis, "confidence": result.situation.diagnosis_confidence, "evidence": [item.explanation for item in result.situation.evidence], "routes": legacy_routes, "backup_vehicle_id": next((action.vehicle_id for action in result.actions if action.action_type == "dispatch_backup"), None), "backup_eta_min": next((action.eta.value for action in result.actions if action.action_type == "dispatch_backup"), None), "decision_id": result.decision_id, "decision": payload}

    def _legacy_routes(self, situation) -> list[dict]:
        routes = []
        for index, candidate in enumerate(k_routes(self.graph, "A", "H", 3)):
            risk = ("high", "low", "medium")[index] if situation.incidents else ("medium", "low", "low")[index]
            eta = round(max(5.0, candidate.cost * 3.4 + (3.0 if index == 0 and situation.incidents else 0)), 1)
            routes.append({"id": f"route-{index + 1}", "name": "Current Route (Delayed)" if index == 0 else f"Alternative {index}", "eta_min": eta, "delay_min": round(eta - 11.4, 1), "uncertainty_min": round(max(1.0, eta * (0.12 if risk == "low" else 0.2)), 1), "risk": risk, "distance_km": round(candidate.cost, 1), "points": [{"lat": self.graph.pos[node][0], "lon": self.graph.pos[node][1]} for node in candidate.path], "explanation": "Avoids the active incident corridor and reduces predicted delay." if index == 1 else "Candidate route evaluated against current traffic and incident risk."})
        return routes

    @staticmethod
    def _backup_eta(vehicle: Vehicle | None, backup: Vehicle | None) -> float | None:
        if not vehicle or not backup:
            return None
        return round(max(3.0, abs(vehicle.lat - backup.lat) * 7000 + abs(vehicle.lon - backup.lon) * 5000), 2)

    @staticmethod
    def _reason(recommendation, situation) -> str:
        if recommendation.action_type == "reroute":
            return "Reroute has the lowest combined ETA, incident risk and uncertainty among evaluated actions."
        if recommendation.action_type == "dispatch_backup":
            return "Dispatching the available backup provides the fastest grounded response while exposing a measurable coverage trade-off."
        return f"Continue is retained because no alternative dominates the current route under the observed {situation.diagnosis}."

    def _persist(self, result: DecisionResult) -> None:
        self.db.add(DecisionRecord(id=result.decision_id, situation_id=result.situation.situation_id, vehicle_id=result.situation.vehicle_id, recommended_action=result.recommendation.as_dict(), reasoning=result.reason, policy_name=result.policy_name, policy_version=result.policy_version))
        self.db.add(SituationSnapshot(id=result.situation.situation_id, vehicle_id=result.situation.vehicle_id, payload=result.situation.as_dict()))
        for item in result.situation.evidence:
            self.db.add(DecisionEvidence(decision_id=result.decision_id, evidence_id=item.evidence_id, payload=item.as_dict()))
        for action in result.actions:
            self.db.add(ActionEvaluationRecord(decision_id=result.decision_id, action_id=action.action_id, payload=action.as_dict()))
            if action.route_id:
                self.db.add(RouteRecord(decision_id=result.decision_id, route_id=action.route_id, payload={"action": action.as_dict()}))
            self.db.add(PredictionRecord(decision_id=result.decision_id, prediction_type="eta", payload=action.eta.as_dict(), model_name=action.eta.model_name, model_version=action.eta.model_version))
        events = (
            ("situation", result.situation.as_dict()),
            ("evidence", {"items": [item.as_dict() for item in result.situation.evidence]}),
            ("diagnosis", {"cause": result.situation.diagnosis, "confidence": result.situation.diagnosis_confidence}),
            ("predictions", {"items": [item.eta.as_dict() for item in result.actions]}),
            ("actions_evaluated", {"actions": [item.as_dict() for item in result.actions]}),
            ("recommendation", result.recommendation.as_dict()),
        )
        for event_type, payload in events:
            self.db.add(DecisionTraceRecord(decision_id=result.decision_id, event_type=event_type, payload=payload))
        self.db.add(AuditEvent(vehicle_id=result.situation.vehicle_id, event_type="decision_generated", payload={"decision_id": result.decision_id, "situation_id": result.situation.situation_id, "action": result.recommendation.action_type}))
        self.db.commit()
