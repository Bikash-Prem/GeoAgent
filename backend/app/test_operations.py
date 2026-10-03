"""Operations features through the real HTTP layer + SQLite: intake, dispatch, alerts, corridor, coverage, what-if, air, reports."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ops.db"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"
os.environ["API_KEY"] = ""
os.environ["TWIN_TICK_HZ"] = "0"  # tests drive the control loop explicitly

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    from app.db.session import engine
    engine.dispose()  # another test module may have removed its SQLite file; start from a fresh pool
    with TestClient(app) as c:
        yield c
    engine.dispose()
    for name in ("test_ops.db", "test_smoke.db"):
        if os.path.exists(name):
            os.remove(name)


def test_medical_call_is_dispatched_but_does_not_slow_roads(client):
    before = client.get("/api/recommendations/AMB-07").json()["routes"][0]["eta_min"]
    inc = client.post("/api/v1/incidents", json={"kind": "medical", "severity": "high", "title": "Collapsed pedestrian", "lat": 12.9712, "lon": 77.5960}).json()
    after = client.get("/api/recommendations/AMB-07").json()["routes"][0]["eta_min"]
    assert abs(before - after) < 1e-6
    plan = client.get(f"/api/v1/dispatch/plan?incident_id={inc['id']}").json()
    assert plan["ambulance"]["id"] in ("AMB-03", "AMB-07", "AMB-12") and plan["hospital"]["status"] != "DIVERT"
    assert plan["unit_options"] == sorted(plan["unit_options"], key=lambda o: o["score"])
    done = client.post("/api/v1/dispatch/execute", json={"incident_id": inc["id"]}).json()
    assert done["status"] == "assigned"
    alerts = client.get("/api/v1/hospitals/alerts").json()["alerts"]
    assert alerts and alerts[0]["stage"] == "pre_alert"
    assert client.post(f"/api/v1/hospitals/alerts/{alerts[0]['id']}/ack", json={"actor": "er"}).json()["acknowledged"] is True


def test_divert_hospital_is_never_chosen(client):
    client.post("/api/v1/hospitals/HOSP-01/capacity", json={"icu": 0.95})
    inc = client.post("/api/v1/incidents", json={"kind": "medical", "severity": "high", "title": "Chest pain", "lat": 12.9718, "lon": 77.6060}).json()
    plan = client.get(f"/api/v1/dispatch/plan?incident_id={inc['id']}").json()
    assert plan["hospital"]["id"] != "HOSP-01"
    client.post("/api/v1/hospitals/HOSP-01/capacity", json={"icu": 0.46})


def test_corridor_turns_route_signals_green(client):
    cor = client.post("/api/v1/corridor/activate", json={"vehicle_id": "AMB-07"}).json()
    green = {s["node"] for s in cor["signals"] if s["overridden"]}
    assert green and green <= set(cor["nodes"])
    assert client.post(f"/api/v1/corridor/{cor['id']}/deactivate").json()["active"] is False


def test_whatif_does_not_persist_and_closure_changes_decision(client):
    n_before = len(client.get("/api/v1/decisions?limit=200").json()["decisions"])
    out = client.post("/api/v1/whatif", json={"preset": "road_closure"}).json()
    assert out["persisted_decision"] is False and out["scenario"]["eta_min"] >= out["baseline"]["eta_min"]
    assert len(client.get("/api/v1/decisions?limit=200").json()["decisions"]) == n_before


def test_coverage_drops_when_a_unit_is_committed(client):
    cov = client.get("/api/v1/coverage").json()
    assert 0 <= cov["coverage_pct"] <= 100 and all(x["drop_pct"] >= 0 for x in cov["impact"])


def test_air_rescue_blocks_unsafe_weather(client):
    assert client.post("/api/v1/air-rescue/execute", json={"region": "ladakh", "weather": {"wind_kmh": 70}}).status_code == 409
    assert client.post("/api/v1/air-rescue/execute", json={"region": "ladakh"}).status_code == 200


def test_shift_report_and_csv(client):
    rec = client.get("/api/recommendations/AMB-07").json()
    client.post(f"/api/v1/decisions/{rec['decision_id']}/approve", json={"approved": True})
    rep = client.get("/api/v1/reports/shift").json()
    assert rep["decisions"]["approved"] >= 1 and rep["operations"]["dispatches"] >= 1
    assert client.get("/api/v1/reports/decisions.csv").text.startswith("decision_id,")


def test_hospital_question_is_answered_without_a_decision(client):
    out = client.post("/api/v1/agent/command", json={"text": "Which hospital has ICU capacity?"}).json()
    assert out["intent"] == "hospital" and out["decision_id"] is None

