from typing import Literal

from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    kind: Literal["accident", "closure", "traffic", "medical"]
    severity: Literal["high", "medium", "low"] = "high"
    title: str = Field(min_length=3, max_length=160)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: float = Field(default=180, ge=30, le=2000)
    details: str | None = Field(default=None, max_length=1000)


class HospitalUpdate(BaseModel):
    icu: float | None = Field(default=None, ge=0, le=1)
    er: float | None = Field(default=None, ge=0, le=1)
    oxygen: float | None = Field(default=None, ge=0, le=1)
    accepting: bool | None = None


class AlertCreate(BaseModel):
    hospital_id: str
    vehicle_id: str | None = None
    incident_id: str | None = None
    stage: Literal["pre_alert", "en_route", "arrived"] = "en_route"
    priority: Literal["high", "medium", "low"] = "high"
    condition: str = Field(default="unknown", max_length=80)
    eta_min: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


class AckIn(BaseModel):
    actor: str = Field(default="hospital-desk", min_length=1, max_length=80)


class DispatchIn(BaseModel):
    incident_id: str | None = None
    actor: str = Field(default="dispatcher", max_length=80)


class CorridorIn(BaseModel):
    vehicle_id: str = Field(default="AMB-07", max_length=32)


class WhatIfIncident(BaseModel):
    kind: Literal["accident", "closure", "traffic"] = "accident"
    severity: Literal["high", "medium", "low"] = "high"
    lat: float
    lon: float
    radius_m: float = Field(default=220, ge=30, le=2000)


class WhatIfIn(BaseModel):
    vehicle_id: str = Field(default="AMB-07", max_length=32)
    preset: Literal["accident_congestion", "road_closure", "traffic_spike", "competing_emergencies", "clear_roads", "custom"] | None = "accident_congestion"
    incidents: list[WhatIfIncident] = []


class AirWeather(BaseModel):
    wind_kmh: float | None = Field(default=None, ge=0, le=200)
    visibility_km: float | None = Field(default=None, ge=0, le=50)
    cloud_base_m: float | None = Field(default=None, ge=0, le=12000)


class AirRescueIn(BaseModel):
    region: Literal["himachal", "uttarakhand", "ladakh"] = "himachal"
    weather: AirWeather | None = None
    actor: str = Field(default="dispatcher", max_length=80)
