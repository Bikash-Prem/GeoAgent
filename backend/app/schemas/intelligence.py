from typing import Any, Literal

from pydantic import BaseModel, Field


class DecisionAnalysisRequest(BaseModel):
    vehicle_id: str = Field(min_length=1, max_length=32)
    mission_id: str | None = None


class DecisionApproval(BaseModel):
    approved: bool
    selected_action_id: str | None = None
    comment: str | None = Field(default=None, max_length=1000)
    actor_id: str = Field(default="dispatcher", min_length=1, max_length=80)


class OutcomeInput(BaseModel):
    actual_eta_minutes: float | None = Field(default=None, ge=0)
    actual_risk: float | None = Field(default=None, ge=0, le=1)
    result: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    selected_action_id: str | None = None


class TelemetryInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(ge=0, le=300)
    heading: float = Field(ge=0, le=360)
    planned_route: list[dict[str, float]] | None = None


class SimulationRequest(BaseModel):
    scenario: Literal["accident_congestion", "road_closure", "traffic_spike", "competing_emergencies"] = "accident_congestion"
    seed: int = Field(default=7, ge=0)


class SituationResponse(BaseModel):
    situation_id: str
    vehicle_id: str
    vehicle: dict[str, Any]
    incidents: list[dict[str, Any]]
    telemetry: dict[str, Any]
    diagnosis: str
    diagnosis_confidence: float
    evidence: list[dict[str, Any]]
    stale_data: bool