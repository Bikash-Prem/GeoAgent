from datetime import datetime
from pydantic import BaseModel, Field

class VehicleOut(BaseModel):
    id: str; name: str; status: str; lat: float; lon: float; speed_kmh: float; heading: float; hospital: str | None
    updated_at: datetime
    class Config: from_attributes = True

class IncidentOut(BaseModel):
    id: str; kind: str; severity: str; title: str; lat: float; lon: float; radius_m: float; active: bool; details: str | None
    class Config: from_attributes = True

class RoutePoint(BaseModel):
    lat: float; lon: float

class RouteOut(BaseModel):
    id: str; name: str; eta_min: float; delay_min: float; uncertainty_min: float; risk: str; distance_km: float; points: list[RoutePoint]; explanation: str
    eta_lower: float | None = None; eta_upper: float | None = None; risk_score: float | None = None; incidents_hit: list[str] = []

class RecommendationOut(BaseModel):
    vehicle_id: str
    current_eta_min: float
    delay_min: float
    cause: str
    confidence: float
    evidence: list[str]
    routes: list[RouteOut]
    backup_vehicle_id: str | None
    backup_eta_min: float | None
    decision_id: str | None = None
    recommended_route_id: str | None = None
    decision: dict | None = None
    routing_source: dict | None = None

class ActionIn(BaseModel):
    action: str = Field(pattern="^(reroute|dispatch_backup|acknowledge)$")
    route_id: str | None = None

class HealthOut(BaseModel):
    status: str
    service: str
    database: str
    environment: str
