from datetime import datetime
from hashlib import sha1

from sqlalchemy.orm import Session
from app.models.intelligence import SimulationRun


SCENARIOS = {
    "accident_congestion": "AMB-07 deviates after an accident increases congestion ahead.",
    "road_closure": "A road closure forces alternate route evaluation.",
    "traffic_spike": "A sudden traffic spike changes corridor travel times.",
    "competing_emergencies": "Two simultaneous emergencies compete for the nearest available backup.",
}


class SimulationEngine:
    def list_scenarios(self) -> list[dict[str, str]]:
        return [{"id": key, "description": value} for key, value in SCENARIOS.items()]

    def run(self, scenario_id: str, seed: int = 7, db: Session | None = None) -> dict:
        if scenario_id not in SCENARIOS:
            raise ValueError("unknown simulation scenario")
        run_id = f"sim-{sha1(f'{scenario_id}:{seed}'.encode()).hexdigest()[:12]}"
        state = {
            "mission": {"id": "SIM-MIS-01", "priority": 1 if scenario_id != "competing_emergencies" else 2},
            "vehicles": [{"id": "AMB-07", "status": "active"}, {"id": "AMB-12", "status": "available"}],
            "incidents": [{"id": "SIM-INC-01", "kind": "accident" if scenario_id == "accident_congestion" else "closure" if scenario_id == "road_closure" else "traffic", "severity": "high"}],
            "traffic": {"state": "deteriorating" if scenario_id in {"accident_congestion", "traffic_spike"} else "disrupted"},
            "fleet": {"available": 1, "coverage_tradeoff": "backup dispatch reduces available regional coverage"},
        }
        result = {"run_id": run_id, "scenario_id": scenario_id, "seed": seed, "status": "completed", "synthetic": True, "started_at": datetime.utcnow().isoformat(), "state": state, "events": ["scenario_initialized", "telemetry_ingested", "situation_snapshot_ready"]}
        if db is not None and db.get(SimulationRun, run_id) is None:
            db.add(SimulationRun(id=run_id, scenario_id=scenario_id, seed=seed, payload=result))
            db.commit()
        if db is not None and scenario_id == "accident_congestion":
            from .engine import GeoAgentEngine
            decision = GeoAgentEngine(db).analyze("AMB-07")
            result["decision_id"] = decision.decision_id
            result["events"].extend(["actions_evaluated", "policy_selected", "decision_traced"])
        return result