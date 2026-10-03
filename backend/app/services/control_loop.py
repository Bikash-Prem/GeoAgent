"""Control loop (merged from the GeoAgentic 'digital twin' loop, rebuilt for this engine).

Every tick it:
  1. syncs live GPS from Traccar (when configured) into the fleet + telemetry tables,
  2. imports live road incidents from TomTom (when configured, every INCIDENT_SYNC_SECONDS),
  3. re-evaluates the focus unit's decision READ-ONLY (nothing is written to the decision log),
  4. raises a 'decision drift' flag when the fresh recommendation no longer matches the one in the log,
  5. keeps a ring buffer of snapshots so the last ~10 minutes can be replayed in the UI.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.entities import AuditEvent, Incident, Vehicle
from app.models.intelligence import DecisionRecord
from .engine import GeoAgentEngine
from .providers.adapters import TraccarFleetProvider
from .providers.registry import describe, device_map, fleet_provider, incident_provider
from .providers.sync import run_sync
from .trajectory import TrajectoryEngine
from .mission import advance as advance_mission

log = logging.getLogger("geoagentic.loop")
FOCUS = "AMB-07"
ETA_DRIFT_MIN = 1.5


class ControlLoop:
    def __init__(self, session_factory: sessionmaker, history_size: int = 120):
        self.session_factory = session_factory
        self.running = True
        self.tick_count = 0
        self.latest: dict | None = None
        self.history: deque[dict] = deque(maxlen=history_size)
        self.subscribers: set[asyncio.Queue] = set()
        self.task: asyncio.Task | None = None
        self.last_incident_sync = 0.0
        self.observations: dict[str, dict] = {}
        self._last_drift_key = None

    # ── lifecycle ──
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
                    snapshot = await asyncio.to_thread(self.tick)
                    await self._publish(snapshot)
                except Exception:  # a provider or DB hiccup degrades one tick, never the server
                    log.exception("control loop tick failed")
            await asyncio.sleep(max(1.0, 1 / max(settings.twin_tick_hz, 0.01)))

    # ── one tick (sync; runs in a worker thread) ──
    def tick(self) -> dict:
        with self.session_factory() as db:
            self._sync_fleet(db)
            self._sync_incidents(db)
            # Advance the local mission state machine. Real Traccar deployments can replace this
            # with actual GPS while preserving the same mission lifecycle and event stream.
            advance_mission(db)
            vehicle = db.get(Vehicle, FOCUS)
            if vehicle is None:
                return self.latest or {}
            engine = GeoAgentEngine(db)
            preview = engine.analyze(FOCUS, persist=False)
            routes = engine.routes
            ra = preview.recommendation.as_dict()
            chosen = next((r for r in routes if r["id"] == ra["route_id"]), routes[0] if routes else None)
            logged = db.scalars(select(DecisionRecord).where(DecisionRecord.vehicle_id == FOCUS).order_by(desc(DecisionRecord.created_at))).first()
            drift = None
            if logged is not None and logged.status in ("pending", "approved"):
                prev = logged.recommended_action or {}
                eta_worse = ra["expected_eta_minutes"] - (prev.get("expected_eta_minutes") or 0)  # arriving sooner is not a problem
                if (prev.get("action"), prev.get("route_id")) != (ra["action"], ra["route_id"]) or eta_worse >= ETA_DRIFT_MIN:
                    drift = {"logged_decision_id": logged.id, "logged_status": logged.status, "was": {"action": prev.get("action"), "route_id": prev.get("route_id"), "eta_min": prev.get("expected_eta_minutes")},
                             "now": {"action": ra["action"], "route_id": ra["route_id"], "eta_min": ra["expected_eta_minutes"]}, "eta_change_min": round(ra["expected_eta_minutes"] - (prev.get("expected_eta_minutes") or 0), 2)}
            # debounce: only flag a change that is still there on the next tick (stops flapping at thresholds)
            key = (drift["now"]["action"], drift["now"]["route_id"], drift["logged_decision_id"]) if drift else None
            confirmed = drift if drift and key == self._last_drift_key else None
            self._last_drift_key = key
            drift = confirmed
            vehicles = db.scalars(select(Vehicle).order_by(Vehicle.id)).all()
            incidents = db.scalars(select(Incident).where(Incident.active.is_(True))).all()
            self.tick_count += 1
            snapshot = {
                "snapshot_id": f"snap-{uuid4().hex[:10]}", "tick": self.tick_count, "at": datetime.now(timezone.utc).isoformat(),
                "vehicles": [{"id": v.id, "name": v.name, "status": v.status, "lat": v.lat, "lon": v.lon, "speed_kmh": v.speed_kmh, "hospital": v.hospital} for v in vehicles],
                "incidents": [{"id": i.id, "kind": i.kind, "severity": i.severity, "title": i.title, "lat": i.lat, "lon": i.lon, "radius_m": i.radius_m} for i in incidents],
                "recommendation": {"action": ra["action"], "route_id": ra["route_id"], "route_name": chosen["name"] if chosen else None, "eta_min": ra["expected_eta_minutes"],
                                   "eta_lower": ra["eta_uncertainty"]["lower"], "eta_upper": ra["eta_uncertainty"]["upper"], "risk": ra["risk"]["level"], "reasoning": preview.reason,
                                   "diagnosis": preview.situation.diagnosis},
                "routes": [{"id": r["id"], "name": r["name"], "eta_min": r["eta_min"], "risk": r["risk"], "points": r["points"]} for r in routes],
                "logged_decision": {"id": logged.id, "status": logged.status, "action": (logged.recommended_action or {}).get("action")} if logged else None,
                "drift": drift, "routing_source": getattr(engine, "routing_source", None),
            }
        self.latest = snapshot
        self.history.append(snapshot)
        return snapshot

    def _observe(self, name: str, available: bool, message: str | None = None, count: int | None = None) -> None:
        self.observations[name] = {"available": available, "message": message, "count": count, "observed_at": datetime.now(timezone.utc).isoformat()}

    def _sync_fleet(self, db) -> None:
        provider = fleet_provider()
        if not isinstance(provider, TraccarFleetProvider):
            return
        obs = run_sync(provider.vehicles())
        mapping = device_map()
        updated = 0
        planned = [{"lat": p["lat"], "lon": p["lon"]} for p in (self.latest or {}).get("routes", [{}])[0].get("points", [])] if self.latest and self.latest.get("routes") else None
        for item in obs.vehicles:
            vid = mapping.get(item["device_id"])
            if vid and db.get(Vehicle, vid) is not None:
                TrajectoryEngine().ingest(db, vid, item["lat"], item["lon"], item["speed_kmh"], item["heading"], planned if vid == FOCUS else None)
                updated += 1
        db.commit()
        self._observe("fleet", obs.status.available, obs.status.message, updated)

    def _sync_incidents(self, db) -> None:
        provider = incident_provider()
        if provider is None or time.time() - self.last_incident_sync < settings.incident_sync_seconds:
            return
        self.last_incident_sync = time.time()
        vs = db.scalars(select(Vehicle)).all()
        if not vs:
            return
        pad = 0.03  # ~3 km around the fleet
        bbox = (min(v.lat for v in vs) - pad, min(v.lon for v in vs) - pad, max(v.lat for v in vs) + pad, max(v.lon for v in vs) + pad)
        rows, status = run_sync(provider.incidents(bbox))
        if not status.available:
            self._observe("incidents", False, status.message)
            return
        seen = set()
        for row in rows:
            iid = "TT-" + hashlib.sha1(row["external_id"].encode()).hexdigest()[:8].upper()
            seen.add(iid)
            inc = db.get(Incident, iid)
            if inc is None:
                db.add(Incident(id=iid, kind=row["kind"], severity=row["severity"], title=row["title"], lat=row["lat"], lon=row["lon"], radius_m=row["radius_m"], details=row["details"], active=True))
                db.add(AuditEvent(vehicle_id=None, event_type="incident_imported", payload={"incident_id": iid, "source": "tomtom", "kind": row["kind"]}))
            else:
                inc.active, inc.severity, inc.lat, inc.lon, inc.radius_m = True, row["severity"], row["lat"], row["lon"], row["radius_m"]
        for stale in db.scalars(select(Incident).where(Incident.id.like("TT-%"), Incident.active.is_(True))).all():
            if stale.id not in seen:
                stale.active = False  # TomTom no longer reports it
        db.commit()
        self._observe("incidents", True, None, len(rows))

    # ── control & streaming ──
    async def command(self, action: str) -> dict:
        if action == "start":
            self.running = True
        elif action == "stop":
            self.running = False
        elif action == "reset":
            self.history.clear()
            self.tick_count = 0
        elif action == "tick":
            snapshot = await asyncio.to_thread(self.tick)
            await self._publish(snapshot)
        return {"running": self.running, "tick": self.tick_count, "history": len(self.history)}

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    async def _publish(self, snapshot: dict) -> None:
        for q in list(self.subscribers):
            if q.full():
                q.get_nowait()
            await q.put(snapshot)

    def provider_status(self) -> list[dict]:
        out = []
        for p in describe():
            obs = self.observations.get({"fleet": "fleet", "traffic": "incidents", "routing": "routing"}[p["name"]])
            out.append({**p, "last": obs})
        return out
