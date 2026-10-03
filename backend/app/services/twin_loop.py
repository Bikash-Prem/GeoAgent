import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.entities import Vehicle
from app.models.intelligence import DecisionRecord, DecisionTraceRecord, SituationSnapshot
from app.schemas.twin import TwinCommand
from .engine import GeoAgentEngine
from .providers.adapters import FallbackFleetProvider, FallbackRoutingProvider, FallbackTrafficProvider, GoogleRoutesProvider, MapboxRoutingProvider, TomTomTrafficProvider, TraccarFleetProvider
from .providers.contracts import ProviderStatus
from .situation import SituationEngine


class TwinLoop:
    """Operational state loop for replay/live provider snapshots.

    It does not fabricate medical telemetry or persist a new decision every tick.
    Decision generation is read-only here; explicit analysis requests create records.
    """

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory
        self.running = True
        self.speed = 1.0
        self.scenario_id = "emergency_response"
        self.dispatch_active = False
        self.simulation_time = 0.0
        self.latest: dict | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self.task: asyncio.Task | None = None
        self.routing = self._routing_provider()
        self.traffic = TomTomTrafficProvider(settings.tomtom_api_key, settings.provider_timeout_seconds) if settings.traffic_provider == "tomtom" and settings.tomtom_api_key else FallbackTrafficProvider()
        self.fleet = TraccarFleetProvider(settings.fleet_api_url, settings.fleet_api_username, settings.fleet_api_password, settings.provider_timeout_seconds) if settings.fleet_provider == "traccar" and settings.fleet_api_url else FallbackFleetProvider()

    def _routing_provider(self):
        if settings.routing_provider == "google" and settings.google_routes_api_key:
            return GoogleRoutesProvider(settings.google_routes_api_key, settings.provider_timeout_seconds, settings.google_routing_preference)
        if settings.routing_provider == "mapbox" and settings.mapbox_access_token:
            return MapboxRoutingProvider(settings.mapbox_access_token, settings.provider_timeout_seconds)
        return FallbackRoutingProvider()

    async def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def _run(self) -> None:
        while True:
            if self.running:
                try:
                    await self.tick()
                except Exception:
                    # Provider/database failures degrade the stream rather than kill the server.
                    pass
            await asyncio.sleep(max(0.5, 1 / max(settings.twin_tick_hz, 0.01)))

    async def tick(self) -> dict:
        with self.session_factory() as db:
            vehicle = db.get(Vehicle, "AMB-07")
            if vehicle is None:
                return self.latest or {}
            situation = SituationEngine(db).build("AMB-07")
            decision = await GeoAgentEngine(db).analyze_async("AMB-07", persist=False)
            traffic = await self.traffic.traffic(vehicle.lat, vehicle.lon)
            fleet_status = await self.fleet.vehicles()
            route_status = await self.routing.routes((vehicle.lat, vehicle.lon), (settings.destination_lat, settings.destination_lon))
            statuses = [traffic.status, route_status.status, fleet_status.status]
            traffic_state = {**(situation.traffic or {})}
            if traffic.traffic:
                traffic_state.update(traffic.traffic)
            snapshot = {
                "schema_version": "2.0",
                "snapshot_id": f"snap-{uuid4().hex[:12]}",
                "simulation_time": round(self.simulation_time, 2),
                "running": self.running,
                "speed": self.speed,
                "scenario_id": self.scenario_id,
                "vehicle": situation.vehicle,
                "mission": situation.mission,
                "incidents": situation.incidents,
                "traffic": traffic_state,
                "routes": [
                    {"id": r.get("route_id"), "eta_min": r.eta.value, "risk": r.risk_level.lower()}
                    for r in decision.actions if r.route_id
                ],
                "actions": [action.as_dict() for action in decision.actions],
                "decision": decision.as_dict(),
                "fleet": situation.fleet,
                "hospital": situation.hospital,
                "timeline": self._timeline_state(),
                "dispatch": self._dispatch_state(situation),
                "traffic_forecast": self._traffic_forecast(traffic_state),
                "congestion_explanations": self._congestion_explanations(situation, traffic_state),
                "providers": [self._status_payload(status) for status in statuses],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.latest = snapshot
            self.simulation_time += self.speed
            # Snapshot persistence is bounded by the loop interval and is operational state, not a decision record.
            db.add(SituationSnapshot(id=snapshot["snapshot_id"], vehicle_id="AMB-07", payload=snapshot))
            db.commit()
        await self._publish(snapshot)
        return snapshot

    async def command(self, command: TwinCommand) -> dict:
        if command.action == "start":
            self.running = True
            self.speed = command.speed
        elif command.action == "stop":
            self.running = False
        elif command.action == "speed":
            self.speed = command.speed
        elif command.action in {"scenario", "reset"}:
            self.simulation_time = 0.0
            self.scenario_id = command.scenario_id or "emergency_response"
            self.running = command.action == "scenario"
            self.dispatch_active = False
        elif command.action == "dispatch":
            self.dispatch_active = True
            self.running = True
        elif command.action in {"approve", "reject"} and command.decision_id:
            with self.session_factory() as db:
                decision = db.get(DecisionRecord, command.decision_id)
                if decision:
                    decision.status = "approved" if command.action == "approve" else "rejected"
                    db.add(DecisionTraceRecord(decision_id=command.decision_id, event_type=f"twin_command_{command.action}", payload={"action": command.action}))
                    db.commit()
        return {"ok": True, "action": command.action, "running": self.running, "speed": self.speed, "dispatch_active": self.dispatch_active, "snapshot": self.latest}

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=2)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)

    async def _publish(self, snapshot: dict) -> None:
        for queue in list(self.subscribers):
            if queue.full():
                queue.get_nowait()
            await queue.put(snapshot)

    def provider_status(self) -> list[dict]:
        return [
            {"name": "routing", "mode": "live" if isinstance(self.routing, (GoogleRoutesProvider, MapboxRoutingProvider)) else "fallback"},
            {"name": "traffic", "mode": "live" if isinstance(self.traffic, TomTomTrafficProvider) else "fallback"},
            {"name": "fleet", "mode": "live" if isinstance(self.fleet, TraccarFleetProvider) else "fallback"},
        ]

    def _timeline_state(self) -> list[dict]:
        phases = ["observe", "diagnose", "predict", "simulate", "recommend", "human_review"]
        current = min(len(phases) - 1, int(self.simulation_time / 6))
        return [{"label": phase, "status": "complete" if index < current else "active" if index == current and self.running else "pending"} for index, phase in enumerate(phases)]

    @staticmethod
    def _traffic_forecast(traffic: dict) -> dict:
        congestion = traffic.get("congestion_factor")
        if congestion is None:
            return {"horizon_min": 15, "trend": "unknown", "current_congestion": None, "predicted_congestion": None, "points": [], "model": "not_available"}
        congestion = float(congestion)
        trend = "worsening" if congestion >= 0.4 else "stable" if congestion >= 0.2 else "easing"
        points = [round(min(1, max(0, congestion + offset)), 2) for offset in (0, 0.04, 0.08, 0.12)]
        return {"horizon_min": 15, "trend": trend, "current_congestion": round(congestion, 2), "predicted_congestion": points[-1], "points": points, "model": "trend-baseline-1.0"}

    @staticmethod
    def _dispatch_state(situation) -> dict:
        fleet = situation.fleet or {}
        available = next((item for item in fleet.get("vehicles", []) if item.get("status") == "available"), None)
        return {"active": False, "ambulance_id": available.get("id") if available else None, "route_stability": "STANDBY", "confidence": situation.diagnosis_confidence, "reason": "Dispatch state reflects the persisted fleet snapshot and requires dispatcher action."}

    @staticmethod
    def _congestion_explanations(situation, traffic: dict) -> list[dict]:
        incident = situation.incidents[0] if situation.incidents else None
        return [{"title": "Incident-driven congestion" if incident else "Corridor traffic", "reason": f"{incident.get('title')} is near the active ambulance corridor." if incident else "Traffic state is derived from the configured provider or persisted telemetry.", "forecast": f"Congestion trend is {traffic.get('congestion_level', 'unknown')}.", "evidence_ids": [item.evidence_id for item in situation.evidence]}]

    @staticmethod
    def _status_payload(status: ProviderStatus) -> dict:
        return {"name": status.name, "mode": status.mode, "available": status.available, "stale": status.stale, "message": status.message, "observed_at": status.observed_at.isoformat()}
