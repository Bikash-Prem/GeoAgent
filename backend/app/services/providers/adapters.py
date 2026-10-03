from datetime import datetime, timezone
from math import cos, radians
from typing import Any

import httpx

from .contracts import FleetObservation, ProviderStatus, RouteObservation, TrafficObservation


def _decode_polyline(encoded: str) -> list[dict[str, float]]:
    """Decode Google's encoded polyline into GeoAgentic route points."""
    points: list[dict[str, float]] = []
    index = lat = lng = 0
    while index < len(encoded):
        result = shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        result = shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        points.append({"lat": lat / 1e5, "lon": lng / 1e5})
    return points


def _duration_seconds(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).rstrip("s"))


class GoogleRoutesProvider:
    """Google Maps Routes API adapter.

    Compute Routes is the real-road routing layer. GeoAgentic remains responsible
    for emergency risk, uncertainty, fleet impact and final decision logic.
    """

    def __init__(self, api_key: str, timeout: float = 8.0, routing_preference: str = "TRAFFIC_AWARE"):
        self.api_key = api_key
        self.timeout = timeout
        self.routing_preference = routing_preference

    async def routes(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteObservation:
        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        body = {
            "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
            "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
            "travelMode": "DRIVE",
            "routingPreference": self.routing_preference,
            "computeAlternativeRoutes": True,
            "units": "METRIC",
        }
        field_mask = "routes.duration,routes.staticDuration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.description,routes.travelAdvisory"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=body, headers=headers)
                response.raise_for_status()
                payload = response.json()
            routes: list[dict[str, Any]] = []
            for index, item in enumerate(payload.get("routes", [])):
                duration = _duration_seconds(item.get("duration")) / 60.0
                static_duration = _duration_seconds(item.get("staticDuration")) / 60.0
                distance = float(item.get("distanceMeters", 0)) / 1000.0
                encoded = item.get("polyline", {}).get("encodedPolyline", "")
                routes.append({
                    "id": f"google-route-{index + 1}",
                    "name": item.get("description") or ("Google primary route" if index == 0 else f"Google alternative {index}"),
                    "eta_min": round(duration, 2),
                    "static_eta_min": round(static_duration or duration, 2),
                    "distance_km": round(distance, 3),
                    "traffic_delay_min": round(max(0.0, duration - static_duration), 2),
                    "points": _decode_polyline(encoded) if encoded else [
                        {"lat": origin[0], "lon": origin[1]},
                        {"lat": destination[0], "lon": destination[1]},
                    ],
                    "provider": "google",
                    "traffic_aware": self.routing_preference != "TRAFFIC_UNAWARE",
                    "warnings": item.get("travelAdvisory", {}).get("warnings", []),
                })
            status = ProviderStatus("google-routes", "live", bool(routes), not bool(routes), None if routes else "No route returned")
            return RouteObservation("google", routes, status)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            return RouteObservation("google", [], ProviderStatus("google-routes", "live", False, True, str(error)))


