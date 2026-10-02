from datetime import datetime
from math import hypot
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Incident, Telemetry, Vehicle
from app.models.intelligence import Mission, TrajectoryRecord
from .decision_models import EvidenceItem, SituationState


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return hypot((lat1 - lat2) * 111_000, (lon1 - lon2) * 105_000)


class SituationEngine:
    """Builds a grounded snapshot from persisted fleet, incident and telemetry state."""

    def __init__(self, db: Session):
        self.db = db

    def build(self, vehicle_id: str) -> SituationState:
        vehicle = self.db.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise ValueError("vehicle not found")
        incidents = list(self.db.scalars(select(Incident).where(Incident.active.is_(True))).all())
        mission = self.db.scalars(select(Mission).where(Mission.vehicle_id == vehicle_id, Mission.status == "active").order_by(Mission.created_at.desc())).first()
        fleet_vehicles = list(self.db.scalars(select(Vehicle).order_by(Vehicle.id)).all())
        telemetry = list(self.db.scalars(select(Telemetry).where(Telemetry.vehicle_id == vehicle_id).order_by(Telemetry.timestamp.desc()).limit(2)).all())
        trajectory = self.db.scalars(select(TrajectoryRecord).where(TrajectoryRecord.vehicle_id == vehicle_id).order_by(TrajectoryRecord.timestamp.desc())).first()
        nearest = min(incidents, key=lambda item: _distance_m(vehicle.lat, vehicle.lon, item.lat, item.lon), default=None)
        evidence: list[EvidenceItem] = []
        if nearest:
            distance = _distance_m(vehicle.lat, vehicle.lon, nearest.lat, nearest.lon)
            proximity = max(0.0, min(1.0, 1 - distance / max(nearest.radius_m * 3, 1)))
            evidence.append(EvidenceItem("incident-nearest", "incident_registry", "incident", nearest.id, 0.95, proximity, f"{nearest.title} is approximately {distance:.0f}m from {vehicle.name}."))
            evidence.append(EvidenceItem("incident-severity", "incident_registry", "severity", nearest.severity, 0.95, 0.8, f"Incident severity is {nearest.severity}."))
        speed_drop = 0.0
        if len(telemetry) == 2 and telemetry[1].speed_kmh:
            speed_drop = max(0.0, (telemetry[1].speed_kmh - telemetry[0].speed_kmh) / telemetry[1].speed_kmh)
        if speed_drop > 0:
            evidence.append(EvidenceItem("telemetry-speed", "telemetry", "speed_change", round(speed_drop, 3), 0.9, min(speed_drop, 1), f"Observed speed changed by {speed_drop:.0%} across the latest telemetry points."))
        if trajectory and trajectory.is_deviating:
            evidence.append(EvidenceItem("trajectory-deviation", "trajectory_engine", "route_deviation", round(trajectory.deviation_distance_m, 2), 0.96, 0.95, f"Vehicle is {trajectory.deviation_distance_m:.0f}m from the planned route baseline."))
        if nearest and nearest.kind in {"accident", "closure"} and (not telemetry or speed_drop >= 0.2 or (trajectory and trajectory.is_deviating)):
            diagnosis = f"{nearest.kind}-induced congestion"
            confidence = min(0.98, 0.55 + nearest.radius_m / 1000 + speed_drop * 0.25)
        elif nearest:
            diagnosis, confidence = "incident-related delay", 0.62
        elif speed_drop >= 0.2:
            diagnosis, confidence = "unexpected speed change", min(0.9, 0.5 + speed_drop / 2)
        else:
            diagnosis, confidence = "no confirmed disruption", 0.55
        highest_severity = max((item.severity for item in incidents), key=lambda value: {"high": 3, "medium": 2, "low": 1}.get(value, 0), default="none")
        traffic_factor = round(min(0.9, len(incidents) * 0.08 + {"high": 0.35, "medium": 0.2, "low": 0.1}.get(highest_severity, 0)), 3)
        return SituationState(
            situation_id=f"sit-{uuid4().hex[:12]}",
            vehicle_id=vehicle_id,
            vehicle={"id": vehicle.id, "name": vehicle.name, "status": vehicle.status, "lat": vehicle.lat, "lon": vehicle.lon, "speed_kmh": vehicle.speed_kmh, "heading": vehicle.heading, "hospital": vehicle.hospital, "updated_at": vehicle.updated_at.isoformat()},
            incidents=[{"id": item.id, "kind": item.kind, "severity": item.severity, "title": item.title, "lat": item.lat, "lon": item.lon, "radius_m": item.radius_m, "details": item.details} for item in incidents],
            telemetry={"latest": telemetry[0].timestamp.isoformat() if telemetry else None, "points": len(telemetry), "speed_drop": round(speed_drop, 3)},
            diagnosis=diagnosis,
            diagnosis_confidence=confidence,
            evidence=evidence,
            stale_data=not telemetry or (datetime.utcnow() - telemetry[0].timestamp).total_seconds() > 120,
            mission={"id": mission.id, "emergency_type": mission.emergency_type, "priority": mission.priority, "destination": mission.destination, "status": mission.status} if mission else None,
            road={"status": "disrupted" if nearest else "open", "nearest_incident_id": nearest.id if nearest else None, "closure_probability": round(0.7 if nearest and nearest.kind == "closure" else 0.1, 3)},
            traffic={"congestion_level": "high" if traffic_factor >= 0.4 else "medium" if traffic_factor >= 0.2 else "low", "congestion_factor": traffic_factor, "current_speed_kmh": vehicle.speed_kmh, "historical_speed_kmh": 62.0, "predicted_speed_kmh": round(max(5, vehicle.speed_kmh * (1 - traffic_factor)), 2), "uncertainty": round(traffic_factor * 0.5 + 0.05, 3)},
            fleet={"total": len(fleet_vehicles), "available": sum(item.status == "available" for item in fleet_vehicles), "occupied": sum(item.status == "active" for item in fleet_vehicles), "vehicles": [{"id": item.id, "status": item.status, "lat": item.lat, "lon": item.lon} for item in fleet_vehicles]},
            hospital={"name": vehicle.hospital, "capacity_status": "unknown", "availability_source": "not_connected"},
            prediction={"value": round(max(1.0, 17.2 * (1 + traffic_factor)), 2), "interval": {"lower": round(max(0.5, 17.2 * (1 + traffic_factor) - 2.0), 2), "upper": round(17.2 * (1 + traffic_factor) + 2.0, 2)}, "confidence": round(max(0.45, 0.9 - traffic_factor * 0.4), 3), "uncertainty": 2.0, "model": {"name": "heuristic-eta", "version": "1.0", "type": "baseline"}},
            trajectory={"deviation_distance_m": trajectory.deviation_distance_m, "route_progress": trajectory.route_progress, "is_deviating": trajectory.is_deviating, "planned_points": len(trajectory.planned_route or []), "actual_points": len(trajectory.actual_route or [])} if trajectory else None,
        )