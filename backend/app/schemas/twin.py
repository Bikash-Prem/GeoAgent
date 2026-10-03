from typing import Any, Literal

from pydantic import BaseModel, Field


class TwinCommand(BaseModel):
    action: Literal["start", "stop", "speed", "reset", "scenario", "dispatch", "approve", "reject"]
    speed: float = Field(default=1.0, ge=0.1, le=20)
    scenario_id: str | None = None
    decision_id: str | None = None


class TwinSnapshot(BaseModel):
    schema_version: str = "1.0"
    snapshot_id: str
    simulation_time: float
    running: bool
    speed: float
    vehicle: dict[str, Any]
    mission: dict[str, Any] | None
    incidents: list[dict[str, Any]]
    traffic: dict[str, Any] | None
    routes: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    decision: dict[str, Any] | None
    fleet: dict[str, Any] | None
    hospital: dict[str, Any] | None
    providers: list[dict[str, Any]]
    generated_at: str
    scenario_id: str = "evolving_stemi"
    patient: dict[str, Any] | None = None
    ecg: dict[str, Any] | None = None
    hospitals: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    impact: dict[str, Any] | None = None
    traffic_forecast: dict[str, Any] | None = None
    green_corridor: dict[str, Any] | None = None
    congestion_explanations: list[dict[str, Any]] = []
    dispatch: dict[str, Any] | None = None
    hospital_alerts: list[dict[str, Any]] = []