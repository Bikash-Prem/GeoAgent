import asyncio
from math import hypot
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import AuditEvent, Incident, Vehicle
from app.models.intelligence import ActionEvaluationRecord, DecisionEvidence, DecisionRecord, DecisionTraceRecord, PredictionRecord, RouteRecord, SituationSnapshot
from .counterfactual import CounterfactualActionEngine
from .decision_models import DecisionResult
from .policy import RuleBasedPolicy
from .prediction import HeuristicETAPredictor
from .providers.adapters import FallbackRoutingProvider, GoogleRoutesProvider, MapboxRoutingProvider
from .providers.contracts import RouteObservation
from .situation import SituationEngine


def _distance_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    return hypot((a_lat - b_lat) * 111_000, (a_lon - b_lon) * 105_000)


class GeoAgentEngine:
    """Decision composition root.

    Routing is provider-backed: Google Routes is primary, Mapbox is optional,
    and a deterministic local geometry fallback is used only without credentials.
    The emergency decision layer remains independent of the routing vendor.
    """

    def __init__(self, db: Session):
        self.db = db
        self.predictor = HeuristicETAPredictor()
        self.policy = RuleBasedPolicy()
        self.actions = CounterfactualActionEngine(self.predictor)
        if settings.routing_provider == "google" and settings.google_routes_api_key:
            self.routing = GoogleRoutesProvider(settings.google_routes_api_key, settings.provider_timeout_seconds, settings.google_routing_preference)
        elif settings.routing_provider == "mapbox" and settings.mapbox_access_token:
            self.routing = MapboxRoutingProvider(settings.mapbox_access_token, settings.provider_timeout_seconds)
        else:
            self.routing = FallbackRoutingProvider()

    def analyze(self, vehicle_id: str, persist: bool = True) -> DecisionResult:
        """Sync entry point for normal API/test callers."""
        return asyncio.run(self.analyze_async(vehicle_id, persist=persist))

    async def analyze_async(self, vehicle_id: str, persist: bool = True) -> DecisionResult:
        situation = SituationEngine(self.db).build(vehicle_id)
        vehicle = self.db.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise ValueError("vehicle not found")

        destination = self._destination()
        observation: RouteObservation = await self.routing.routes((vehicle.lat, vehicle.lon), destination)
        if not observation.routes:
            raise ValueError(f"routing provider unavailable: {observation.status.message or observation.provider}")

        routes = self._enrich_routes(observation.routes, situation)
        self._last_routes = routes
        backup = self.db.scalars(select(Vehicle).where(Vehicle.status == "available", Vehicle.id != vehicle_id).order_by(Vehicle.id)).first()
        backup_eta = await self._backup_eta(vehicle, backup)

        action_evaluations = self.actions.evaluate(situation, routes, backup.id if backup else None, backup_eta)
        if action_evaluations:
            situation.prediction = action_evaluations[0].eta.as_dict()
        recommendation = self.policy.select(action_evaluations)
        reason = self._reason(recommendation, situation, routes)
        result = DecisionResult(
            f"dec-{uuid4().hex[:12]}", situation, action_evaluations, recommendation, reason,
            self.policy.name, self.policy.version,
        )
        if persist:
            self._persist(result, observation, routes)
        return result

    def recommendation(self, vehicle_id: str) -> dict:
        """Read-only compatibility endpoint: return the most recent decision."""
        decision = self.db.scalars(select(DecisionRecord).where(DecisionRecord.vehicle_id == vehicle_id).order_by(DecisionRecord.created_at.desc())).first()
        if decision is None:
            raise ValueError("no decision exists; call POST /api/v1/decisions/analyze first")
        actions = self.db.scalars(select(ActionEvaluationRecord).where(ActionEvaluationRecord.decision_id == decision.id).order_by(ActionEvaluationRecord.id)).all()
        situation = self.db.get(SituationSnapshot, decision.situation_id)
        if situation is None:
            raise ValueError("decision situation snapshot not found")
        routes: list[dict] = []
        for item in actions:
            payload = item.payload
            if payload.get("route_id"):
                routes.append({
                    "id": payload["route_id"],
                    "name": payload.get("route_name") or payload["route_id"],
                    "eta_min": payload.get("expected_eta_minutes", 0),
                    "delay_min": payload.get("delay_min", 0),
                    "uncertainty_min": payload.get("eta_uncertainty", {}).get("upper", 0) - payload.get("eta_uncertainty", {}).get("lower", 0),
                    "risk": payload.get("risk", {}).get("level", "unknown").lower(),
                    "distance_km": payload.get("distance_km", 0),
                    "points": payload.get("points", []),
                    "explanation": payload.get("route_explanation", "Route evaluated by the decision engine."),
                })
        action_payloads = [a.payload for a in actions]
        reroutes = [a for a in action_payloads if a.get("route_id")]
        current = reroutes[0] if reroutes else {"expected_eta_minutes": 0, "delay_min": 0}
        recommended = decision.recommended_action
        return {
            "vehicle_id": vehicle_id,
            "current_eta_min": current.get("expected_eta_minutes", 0),
            "delay_min": current.get("delay_min", 0),
            "cause": situation.payload.get("diagnosis", "unknown"),
            "confidence": situation.payload.get("diagnosis_confidence", 0),
            "evidence": [item.get("explanation", "") for item in situation.payload.get("evidence", [])],
            "routes": routes,
            "backup_vehicle_id": next((a.get("vehicle_id") for a in action_payloads if a.get("action") == "dispatch_backup"), None),
            "backup_eta_min": next((a.get("expected_eta_minutes") for a in action_payloads if a.get("action") == "dispatch_backup"), None),
            "decision_id": decision.id,
            "reasoning": decision.reasoning,
            "decision": {"decision_id": decision.id, "recommended_action": recommended, "actions": action_payloads, "situation": situation.payload},
        }

    def _destination(self) -> tuple[float, float]:
        return settings.destination_lat, settings.destination_lon

    async def _backup_eta(self, vehicle: Vehicle, backup: Vehicle | None) -> float | None:
        if not backup:
            return None
        observation = await self.routing.routes((backup.lat, backup.lon), (vehicle.lat, vehicle.lon))
        if observation.routes:
            return round(float(observation.routes[0]["eta_min"]), 2)
        return None

    def _enrich_routes(self, provider_routes: list[dict], situation) -> list[dict]:
        min_eta = min(float(route.get("eta_min", 0)) for route in provider_routes)
        enriched: list[dict] = []
        for index, route in enumerate(provider_routes):
            risk_score, reasons = self._route_risk(route, situation)
            risk_level = "high" if risk_score >= 0.67 else "medium" if risk_score >= 0.34 else "low"
            eta = float(route.get("eta_min", 0))
            uncertainty = max(0.6, float(route.get("traffic_delay_min", 0)) * 0.35 + risk_score * 2.0)
            enriched.append({
                **route,
                "name": route.get("name") or ("Primary route" if index == 0 else f"Alternative {index}"),
                "eta_min": round(eta, 2),
                "delay_min": round(eta - min_eta, 2),
                "uncertainty_min": round(uncertainty, 2),
                "risk": risk_level,
                "risk_score": round(risk_score, 3),
                "delay_probability": round(min(0.95, max(0.03, (float(route.get("traffic_delay_min", 0)) / max(eta, 1)) + risk_score * 0.25)), 3),
                "risk_reasons": reasons,
                "explanation": " ".join(reasons) if reasons else "No active incident intersects the returned route; provider ETA used as the routing baseline.",
            })
        return enriched

    @staticmethod
    def _route_risk(route: dict, situation) -> tuple[float, list[str]]:
        points = route.get("points", [])
        score = 0.05
        reasons: list[str] = []
        for incident in situation.incidents:
            nearest = min((_distance_m(p["lat"], p["lon"], incident["lat"], incident["lon"]) for p in points), default=float("inf"))
            radius = float(incident.get("radius_m", 150))
            if nearest <= radius:
                severity = {"high": 0.72, "medium": 0.48, "low": 0.28}.get(incident.get("severity"), 0.25)
                score = max(score, severity)
                reasons.append(f"passes through {incident.get('title', incident.get('id'))}")
            elif nearest <= radius * 2.5:
                severity = {"high": 0.45, "medium": 0.3, "low": 0.2}.get(incident.get("severity"), 0.2)
                score = max(score, severity)
                reasons.append(f"passes near {incident.get('title', incident.get('id'))}")
        if situation.traffic and situation.traffic.get("congestion_factor") is not None:
            score = max(score, min(0.9, float(situation.traffic["congestion_factor"])))
        return min(score, 0.99), reasons

    @staticmethod
    def _reason(recommendation, situation, routes) -> str:
        action = recommendation.action_type
        if action == "reroute":
            route = next((r for r in routes if r.get("id") == recommendation.route_id), None)
            why = ", ".join(route.get("risk_reasons", [])) if route else "lower evaluated route risk"
            return f"Reroute selected after comparing provider ETA, route risk, uncertainty and incident proximity. {why or 'The selected route has the strongest evaluated trade-off.'}"
        if action == "dispatch_backup":
            return "Backup dispatch is selected because the available response unit provides a grounded response option without requiring a route change for the active vehicle."
        if action == "reroute_and_dispatch":
            return "Combined reroute and backup dispatch has the strongest response trade-off after considering ETA, route risk and available fleet resources."
        return f"Continue remains the selected action under the observed situation: {situation.diagnosis}."

    def _persist(self, result: DecisionResult, observation: RouteObservation, routes: list[dict]) -> None:
        self.db.add(DecisionRecord(id=result.decision_id, situation_id=result.situation.situation_id, vehicle_id=result.situation.vehicle_id, recommended_action=result.recommendation.as_dict(), reasoning=result.reason, policy_name=result.policy_name, policy_version=result.policy_version))
        self.db.add(SituationSnapshot(id=result.situation.situation_id, vehicle_id=result.situation.vehicle_id, payload=result.situation.as_dict()))
        for item in result.situation.evidence:
            self.db.add(DecisionEvidence(decision_id=result.decision_id, evidence_id=item.evidence_id, payload=item.as_dict()))
        route_map = {action.route_id: action for action in result.actions if action.route_id}
        for action in result.actions:
            payload = action.as_dict()
            if action.route_id:
                route = next((r for r in routes if r.get("id") == action.route_id), {})
                payload.update({"route_name": route.get("name"), "delay_min": route.get("delay_min", 0), "distance_km": route.get("distance_km", 0), "points": route.get("points", []), "route_explanation": route.get("explanation", "")})
                self.db.add(RouteRecord(decision_id=result.decision_id, route_id=action.route_id, payload=payload))
            self.db.add(ActionEvaluationRecord(decision_id=result.decision_id, action_id=action.action_id, payload=payload))
            self.db.add(PredictionRecord(decision_id=result.decision_id, prediction_type="eta", payload=action.eta.as_dict(), model_name=action.eta.model_name, model_version=action.eta.model_version))
        events = (
            ("routing_observation", {"provider": observation.provider, "status": {"name": observation.status.name, "mode": observation.status.mode, "available": observation.status.available, "stale": observation.status.stale, "message": observation.status.message, "observed_at": observation.status.observed_at.isoformat()}, "route_count": len(observation.routes), "routes": observation.routes}),
            ("situation", result.situation.as_dict()),
            ("evidence", {"items": [item.as_dict() for item in result.situation.evidence]}),
            ("diagnosis", {"cause": result.situation.diagnosis, "confidence": result.situation.diagnosis_confidence}),
            ("predictions", {"items": [item.eta.as_dict() for item in result.actions]}),
            ("actions_evaluated", {"actions": [item.as_dict() for item in result.actions]}),
            ("recommendation", result.recommendation.as_dict()),
        )
        for event_type, payload in events:
            self.db.add(DecisionTraceRecord(decision_id=result.decision_id, event_type=event_type, payload=payload))
        self.db.add(AuditEvent(vehicle_id=result.situation.vehicle_id, event_type="decision_generated", payload={"decision_id": result.decision_id, "situation_id": result.situation.situation_id, "action": result.recommendation.action_type, "routing_provider": observation.provider}))
        self.db.commit()
