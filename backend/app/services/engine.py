from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.algorithms.astar import build_demo_graph
from app.core.config import settings
from app.models.entities import AuditEvent, Vehicle
from app.models.intelligence import ActionEvaluationRecord, DecisionEvidence, DecisionRecord, DecisionTraceRecord, PredictionRecord, RouteRecord, SituationSnapshot
from .counterfactual import CounterfactualActionEngine
from .decision_models import DecisionResult
from .policy import RuleBasedPolicy
from .prediction import HeuristicETAPredictor
from .planner import display_routes, plan_routes
from .situation import SituationEngine
from .decision_models import EvidenceItem
from .providers.registry import routing_provider, traffic_provider
from .providers.adapters import TomTomTrafficProvider
from .providers.sync import run_sync
from .road_routes import provider_plan
from app.models.operations import Hospital
from datetime import datetime, timedelta
import time as _time

_traffic_cache: dict = {}


class GeoAgentEngine:
    """Decision composition root used by both legacy and versioned API routes."""

    def __init__(self, db: Session):
        self.db = db
        self.graph = build_demo_graph()
        self.predictor = HeuristicETAPredictor()
        self.policy = RuleBasedPolicy(settings.response_target_min)
        self.routes: list[dict] = []
        self.actions = CounterfactualActionEngine(self.predictor)

    def analyze(self, vehicle_id: str, persist: bool = True) -> DecisionResult:
        situation = SituationEngine(self.db).build(vehicle_id)
        vehicle = self.db.get(Vehicle, vehicle_id)
        backups = [(v.id, (v.lat, v.lon)) for v in self.db.scalars(select(Vehicle).where(Vehicle.status == "available", Vehicle.id != vehicle_id).order_by(Vehicle.id)).all()]
        plan = self._plan(situation, vehicle, backups)
        self._traffic_evidence(situation, vehicle)
        action_evaluations = self.actions.evaluate(situation, plan.routes, plan.backup_id, plan.backup_eta)
        self.routes = display_routes(plan, action_evaluations)
        situation.prediction = action_evaluations[0].eta.as_dict()
        recommendation = self.policy.select(action_evaluations)
        reason = self._reason(recommendation, action_evaluations, self.routes, self.policy.response_target_min)
        result = DecisionResult(f"dec-{uuid4().hex[:12]}", situation, action_evaluations, recommendation, reason, self.policy.name, self.policy.version)
        if persist:
            self._persist(result)
        return result

    # ── routing source: real roads when a provider is configured, demo graph otherwise (never silently) ──
    def _destination(self, vehicle) -> tuple[float, float]:
        if vehicle.hospital:
            h = self.db.scalars(select(Hospital).where(Hospital.name == vehicle.hospital)).first()
            if h:
                return (h.lat, h.lon)
        return (settings.destination_lat, settings.destination_lon)

    def _plan(self, situation, vehicle, backups):
        provider = routing_provider()
        if provider is not None:
            try:
                plan, obs = provider_plan(provider, situation.incidents, (vehicle.lat, vehicle.lon), self._destination(vehicle), backups)
            except Exception as error:  # network / parsing problems degrade to the graph, visibly
                plan, obs = None, None
                message = str(error)
            else:
                message = obs.status.message if obs else None
            if plan is not None:
                self.routing_source = {"source": obs.provider, "mode": "live", "routes": len(plan.routes)}
                situation.evidence.append(EvidenceItem("routing-provider", obs.provider, "route_source", obs.provider, 0.9, 0.6,
                                                       f"{len(plan.routes)} real-road routes from {obs.provider.title()}, re-scored for registry incidents."))
                return plan
            self.routing_source = {"source": "demo-graph", "mode": "fallback", "reason": message or "provider returned no route"}
            situation.evidence.append(EvidenceItem("routing-fallback", "routing", "route_source", "demo-graph", 0.9, 0.3,
                                                   f"Routing provider unavailable ({(message or 'no route')[:80]}); demo road graph used."))
        else:
            self.routing_source = {"source": "demo-graph", "mode": "demo"}
        return plan_routes(situation.incidents, (vehicle.lat, vehicle.lon), backups, self.graph)

    def _traffic_evidence(self, situation, vehicle) -> None:
        provider = traffic_provider()
        if not isinstance(provider, TomTomTrafficProvider):
            return
        key = (round(vehicle.lat, 3), round(vehicle.lon, 3))
        hit = _traffic_cache.get(key)
        if not hit or _time.time() - hit[0] > 60:
            try:
                hit = (_time.time(), run_sync(provider.traffic(vehicle.lat, vehicle.lon)))
                _traffic_cache[key] = hit
            except Exception:
                return
        obs = hit[1]
        t = obs.traffic or {}
        if obs.status.available and t.get("current_speed_kmh") is not None:
            situation.traffic = {**(situation.traffic or {}), **t, "source": "tomtom"}
            situation.evidence.append(EvidenceItem("traffic-flow", "tomtom", "flow_speed", t.get("congestion_factor"), 0.85, 0.7,
                                                   f"TomTom flow near {vehicle.name}: {t['current_speed_kmh']:.0f} km/h vs {t['free_flow_speed_kmh']:.0f} km/h free-flow ({round((t.get('congestion_factor') or 0) * 100)}% slower)."))

    def recommendation(self, vehicle_id: str) -> dict:
        result = self.analyze(vehicle_id)
        routes = self.routes
        current = routes[0]
        backup = next((a for a in result.actions if a.action_type == "dispatch_backup"), None)
        return {"routing_source": getattr(self, "routing_source", {"source": "demo-graph", "mode": "demo"}), "vehicle_id": vehicle_id, "current_eta_min": current["eta_min"], "delay_min": current["delay_min"], "cause": result.situation.diagnosis, "confidence": result.situation.diagnosis_confidence, "evidence": [item.explanation for item in result.situation.evidence], "routes": routes, "backup_vehicle_id": backup.vehicle_id if backup else None, "backup_eta_min": round(backup.eta.value, 2) if backup else None, "decision_id": result.decision_id, "recommended_route_id": result.recommendation.route_id, "decision": result.as_dict()}

    @staticmethod
    def _reason(rec, actions, routes, target) -> str:
        by_route = {r["id"]: r for r in routes}
        current = by_route.get("route-1")
        chosen = by_route.get(rec.route_id)
        backup = next((a for a in actions if a.action_type == "dispatch_backup"), None)
        if rec.action_type == "continue":
            return f"Continue on the current route: ETA {rec.eta.value:.1f} min ({rec.eta.lower:.1f}-{rec.eta.upper:.1f}), {rec.risk_level.lower()} risk. No evaluated alternative beats it on ETA and risk."
        if rec.action_type == "reroute":
            saved = current["eta_min"] - chosen["eta_min"]
            return f"Reroute to {chosen['name']}: {chosen['eta_min']:.1f} min vs {current['eta_min']:.1f} min on the current route ({saved:.1f} min saved), risk {current['risk']} -> {chosen['risk']}. {chosen['explanation']} Upper-bound ETA {chosen['eta_upper']:.1f} min is within the {target:.0f} min target, so no backup unit is spent."
        verb = "Reroute" if rec.action_type == "reroute_and_dispatch" else "Continue"
        eta_txt = f" (backup ETA {backup.eta.value:.1f} min)" if backup else ""
        return f"{verb} on {chosen['name']} AND dispatch {rec.backup_vehicle_id}{eta_txt}: even the best route is expected at {chosen['eta_min']:.1f} min with an upper bound of {chosen['eta_upper']:.1f} min, above the {target:.0f} min response target. Spending one backup unit reduces regional coverage."
        
    def _persist(self, result: DecisionResult) -> None:
        # A dashboard refresh must not flood the log: if the latest pending decision for this unit recommends the same
        # action on the same route with (almost) the same ETA, keep using it instead of writing a duplicate.
        last = self.db.scalars(select(DecisionRecord).where(DecisionRecord.vehicle_id == result.situation.vehicle_id).order_by(DecisionRecord.created_at.desc())).first()
        ra = result.recommendation.as_dict()
        if last is not None and last.status == "pending" and last.created_at and datetime.utcnow() - last.created_at < timedelta(minutes=5):
            prev = last.recommended_action or {}
            if (prev.get("action"), prev.get("route_id"), prev.get("backup_vehicle_id")) == (ra["action"], ra["route_id"], ra["backup_vehicle_id"]) \
                    and abs((prev.get("expected_eta_minutes") or 0) - ra["expected_eta_minutes"]) < 0.25:
                result.decision_id = last.id
                return
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
        self.db.add(AuditEvent(vehicle_id=result.situation.vehicle_id, event_type="decision_generated", payload={"decision_id": result.decision_id, "situation_id": result.situation.situation_id, "action": result.recommendation.action_type, "routing_source": getattr(self, "routing_source", {}).get("source")}))
        self.db.commit()
