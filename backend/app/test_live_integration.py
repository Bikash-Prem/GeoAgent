"""Provider-backed routing, decision de-duplication and the control loop, through the real engine + SQLite."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_live.db"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"
os.environ["API_KEY"] = ""
os.environ["TWIN_TICK_HZ"] = "0"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.providers.contracts import ProviderStatus, RouteObservation


class FakeRoads:
    """Two real-road-like polylines from AMB-07 to City General: north (through INC-204) and south."""

    async def routes(self, origin, destination):
        north = [{"lat": origin[0], "lon": origin[1]}, {"lat": 12.9731, "lon": 77.5997}, {"lat": destination[0], "lon": destination[1]}]
        south = [{"lat": origin[0], "lon": origin[1]}, {"lat": 12.9655, "lon": 77.6020}, {"lat": destination[0], "lon": destination[1]}]
        return RouteObservation("google", [
            {"eta_min": 9.0, "static_eta_min": 8.0, "distance_km": 3.1, "traffic_delay_min": 1.0, "points": north},
            {"eta_min": 10.0, "static_eta_min": 9.5, "distance_km": 3.6, "traffic_delay_min": 0.5, "points": south},
        ], ProviderStatus("google-routes", "live", True))


class DeadRoads:
    async def routes(self, origin, destination):
        return RouteObservation("google", [], ProviderStatus("google-routes", "live", False, True, "HTTP 403"))


@pytest.fixture(scope="module")
def client():
    from app.db.session import engine
    engine.dispose()
    with TestClient(app) as c:
        yield c
    engine.dispose()
    for name in ("test_live.db", "test_smoke.db", "test_ops.db"):
        if os.path.exists(name):
            os.remove(name)


def test_refresh_reuses_the_same_pending_decision(client):
    a = client.get("/api/recommendations/AMB-07").json()["decision_id"]
    b = client.get("/api/recommendations/AMB-07").json()["decision_id"]
    assert a == b


def test_provider_routes_are_rescored_for_registry_incidents(client):
    from app.services import road_routes
    road_routes._cache.clear()
    with patch_provider(FakeRoads()):
        rec = client.get("/api/recommendations/AMB-07").json()
    assert rec["routing_source"]["source"] == "google" and rec["routing_source"]["mode"] == "live"
    north = rec["routes"][0]
    assert "INC-204" in north["incidents_hit"]          # the accident from the registry is on the north road
    assert north["eta_min"] > 9.0                        # so the provider's 9 min becomes slower
    assert rec["recommended_route_id"] == "route-2"      # and the clear south road wins
    assert any("Google" in e for e in rec["evidence"])


def test_provider_failure_falls_back_to_demo_graph_visibly(client):
    from app.services import road_routes
    road_routes._cache.clear()
    with patch_provider(DeadRoads()):
        rec = client.get("/api/recommendations/AMB-07").json()
    assert rec["routing_source"]["mode"] == "fallback" and "403" in rec["routing_source"]["reason"]
    assert any("demo road graph used" in e for e in rec["evidence"])


def test_control_loop_is_read_only_and_detects_drift(client):
    client.get("/api/recommendations/AMB-07")
    before = len(client.get("/api/v1/decisions?limit=200").json()["decisions"])
    assert client.post("/api/v1/twin/command", json={"action": "tick"}).json()["tick"] >= 1
    snap = client.get("/api/v1/twin/snapshot").json()
    assert snap["recommendation"]["action"] and snap["drift"] is None
    # a new closure on the recommended road changes what the engine would advise now
    chosen = next(r for r in snap["routes"] if r["id"] == snap["recommendation"]["route_id"])
    mid = chosen["points"][len(chosen["points"]) // 2]
    client.post("/api/v1/incidents", json={"kind": "closure", "severity": "high", "title": "Flyover shut", "lat": mid["lat"], "lon": mid["lon"], "radius_m": 250})
    client.post("/api/v1/twin/command", json={"action": "tick"})
    assert client.get("/api/v1/twin/snapshot").json()["drift"] is None   # debounced: one tick is not enough
    client.post("/api/v1/twin/command", json={"action": "tick"})
    snap = client.get("/api/v1/twin/snapshot").json()
    assert snap["drift"] is not None
    assert len(client.get("/api/v1/decisions?limit=200").json()["decisions"]) == before
    hist = client.get("/api/v1/twin/history").json()
    assert len(hist["snapshots"]) >= 2
    assert {p["name"] for p in client.get("/api/v1/twin/providers").json()["providers"]} == {"routing", "traffic", "fleet"}


from contextlib import contextmanager  # noqa: E402
from unittest.mock import patch  # noqa: E402


@contextmanager
def patch_provider(provider):
    with patch("app.services.engine.routing_provider", return_value=provider):
        yield
