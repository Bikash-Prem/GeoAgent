from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import Vehicle, Incident, AuditEvent
from app.schemas.dto import VehicleOut, IncidentOut, RecommendationOut, ActionIn, HealthOut
from app.core.config import settings
from app.db.session import check_database
from app.services.engine import GeoAgentEngine

router=APIRouter(prefix='/api')

def require_api_key(x_api_key: str | None = Header(default=None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail='A valid API key is required')

@router.get('/health', response_model=HealthOut)
def health():
    try:
        check_database()
        database = 'ok'
    except Exception:
        database = 'degraded'
    return {'status':'ok' if database == 'ok' else 'degraded','service':'geoagentic-api','database':database,'environment':settings.environment}

@router.get('/ready', response_model=HealthOut)
def ready():
    if not check_database():
        raise HTTPException(status_code=503, detail='Database is unavailable')
    return {'status':'ready','service':'geoagentic-api','database':'ok','environment':settings.environment}

@router.get('/vehicles',response_model=list[VehicleOut])
def vehicles(db:Session=Depends(get_db)): return db.scalars(select(Vehicle).order_by(Vehicle.id)).all()

@router.get('/incidents',response_model=list[IncidentOut])
def incidents(db:Session=Depends(get_db)): return db.scalars(select(Incident).where(Incident.active==True).order_by(desc(Incident.created_at))).all()

@router.get('/recommendations/{vehicle_id}',response_model=RecommendationOut)
def recommendation(vehicle_id:str,db:Session=Depends(get_db)):
    try:return GeoAgentEngine(db).recommendation(vehicle_id)
    except ValueError as e:raise HTTPException(404,str(e))

@router.post('/vehicles/{vehicle_id}/actions')
def action(vehicle_id:str,payload:ActionIn,db:Session=Depends(get_db),_:None=Depends(require_api_key)):
    if not db.get(Vehicle,vehicle_id): raise HTTPException(404,'vehicle not found')
    event=AuditEvent(vehicle_id=vehicle_id,event_type=f'action:{payload.action}',payload=payload.model_dump())
    db.add(event); db.commit()
    return {'ok':True,'message':f'{payload.action.replace("_"," ").title()} recorded','event_id':event.id}

@router.get('/audit')
def audit(db:Session=Depends(get_db)):
    return [{'id':x.id,'vehicle_id':x.vehicle_id,'event_type':x.event_type,'payload':x.payload,'created_at':x.created_at} for x in db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(25)).all()]
