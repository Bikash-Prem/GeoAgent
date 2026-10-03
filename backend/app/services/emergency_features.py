from __future__ import annotations
from datetime import datetime, timezone
from math import hypot
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import AuditEvent, Incident, Vehicle

# Local deterministic operational fixtures. They are synthetic and are surfaced as such.
HOSPITALS = [
    {"id":"HOSP-01","name":"KEM Hospital","lat":18.9998,"lon":72.8428,"icu":0.38,"er":0.31,"oxygen":0.22,"trauma":"READY"},
    {"id":"HOSP-02","name":"Bombay Hospital","lat":18.9435,"lon":72.8234,"icu":0.44,"er":0.36,"oxygen":0.29,"trauma":"READY"},
    {"id":"HOSP-03","name":"Lilavati Hospital","lat":19.0509,"lon":72.8296,"icu":0.52,"er":0.47,"oxygen":0.34,"trauma":"LIMITED"},
    {"id":"HOSP-04","name":"Kokilaben Hospital","lat":19.1364,"lon":72.8262,"icu":0.33,"er":0.28,"oxygen":0.19,"trauma":"READY"},
]

SIGNALS = [
    {"id":"SIG-01","name":"Sion Circle","lat":19.0432,"lon":72.8618},
    {"id":"SIG-02","name":"Dadar TT Junction","lat":19.0195,"lon":72.8420},
    {"id":"SIG-03","name":"Bandra Junction","lat":19.0544,"lon":72.8400},
    {"id":"SIG-04","name":"Mahim Junction","lat":19.0422,"lon":72.8395},
    {"id":"SIG-05","name":"Worli Naka","lat":19.0178,"lon":72.8173},
    {"id":"SIG-06","name":"Haji Ali","lat":18.9824,"lon":72.8088},
    {"id":"SIG-07","name":"Parel Junction","lat":18.9988,"lon":72.8405},
    {"id":"SIG-08","name":"Elphinstone Bridge","lat":19.0014,"lon":72.8337},
]

_corridors: dict[str, dict] = {}


def _distance(a, b):
    return hypot((a[0]-b[0])*111_000, (a[1]-b[1])*105_000)


def hospital_state() -> list[dict]:
    # Small deterministic time-based fluctuation for the local demo; explicitly synthetic.
    minute = datetime.now(timezone.utc).minute
    result=[]
    for i,h in enumerate(HOSPITALS):
        delta=((minute + i*7)%9 - 4)/100
        x=dict(h)
        x["icu"]=round(min(.98,max(.05,h["icu"]+delta)),2)
        x["er"]=round(min(.98,max(.05,h["er"]+delta/2)),2)
        x["oxygen"]=round(min(.98,max(.05,h["oxygen"]+delta/3)),2)
        x["trauma"]="CRITICAL" if x["icu"]>=.80 else "LIMITED" if x["icu"]>=.50 else "READY"
        x["synthetic"]=True
        return result+[x] if False else None
    return result


def get_hospitals() -> list[dict]:
    minute = datetime.now(timezone.utc).minute
    result=[]
    for i,h in enumerate(HOSPITALS):
        delta=((minute + i*7)%9 - 4)/100
        x=dict(h)
        x["icu"]=round(min(.98,max(.05,h["icu"]+delta)),2)
        x["er"]=round(min(.98,max(.05,h["er"]+delta/2)),2)
        x["oxygen"]=round(min(.98,max(.05,h["oxygen"]+delta/3)),2)
        x["trauma"]="CRITICAL" if x["icu"]>=.80 else "LIMITED" if x["icu"]>=.50 else "READY"
        x["synthetic"]=True
        result.append(x)
    return result


def get_signals(corridor_id: str | None = None) -> list[dict]:
    corridor=_corridors.get(corridor_id or "")
    points=corridor.get("points",[]) if corridor else []
    result=[]
    for i,s in enumerate(SIGNALS):
        state="GREEN" if points and min(_distance((s["lat"],s["lon"]),(p["lat"],p["lon"])) for p in points) < 650 else ["RED","AMBER","GREEN"][i%3]
        result.append({**s,"state":state,"overridden":bool(points and state=="GREEN"),"synthetic":True})
    return result


