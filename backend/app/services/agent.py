from collections.abc import Callable
from inspect import Parameter, signature
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.intelligence import AgentRun, ToolCall
from .decision_models import SituationState


class AgentTool:
    def __init__(self, name: str, handler: Callable[..., Any], description: str = ""):
        self.name, self.handler = name, handler
        self.description = description
        self.parameters = list(signature(handler).parameters)


class ToolRegistry:
    def __init__(self): self._tools: dict[str, AgentTool] = {}
    def register(self, tool: AgentTool): self._tools[tool.name] = tool
    def call(self, name: str, **arguments: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"tool is not allowed: {name}")
        tool = self._tools[name]
        unexpected = set(arguments) - set(tool.parameters)
        missing = {parameter for parameter in tool.parameters if signature(tool.handler).parameters[parameter].default is Parameter.empty and parameter not in arguments}
        if unexpected or missing:
            raise ValueError(f"invalid arguments for {name}: unexpected={sorted(unexpected)}, missing={sorted(missing)}")
        return tool.handler(**arguments)
    def names(self) -> list[str]: return sorted(self._tools)
    def schemas(self) -> list[dict[str, Any]]: return [{"name": item.name, "description": item.description, "parameters": item.parameters} for item in self._tools.values()]


class GeoAgent:
    """Deterministic grounded orchestrator. No LLM is required for correctness."""

    def __init__(self, situation: SituationState, registry: ToolRegistry | None = None, db: Session | None = None):
        self.situation, self.registry = situation, registry or ToolRegistry()
        self.db = db
        self.registry.register(AgentTool("get_vehicle_state", lambda vehicle_id: situation.vehicle if vehicle_id == situation.vehicle_id else None, "Read persisted vehicle state."))
        self.registry.register(AgentTool("get_traffic_state", lambda: situation.traffic, "Read current and predicted traffic state."))
        self.registry.register(AgentTool("get_incidents", lambda: situation.incidents, "Read active incident evidence."))
        self.registry.register(AgentTool("get_available_ambulances", lambda: [item for item in (situation.fleet or {}).get("vehicles", []) if item["status"] == "available"], "Read available fleet resources."))
        self.registry.register(AgentTool("get_fleet_coverage", lambda: {"available": (situation.fleet or {}).get("available", 0), "occupied": (situation.fleet or {}).get("occupied", 0)}, "Read fleet coverage state."))
        self.registry.register(AgentTool("get_hospital_state", lambda: situation.hospital, "Read hospital state; unknown when no feed is connected."))
        self.registry.register(AgentTool("get_situation", lambda: situation.as_dict(), "Read the complete grounded situation snapshot."))

    def analyze(self) -> dict[str, Any]:
        run_id = f"agent-{uuid4().hex[:12]}"
        calls = {
            "vehicle": self.registry.call("get_vehicle_state", vehicle_id=self.situation.vehicle_id),
            "traffic": self.registry.call("get_traffic_state"),
            "incidents": self.registry.call("get_incidents"),
            "fleet": self.registry.call("get_fleet_coverage"),
            "hospital": self.registry.call("get_hospital_state"),
        }
        if self.db:
            self.db.add(AgentRun(id=run_id, situation_id=self.situation.situation_id, mode="deterministic-fallback", grounding=[item.evidence_id for item in self.situation.evidence]))
            for name, value in calls.items():
                self.db.add(ToolCall(agent_run_id=run_id, tool_name=name, arguments={}, success=value is not None))
            self.db.commit()
        return {"agent_run_id": run_id, "agent_mode": "deterministic-fallback", "tools": self.registry.schemas(), "called_tools": list(calls), "grounding": [item.evidence_id for item in self.situation.evidence], "missing_evidence": ["hospital_capacity"] if (self.situation.hospital or {}).get("capacity_status") == "unknown" else []}