"""Response-operations API: incident intake, AI dispatch, green corridor, hospital network, coverage,
what-if lab, mountain air rescue and shift reporting. Every write is audited; nothing acts without a human call."""
from uuid import uuid4

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import AuditEvent, Incident, Vehicle
from app.schemas.operations import AckIn, AirRescueIn, AlertCreate, CorridorIn, DispatchIn, HospitalUpdate, IncidentCreate, WhatIfIn
from app.services import operations as ops
from app.services.air_rescue import REGIONS, build_air_rescue_plan
from app.services.engine import GeoAgentEngine
from app.services.reports import decisions_csv, list_decisions, shift_report
from app.services.whatif import PRESETS, run_whatif
from app.services.mission import active_assignment, mission_state

router = APIRouter(prefix="/api/v1")


def require_api_key(x_api_key: str | None = Header(default=None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="A valid API key is required")


def _404(fn):
    try:
        return fn()
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


# ── incidents ──
@router.post("/incidents", status_code=201)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    inc = Incident(id=f"INC-{uuid4().hex[:5].upper()}", kind=payload.kind, severity=payload.severity, title=payload.title,
                   lat=payload.lat, lon=payload.lon, radius_m=payload.radius_m, details=payload.details, active=True)
    db.add(inc)
    db.add(AuditEvent(vehicle_id=None, event_type="incident_logged", payload=payload.model_dump() | {"incident_id": inc.id}))
    db.commit()
    return {"id": inc.id, "kind": inc.kind, "severity": inc.severity, "title": inc.title, "lat": inc.lat, "lon": inc.lon,
            "radius_m": inc.radius_m, "active": True, "details": inc.details}


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise HTTPException(404, "incident not found")
    inc.active = False
    db.add(AuditEvent(vehicle_id=None, event_type="incident_resolved", payload={"incident_id": incident_id}))
    db.commit()
    return {"incident_id": incident_id, "resolved": True}


# ── hospitals ──
@router.get("/hospitals")
def hospitals(db: Session = Depends(get_db)):
    return {"hospitals": ops.list_hospitals(db)}


@router.post("/hospitals/{hospital_id}/capacity")
def hospital_capacity(hospital_id: str, payload: HospitalUpdate, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    return _404(lambda: ops.update_hospital(db, hospital_id, payload.model_dump()))


@router.get("/hospitals/alerts")
def hospital_alerts(hospital_id: str | None = None, db: Session = Depends(get_db)):
    return {"alerts": ops.list_alerts(db, hospital_id)}


@router.post("/hospitals/alerts", status_code=201)
def hospital_alert(payload: AlertCreate, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    return _404(lambda: ops.send_alert(db, payload.model_dump()))


@router.post("/hospitals/alerts/{alert_id}/ack")
def hospital_alert_ack(alert_id: int, payload: AckIn, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    return _404(lambda: ops.acknowledge_alert(db, alert_id, payload.actor))


# ── signals / corridor ──
@router.get("/signals")
def signals(vehicle_id: str | None = None):
    return {"controller": "simulated", "signals": ops.list_signals(vehicle_id)}


@router.get("/corridor")
def corridor(vehicle_id: str | None = None):
    return ops.current_corridor(vehicle_id) or {"active": False}


@router.post("/corridor/activate")
def corridor_activate(payload: CorridorIn, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    def go():
        rec = GeoAgentEngine(db).recommendation(payload.vehicle_id)
        data = ops.activate_corridor(db, payload.vehicle_id, rec)
        return {**data, "signals": ops.list_signals(payload.vehicle_id)}
    return _404(go)


@router.post("/corridor/{corridor_id}/deactivate")
def corridor_deactivate(corridor_id: str, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    return _404(lambda: {**ops.deactivate_corridor(db, corridor_id), "signals": ops.list_signals()})


# ── mission lifecycle ──
@router.get("/mission/active")
def active_mission(db: Session = Depends(get_db)):
    return {"active": bool(active_assignment(db)), "mission": mission_state(db, active_assignment(db))}


# ── dispatch ──
@router.get("/dispatch/plan")
def dispatch_plan(incident_id: str | None = None, db: Session = Depends(get_db)):
    return _404(lambda: ops.dispatch_plan(db, incident_id, settings.coverage_target_min))


@router.post("/dispatch/execute")
def dispatch_execute(payload: DispatchIn, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    return _404(lambda: ops.execute_dispatch(db, payload.incident_id, payload.actor))


@router.get("/dispatch/assignments")
def dispatch_assignments(db: Session = Depends(get_db)):
    return {"assignments": ops.list_assignments(db)}


@router.post("/dispatch/assignments/{assignment_id}/complete")
def dispatch_complete(assignment_id: str, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    return _404(lambda: ops.complete_assignment(db, assignment_id))


# ── coverage ──
@router.get("/coverage")
def coverage(target_min: float | None = None, db: Session = Depends(get_db)):
    target = target_min or settings.coverage_target_min
    data = ops.coverage(db, target)
    data["impact"] = ops.coverage_impact(db, target)
    return data


# ── what-if ──
@router.get("/whatif/presets")
def whatif_presets():
    return [{"id": k, "description": v} for k, v in PRESETS.items()]


@router.post("/whatif")
def whatif(payload: WhatIfIn, db: Session = Depends(get_db)):
    try:
        return run_whatif(db, payload.vehicle_id, payload.preset, [i.model_dump() for i in payload.incidents], settings.response_target_min)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


# ── air rescue ──
@router.get("/air-rescue/regions")
def air_regions():
    return [{"id": k, "name": v["name"]} for k, v in REGIONS.items()]


@router.get("/air-rescue/plan")
def air_rescue_plan(region: str = "himachal", wind_kmh: float | None = None, visibility_km: float | None = None, cloud_base_m: float | None = None):
    return build_air_rescue_plan(region, {"wind_kmh": wind_kmh, "visibility_km": visibility_km, "cloud_base_m": cloud_base_m})


@router.post("/air-rescue/execute")
def air_rescue_execute(payload: AirRescueIn, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    plan = build_air_rescue_plan(payload.region, payload.weather.model_dump() if payload.weather else None)
    if plan["checks_failed"]:
        raise HTTPException(409, "Air response blocked: " + "; ".join(plan["checks_failed"]))
    db.add(AuditEvent(vehicle_id=plan["air_ambulance"]["id"], event_type="air_rescue_activated",
                      payload={"region": plan["region"], "landing_zone": plan["selected_landing_zone"]["id"], "eta_min": plan["flight_eta_min"], "actor": payload.actor}))
    db.commit()
    return {**plan, "status": "AIR AMBULANCE TASKED", "execution": "recorded in audit trail (simulation)"}


# ── reporting ──
@router.get("/decisions")
def decisions(limit: int = 25, db: Session = Depends(get_db)):
    return {"decisions": list_decisions(db, max(1, min(limit, 200)))}


@router.get("/reports/shift")
def report_shift(hours: float = 12, db: Session = Depends(get_db)):
    return shift_report(db, max(0.5, min(hours, 168)))


@router.get("/reports/decisions.csv", response_class=PlainTextResponse)
def report_csv(db: Session = Depends(get_db)):
    return PlainTextResponse(decisions_csv(db), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=geoagentic-decisions.csv"})


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    vehicles = db.scalars(select(Vehicle)).all()
    last = db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(1)).first()
    from app.services.providers.registry import describe
    return {"providers": describe(), "routing": next(p["source"] for p in describe() if p["name"] == "routing"), "signal_controller": "simulated",
            "hospital_capacity": "hospital desk updates", "llm": "enabled" if settings.anthropic_api_key else "off (deterministic answers)",
            "fleet": {"total": len(vehicles), "available": sum(v.status == "available" for v in vehicles)},
            "last_event": last.created_at.isoformat() if last else None, "response_target_min": settings.response_target_min,
            "coverage_target_min": settings.coverage_target_min}


# ── control loop (live twin) ──
class LoopCommand(BaseModel):
    action: Literal["start", "stop", "reset", "tick"]


def _loop(request: Request):
    loop = getattr(request.app.state, "control_loop", None)
    if loop is None:
        raise HTTPException(503, "Control loop is not running")
    return loop


@router.get("/twin/snapshot")
async def twin_snapshot(request: Request):
    loop = _loop(request)
    if loop.latest is None:
        await loop.command("tick")
    return loop.latest


@router.get("/twin/history")
def twin_history(request: Request, limit: int = 120):
    loop = _loop(request)
    return {"running": loop.running, "interval_s": round(1 / max(settings.twin_tick_hz, 0.01), 1), "snapshots": list(loop.history)[-max(1, min(limit, 500)):]}


@router.get("/twin/providers")
def twin_providers(request: Request):
    return {"providers": _loop(request).provider_status()}


@router.post("/twin/command")
async def twin_command(payload: LoopCommand, request: Request, _: None = Depends(require_api_key)):
    return await _loop(request).command(payload.action)
