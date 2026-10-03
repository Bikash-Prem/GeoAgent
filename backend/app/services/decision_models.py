from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    source: str
    evidence_type: str
    value: Any
    confidence: float
    relevance: float
    explanation: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "type": self.evidence_type,
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "relevance": round(self.relevance, 3),
            "explanation": self.explanation,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class Prediction:
    name: str
    value: float
    lower: float
    upper: float
    confidence: float
    uncertainty: float
    model_name: str
    model_version: str
    features: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "prediction": round(self.value, 2),
            "interval": {"lower": round(self.lower, 2), "upper": round(self.upper, 2)},
            "confidence": round(self.confidence, 3),
            "uncertainty": round(self.uncertainty, 2),
            "model": {"name": self.model_name, "version": self.model_version, "type": "baseline"},
            "features": list(self.features),
        }


@dataclass
class SituationState:
    situation_id: str
    vehicle_id: str
    vehicle: dict[str, Any]
    incidents: list[dict[str, Any]]
    telemetry: dict[str, Any]
    diagnosis: str
    diagnosis_confidence: float
    evidence: list[EvidenceItem]
    stale_data: bool = False
    mission: dict[str, Any] | None = None
    road: dict[str, Any] | None = None
    traffic: dict[str, Any] | None = None
    fleet: dict[str, Any] | None = None
    hospital: dict[str, Any] | None = None
    prediction: dict[str, Any] | None = None
    trajectory: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "situation_id": self.situation_id,
            "vehicle_id": self.vehicle_id,
            "vehicle": self.vehicle,
            "incidents": self.incidents,
            "telemetry": self.telemetry,
            "diagnosis": self.diagnosis,
            "diagnosis_confidence": round(self.diagnosis_confidence, 3),
            "evidence": [item.as_dict() for item in self.evidence],
            "stale_data": self.stale_data,
            "mission": self.mission,
            "road": self.road,
            "traffic": self.traffic,
            "fleet": self.fleet,
            "hospital": self.hospital,
            "prediction": self.prediction,
            "trajectory": self.trajectory,
        }


@dataclass
class ActionEvaluation:
    action_id: str
    action_type: str
    vehicle_id: str
    eta: Prediction
    risk_score: float
    risk_level: str
    delay_probability: float
    resource_impact: str
    coverage_change: float
    affected_missions: list[str]
    confidence: float
    evidence_ids: list[str]
    route_id: str | None = None
    backup_vehicle_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action": self.action_type,
            "vehicle_id": self.vehicle_id,
            "route_id": self.route_id,
            "backup_vehicle_id": self.backup_vehicle_id,
            "expected_eta_minutes": round(self.eta.value, 2),
            "eta_uncertainty": {"lower": round(self.eta.lower, 2), "upper": round(self.eta.upper, 2), "confidence": round(self.eta.confidence, 3)},
            "risk": {"level": self.risk_level, "score": round(self.risk_score, 3)},
            "delay_probability": round(self.delay_probability, 3),
            "resource_impact": self.resource_impact,
            "fleet_coverage_change": round(self.coverage_change, 3),
            "affected_missions": self.affected_missions,
            "confidence": round(self.confidence, 3),
            "evidence_ids": self.evidence_ids,
        }


@dataclass
class DecisionResult:
    decision_id: str
    situation: SituationState
    actions: list[ActionEvaluation]
    recommendation: ActionEvaluation
    reason: str
    policy_name: str = "rule-based-safety-first"
    policy_version: str = "1.0"

    def as_dict(self) -> dict[str, Any]:
        recommendation = self.recommendation.as_dict()
        return {
            "decision_id": self.decision_id,
            "mission_id": None,
            "recommended_action": recommendation,
            "expected_eta_minutes": recommendation["expected_eta_minutes"],
            "eta_uncertainty": recommendation["eta_uncertainty"],
            "risk": recommendation["risk"],
            "fleet_impact": {"level": recommendation["resource_impact"], "coverage_change": recommendation["fleet_coverage_change"]},
            "alternatives": [action.as_dict() for action in self.actions if action.action_id != self.recommendation.action_id],
            "evidence": [item.as_dict() for item in self.situation.evidence],
            "reasoning": self.reason,
            "requires_human_approval": True,
            "created_at": datetime.utcnow().isoformat(),
            "model_versions": {"eta": "heuristic-1.1", "policy": self.policy_version},
            "situation": self.situation.as_dict(),
        }