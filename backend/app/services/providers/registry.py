"""Builds the configured providers once, so every module (engine, control loop, status API) agrees on the source."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from .adapters import (FallbackFleetProvider, FallbackRoutingProvider, FallbackTrafficProvider, GoogleRoutesProvider, MapboxRoutingProvider,
                       TomTomIncidentsProvider, TomTomTrafficProvider, TraccarFleetProvider)


@lru_cache(maxsize=1)
def routing_provider():
    if settings.routing_provider == "google" and settings.google_routes_api_key:
        return GoogleRoutesProvider(settings.google_routes_api_key, settings.provider_timeout_seconds, settings.google_routing_preference)
    if settings.routing_provider == "mapbox" and settings.mapbox_access_token:
        return MapboxRoutingProvider(settings.mapbox_access_token, settings.provider_timeout_seconds)
    return None  # None => the incident-aware demo road graph is the routing source


@lru_cache(maxsize=1)
def traffic_provider():
    if settings.traffic_provider == "tomtom" and settings.tomtom_api_key:
        return TomTomTrafficProvider(settings.tomtom_api_key, settings.provider_timeout_seconds)
    return FallbackTrafficProvider()


@lru_cache(maxsize=1)
def incident_provider():
    if settings.traffic_provider == "tomtom" and settings.tomtom_api_key:
        return TomTomIncidentsProvider(settings.tomtom_api_key, settings.provider_timeout_seconds)
    return None


@lru_cache(maxsize=1)
def fleet_provider():
    if settings.fleet_provider == "traccar" and settings.fleet_api_url:
        return TraccarFleetProvider(settings.fleet_api_url, settings.fleet_api_username, settings.fleet_api_password, settings.provider_timeout_seconds)
    return FallbackFleetProvider()


def device_map() -> dict[str, str]:
    """TRACCAR_DEVICE_MAP="12:AMB-07,15:AMB-12" maps Traccar device ids to fleet vehicle ids."""
    out = {}
    for pair in settings.traccar_device_map.split(","):
        if ":" in pair:
            dev, vid = pair.split(":", 1)
            out[dev.strip()] = vid.strip()
    return out


def describe() -> list[dict]:
    r, t, f = routing_provider(), traffic_provider(), fleet_provider()
    return [
        {"name": "routing", "source": type(r).__name__.replace("Provider", "") if r else "Demo road graph", "mode": "live" if r else "demo",
         "detail": "Real-road route candidates, re-scored for incident risk" if r else "Incident-aware A* on the built-in demo graph"},
        {"name": "traffic", "source": "TomTom" if isinstance(t, TomTomTrafficProvider) else "Incident registry", "mode": "live" if isinstance(t, TomTomTrafficProvider) else "local",
         "detail": "Flow speed near the unit + live incidents imported to the registry" if isinstance(t, TomTomTrafficProvider) else "Incidents logged by dispatchers"},
        {"name": "fleet", "source": "Traccar" if isinstance(f, TraccarFleetProvider) else "Fleet database", "mode": "live" if isinstance(f, TraccarFleetProvider) else "local",
         "detail": f"GPS positions for {len(device_map())} mapped devices" if isinstance(f, TraccarFleetProvider) else "Positions from the API / demo telemetry stream"},
    ]