class MapboxRoutingProvider:
    def __init__(self, token: str, timeout: float = 5.0):
        self.token, self.timeout = token, timeout

    async def routes(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteObservation:
        url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
        params = {"alternatives": "true", "geometries": "geojson", "overview": "full", "access_token": self.token}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            routes = [{"id": f"mapbox-{index + 1}", "name": f"Mapbox route {index + 1}", "distance_km": item["distance"] / 1000, "eta_min": item["duration"] / 60, "traffic_delay_min": 0.0, "points": [{"lat": point[1], "lon": point[0]} for point in item.get("geometry", {}).get("coordinates", [])], "provider": "mapbox", "traffic_aware": False} for index, item in enumerate(payload.get("routes", []))]
            return RouteObservation("mapbox", routes, ProviderStatus("mapbox", "live", bool(routes), not bool(routes)))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            return RouteObservation("mapbox", [], ProviderStatus("mapbox", "live", False, True, str(error)))


class TomTomTrafficProvider:
    def __init__(self, api_key: str, timeout: float = 5.0):
        self.api_key, self.timeout = api_key, timeout

    async def traffic(self, latitude: float, longitude: float) -> TrafficObservation:
        url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
        params = {"point": f"{latitude},{longitude}", "key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json().get("flowSegmentData", {})
            current = float(data.get("currentSpeed", 0))
            free_flow = float(data.get("freeFlowSpeed", current or 1))
            return TrafficObservation("tomtom", {"current_speed_kmh": current, "free_flow_speed_kmh": free_flow, "congestion_factor": round(max(0, 1 - current / free_flow), 3)}, ProviderStatus("tomtom", "live", True))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            return TrafficObservation("tomtom", {}, ProviderStatus("tomtom", "live", False, True, str(error)))


class TraccarFleetProvider:
    def __init__(self, base_url: str, username: str = "", password: str = "", timeout: float = 5.0):
        self.base_url, self.auth, self.timeout = base_url.rstrip("/"), (username, password) if username else None, timeout

    async def vehicles(self) -> FleetObservation:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/positions", auth=self.auth)
                response.raise_for_status()
                positions = response.json()
            vehicles = [{"device_id": str(item["deviceId"]), "lat": item["latitude"], "lon": item["longitude"], "speed_kmh": round(item.get("speed", 0) * 1.852, 1), "heading": item.get("course", 0), "fix_time": item.get("fixTime")} for item in positions]  # Traccar speed is in knots
            return FleetObservation("traccar", vehicles, ProviderStatus("traccar", "live", True))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            return FleetObservation("traccar", [], ProviderStatus("traccar", "live", False, True, str(error)))


class FallbackRoutingProvider:
    async def routes(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteObservation:
        # Deterministic geometry fallback for local development. It is explicitly
        # marked fallback and is never presented as a real-road provider.
        points = [
            {"lat": origin[0], "lon": origin[1]},
            {"lat": (origin[0] * 2 + destination[0]) / 3, "lon": (origin[1] * 2 + destination[1]) / 3},
            {"lat": (origin[0] + destination[0] * 2) / 3, "lon": (origin[1] + destination[1] * 2) / 3},
            {"lat": destination[0], "lon": destination[1]},
        ]
        distance_km = ((destination[0] - origin[0]) ** 2 + ((destination[1] - origin[1]) * cos(radians(origin[0]))) ** 2) ** 0.5 * 111
        route = {"id": "local-fallback-1", "name": "Local fallback geometry", "distance_km": round(distance_km, 3), "eta_min": round(max(1.0, distance_km / 0.7), 2), "traffic_delay_min": 0.0, "points": points, "provider": "local", "traffic_aware": False}
        return RouteObservation("local", [route], ProviderStatus("local", "fallback", True, False, "No live routing credentials; deterministic fallback is active"))


class FallbackTrafficProvider:
    async def traffic(self, latitude: float, longitude: float) -> TrafficObservation:
        return TrafficObservation("local", {"current_speed_kmh": None, "free_flow_speed_kmh": None, "congestion_factor": None}, ProviderStatus("local", "fallback", True, False, "No live traffic credentials; traffic is derived from persisted incidents/telemetry"))


class FallbackFleetProvider:
    async def vehicles(self) -> FleetObservation:
        return FleetObservation("local", [], ProviderStatus("local", "fallback", True, False, "Using persisted fleet state"))


# TomTom Incident Details v5: iconCategory -> GeoAgentic incident kind
TOMTOM_KIND = {1: "accident", 6: "traffic", 7: "closure", 8: "closure", 9: "closure", 14: "accident"}
TOMTOM_SEVERITY = {0: "low", 1: "low", 2: "medium", 3: "high", 4: "high"}


def normalize_tomtom_incidents(payload: dict) -> list[dict]:
    """Turn a TomTom incidentDetails response into incident-registry rows (only kinds the risk model understands)."""
    out = []
    for item in payload.get("incidents", []):
        props = item.get("properties", {}) or {}
        kind = TOMTOM_KIND.get(props.get("iconCategory"))
        geom = item.get("geometry", {}) or {}
        coords = geom.get("coordinates") or []
        if not kind or not coords:
            continue
        pts = [coords] if geom.get("type") == "Point" else coords
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        # radius covers the affected stretch (half its extent), clamped to a sensible range
        span = max((abs(p[1] - lat) * 111_000 + abs(p[0] - lon) * 108_000) for p in pts) if len(pts) > 1 else 120
        events = props.get("events") or [{}]
        ext_id = str(props.get("id") or item.get("id") or f"{lat:.5f},{lon:.5f}")
        out.append({"external_id": ext_id, "kind": kind, "severity": TOMTOM_SEVERITY.get(props.get("magnitudeOfDelay", 1), "medium"),
                    "title": (events[0].get("description") or kind.title())[:150], "lat": lat, "lon": lon,
                    "radius_m": round(max(80.0, min(600.0, span))), "details": f"TomTom incident, delay magnitude {props.get('magnitudeOfDelay', '?')}"})
    return out


class TomTomIncidentsProvider:
    """Live road incidents in a bounding box (TomTom Traffic Incident Details v5)."""

    FIELDS = "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,events{description}}}}"

    def __init__(self, api_key: str, timeout: float = 5.0):
        self.api_key, self.timeout = api_key, timeout

    async def incidents(self, bbox: tuple[float, float, float, float]) -> tuple[list[dict], ProviderStatus]:
        min_lat, min_lon, max_lat, max_lon = bbox
        params = {"key": self.api_key, "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}", "fields": self.FIELDS, "language": "en-GB", "timeValidityFilter": "present"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get("https://api.tomtom.com/traffic/services/5/incidentDetails", params=params)
                response.raise_for_status()
                rows = normalize_tomtom_incidents(response.json())
            return rows, ProviderStatus("tomtom-incidents", "live", True)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            return [], ProviderStatus("tomtom-incidents", "live", False, True, str(error))
