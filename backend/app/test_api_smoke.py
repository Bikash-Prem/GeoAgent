"""End-to-end smoke test through the real HTTP layer + SQLite.
Run from backend/:   python -m pytest app/test_api_smoke.py -q      (needs: pip install -r requirements-dev.txt)
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_smoke.db"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"
os.environ["API_KEY"] = ""
os.environ["TWIN_TICK_HZ"] = "0"  # tests drive the control loop explicitly

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # context manager => lifespan => database seeding
        yield c
    if os.path.exists("test_smoke.db"):
        os.remove("test_smoke.db")


def test_recommendation_is_incident_aware_and_explained(client):
    r = client.get("/api/recommendations/AMB-07")
    assert r.status_code == 200
    body = r.json()
    assert len(body["routes"]) >= 2 and body["decision_id"]
    current = body["routes"][0]
    chosen = next(x for x in body["routes"] if x["id"] == body["recommended_route_id"])
    assert chosen["eta_min"] <= current["eta_min"]
    assert chosen["eta_lower"] <= chosen["eta_min"] <= chosen["eta_upper"]
    assert body["decision"]["requires_human_approval"] is True


def test_command_flow_and_human_approval(client):
    out = client.post("/api/v1/agent/command", json={"text": "Show the best alternative route for AMB-07"}).json()
    assert out["intent"] == "best_route" and out["decision_id"] and "min" in out["answer"]
    assert client.post("/api/v1/agent/command", json={"text": "approve the reroute"}).json()["decision_id"] is None
    ok = client.post(f"/api/v1/decisions/{out['decision_id']}/approve", json={"approved": True, "actor_id": "tester"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    trace = client.get(f"/api/v1/decisions/{out['decision_id']}/trace").json()
    assert "human_approval" in [e["event_type"] for e in trace["events"]]


def test_unknown_vehicle_is_404_and_benchmark_runs(client):
    assert client.post("/api/v1/agent/command", json={"text": "best route for AMB-99"}).status_code == 404
    bench = client.get("/api/v1/evaluation/run?n=40&seed=1").json()
    assert bench["synthetic"] is True and bench["targets"][-1]["status"] == "not_measured"
