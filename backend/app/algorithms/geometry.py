"""Pure geometry helpers (no DB / web dependencies, so they are unit-testable anywhere)."""
from __future__ import annotations

from math import cos, hypot, radians

M_PER_DEG_LAT = 111_320.0
DEVIATION_THRESHOLD_M = 250.0


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Equirectangular distance in metres - accurate to <0.5% at city scale."""
    mid = radians((lat1 + lat2) / 2)
    return hypot((lat1 - lat2) * M_PER_DEG_LAT, (lon1 - lon2) * M_PER_DEG_LAT * cos(mid))


def point_to_segment_m(lat: float, lon: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from a point to the SEGMENT a-b (not just to its end points)."""
    k = M_PER_DEG_LAT * cos(radians(lat))
    px, py = lon * k, lat * M_PER_DEG_LAT
    ax, ay = a[1] * k, a[0] * M_PER_DEG_LAT
    bx, by = b[1] * k, b[0] * M_PER_DEG_LAT
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_to_polyline_m(lat: float, lon: float, points: list[tuple[float, float]]) -> float:
    if not points:
        return 0.0
    if len(points) == 1:
        return metres(lat, lon, *points[0])
    return min(point_to_segment_m(lat, lon, a, b) for a, b in zip(points, points[1:]))


def nearest_vertex_m(lat: float, lon: float, points: list[tuple[float, float]]) -> float:
    """Old behaviour (distance to the closest vertex). Kept for the benchmark comparison."""
    return min((metres(lat, lon, p[0], p[1]) for p in points), default=0.0)