def activate_corridor(db: Session, vehicle: Vehicle, points: list[dict], eta_min: float | None, incident_id: str | None = None) -> dict:
    cid=f"COR-{vehicle.id}"
    data={"id":cid,"vehicle_id":vehicle.id,"incident_id":incident_id,"active":True,"activated_at":datetime.now(timezone.utc).isoformat(),"eta_min":eta_min,"points":points,"provider":"local_signal_controller_simulation","synthetic":True}
    _corridors[cid]=data
    db.add(AuditEvent(vehicle_id=vehicle.id,event_type="green_corridor_activated",payload=data)); db.commit()
    return data


def deactivate_corridor(db: Session, corridor_id: str) -> dict:
    data=_corridors.get(corridor_id)
    if not data: raise ValueError("corridor not found")
    data={**data,"active":False,"deactivated_at":datetime.now(timezone.utc).isoformat()}
    _corridors[corridor_id]=data
    db.add(AuditEvent(vehicle_id=data.get("vehicle_id"),event_type="green_corridor_deactivated",payload=data)); db.commit()
    return data


def current_corridor(vehicle_id: str | None=None):
    active=[x for x in _corridors.values() if x.get("active") and (vehicle_id is None or x.get("vehicle_id")==vehicle_id)]
    return active[-1] if active else None


def dispatch_plan(db: Session, incident: Incident | None = None) -> dict:
    vehicles=db.scalars(select(Vehicle).where(Vehicle.status.in_(["available","active"]))).all()
    if not vehicles: raise ValueError("no ambulance available")
    if incident is None: incident=db.scalars(select(Incident).where(Incident.active==True).order_by(Incident.created_at.desc())).first()
    if incident is None: raise ValueError("no active incident")
    ranked=sorted(vehicles,key=lambda v:_distance((v.lat,v.lon),(incident.lat,incident.lon)))
    ambulance=ranked[0]
    hospitals=sorted(get_hospitals(),key=lambda h:(h["icu"],_distance((incident.lat,incident.lon),(h["lat"],h["lon"]))))
    hospital=hospitals[0]
    response_minutes=max(2.0,_distance((ambulance.lat,ambulance.lon),(incident.lat,incident.lon))/max(ambulance.speed_kmh or 35,35)*60/1000)
    survival=max(0.05,min(0.99,0.96-response_minutes*0.018-(0.12 if incident.severity=="high" else 0.05)))
    confidence=max(.55,min(.97,.78 + (.08 if ambulance.status=="available" else 0) - response_minutes*.005))
    return {"ambulance": {"id":ambulance.id,"name":ambulance.name,"distance_m":round(_distance((ambulance.lat,ambulance.lon),(incident.lat,incident.lon)),0)},"hospital":hospital,"incident":{"id":incident.id,"kind":incident.kind,"severity":incident.severity},"response_eta_min":round(response_minutes,2),"survival_probability":round(survival,3),"dispatch_confidence":round(confidence,3),"model":"deterministic dispatch decision model (local simulation)","synthetic":True}


def execute_dispatch(db: Session, plan: dict) -> dict:
    vehicle_id=plan["ambulance"]["id"]
    vehicle=db.get(Vehicle,vehicle_id)
    if not vehicle: raise ValueError("vehicle not found")
    vehicle.status="active"
    vehicle.hospital=plan["hospital"]["name"]
    db.add(AuditEvent(vehicle_id=vehicle_id,event_type="ai_dispatch_executed",payload=plan))
    db.add(AuditEvent(vehicle_id=vehicle_id,event_type="hospital_alert_dispatched",payload={"hospital":plan["hospital"]["name"],"eta_min":plan["response_eta_min"],"priority":plan["incident"]["severity"],"patient_condition":plan["incident"]["kind"],"alert_number":1}))
    db.commit()
    return plan


def send_hospital_alert(db: Session, vehicle_id: str, hospital: dict, eta: float, incident: dict, alert_number: int) -> dict:
    payload={"hospital":hospital["name"],"eta_min":eta,"patient_condition":incident.get("kind","unknown"),"priority":incident.get("severity","medium"),"alert_number":alert_number,"sent_at":datetime.now(timezone.utc).isoformat()}
    db.add(AuditEvent(vehicle_id=vehicle_id,event_type="hospital_alert_dispatched",payload=payload)); db.commit(); return payload
