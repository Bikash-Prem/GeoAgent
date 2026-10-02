from datetime import datetime
from math import hypot

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Telemetry, Vehicle
from app.models.intelligence import TrajectoryRecord


def distance_m(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    return hypot((lat_a - lat_b) * 111_000, (lon_a - lon_b) * 105_000)


class TrajectoryEngine:
    """Stores GPS observations and compares them with a planned polyline baseline."""

    def ingest(self, db: Session, vehicle_id: str, latitude: float, longitude: float, speed_kmh: float, heading: float, planned_route: list[dict] | None = None) -> TrajectoryRecord:
        vehicle = db.get(Vehicle, vehicle_id)
        if vehicle is None:
            raise ValueError("vehicle not found")
        previous = db.scalars(select(TrajectoryRecord).where(TrajectoryRecord.vehicle_id == vehicle_id).order_by(TrajectoryRecord.timestamp.desc()).limit(1)).first()
        planned_route = planned_route or [{"lat": vehicle.lat, "lon": vehicle.lon}, {"lat": 12.972, "lon": 77.607}]
        nearest = min((distance_m(latitude, longitude, point["lat"], point["lon"]) for point in planned_route), default=0)
        progress = min(1.0, max(0.0, (previous.route_progress if previous else 0.0) + 0.02))
        record = TrajectoryRecord(vehicle_id=vehicle_id, latitude=latitude, longitude=longitude, speed_kmh=speed_kmh, heading=heading, planned_route=planned_route, actual_route=([{"lat": previous.latitude, "lon": previous.longitude}] if previous else []) + [{"lat": latitude, "lon": longitude}], deviation_distance_m=round(nearest, 2), route_progress=progress, is_deviating=nearest > 250 or (previous is not None and abs(speed_kmh - previous.speed_kmh) > 35), timestamp=datetime.utcnow())
        db.add(record)
        db.add(Telemetry(vehicle_id=vehicle_id, lat=latitude, lon=longitude, speed_kmh=speed_kmh, heading=heading, timestamp=record.timestamp))
        vehicle.lat, vehicle.lon, vehicle.speed_kmh, vehicle.heading, vehicle.updated_at = latitude, longitude, speed_kmh, heading, record.timestamp
        db.commit()
        db.refresh(record)
        return record
