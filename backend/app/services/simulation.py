from datetime import datetime, timezone
from hashlib import sha1

from sqlalchemy.orm import Session

from app.models.intelligence import SimulationRun

SCENARIOS = {
    "accident_congestion": "Increase incident severity/congestion pressure and compare response actions.",
    "road_closure": "Treat the active corridor as unavailable and expose the need for an alternate route.",
    "traffic_spike": "Increase traffic delay pressure without changing the incident registry.",
    "competing_emergencies": "Reduce available backup coverage to expose a fleet trade-off.",
}


class SimulationEngine:
    def list_scenarios(self) -> list[dict[str, str]]:
        return [{"id": key, "description": value} for key, value in SCENARIOS.items()]

    def run(self, scenario_id: str, seed: int = 7, db: Session | None = None) -> dict:
        if scenario_id not in SCENARIOS:
            raise ValueError("unknown simulation scenario")
        run_id = f"sim-{sha1(f'{scenario_id}:{seed}'.encode()).hexdigest()[:12]}"
        result = {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "seed": seed,
            "status": "completed",
            "synthetic": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "events": ["scenario_initialized", "counterfactual_state_created"],
            "state": self._scenario_state(scenario_id, seed),
        }
        if db is not None:
            from .engine import GeoAgentEngine
            baseline = GeoAgentEngine(db).analyze("AMB-07", persist=False)
            baseline_actions = [a.as_dict() for a in baseline.actions]
            result["baseline_decision"] = {
                "recommended_action": baseline.recommendation.as_dict(),
                "actions": baseline_actions,
                "reasoning": baseline.reason,
            }
            result["counterfactual"] = self._counterfactual(baseline_actions, scenario_id)
            result["events"].extend(["baseline_evaluated", "counterfactual_actions_scored"])
            if db.get(SimulationRun, run_id) is None:
                db.add(SimulationRun(id=run_id, scenario_id=scenario_id, seed=seed, payload=result))
                db.commit()
        return result

    @staticmethod
    def _scenario_state(scenario_id: str, seed: int) -> dict:
        pressure = {"accident_congestion": 0.25, "road_closure": 0.35, "traffic_spike": 0.2, "competing_emergencies": 0.1}[scenario_id]
        available = 1 if scenario_id != "competing_emergencies" else 0
        return {
            "scenario": scenario_id,
            "seed": seed,
            "traffic_pressure_delta": pressure,
            "route_constraints": ["corridor_blocked"] if scenario_id == "road_closure" else [],
            "fleet": {"available_backup_units": available, "coverage_constraint": scenario_id == "competing_emergencies"},
            "note": "Synthetic counterfactual input. It does not mutate live fleet or incident records.",
        }

    @staticmethod
    def _counterfactual(actions: list[dict], scenario_id: str) -> list[dict]:
        pressure = {"accident_congestion": 1.25, "road_closure": 1.45, "traffic_spike": 1.2, "competing_emergencies": 1.0}[scenario_id]
        results = []
        for action in actions:
            risk = float(action.get("risk", {}).get("score", 0.5))
            eta = float(action.get("expected_eta_minutes", 0))
            coverage = float(action.get("fleet_coverage_change", 0))
            if scenario_id == "road_closure" and action.get("action") in {"continue", "reroute"}:
                risk = min(0.99, risk + 0.2 if action.get("action") == "continue" else risk + 0.05)
            elif scenario_id != "competing_emergencies":
                eta *= pressure
            if scenario_id == "competing_emergencies" and action.get("action") in {"dispatch_backup", "reroute_and_dispatch"}:
                coverage -= 0.25
            score = eta + risk * 4 + max(0, -coverage) * 8
            results.append({"action_id": action.get("action_id"), "action": action.get("action"), "counterfactual_eta_min": round(eta, 2), "counterfactual_risk": round(risk, 3), "coverage_change": round(coverage, 3), "objective_score": round(score, 3)})
        return sorted(results, key=lambda x: x["objective_score"])
