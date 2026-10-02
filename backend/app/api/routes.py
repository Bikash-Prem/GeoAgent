from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.entities import Vehicle, Incident, AuditEvent
from app.models.intelligence import DecisionOutcome, DecisionRecord, DecisionTraceRecord
from app.schemas.dto import VehicleOut, IncidentOut, RecommendationOut, ActionIn, HealthOut
from app.schemas.intelligence import DecisionAnalysisRequest, DecisionApproval, OutcomeInput, SimulationRequest, TelemetryInput
from app.core.config import settings
from app.db.session import check_database
from app.services.engine import GeoAgentEngine
from app.services.agent import GeoAgent
from app.services.simulation import SimulationEngine
from app.services.situation import SituationEngine
from app.services.trajectory import TrajectoryEngine
from app.services.evaluation import EvaluationPlan

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
@router.get('/v1/vehicles',response_model=list[VehicleOut])
def vehicles(db:Session=Depends(get_db)): return db.scalars(select(Vehicle).order_by(Vehicle.id)).all()

@router.get('/incidents',response_model=list[IncidentOut])
@router.get('/v1/incidents',response_model=list[IncidentOut])
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


@router.get('/v1/situations/{vehicle_id}')
def situation(vehicle_id: str, db: Session = Depends(get_db)):
    try:
        return SituationEngine(db).build(vehicle_id).as_dict()
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.post('/v1/vehicles/{vehicle_id}/telemetry')
def ingest_telemetry(vehicle_id: str, payload: TelemetryInput, db: Session = Depends(get_db)):
    try:
        record = TrajectoryEngine().ingest(db, vehicle_id, payload.latitude, payload.longitude, payload.speed_kmh, payload.heading, payload.planned_route)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    return {"id": record.id, "vehicle_id": record.vehicle_id, "deviation_distance_m": record.deviation_distance_m, "route_progress": record.route_progress, "is_deviating": record.is_deviating, "timestamp": record.timestamp}


@router.post('/v1/decisions/analyze')
def analyze_decision(request: DecisionAnalysisRequest, db: Session = Depends(get_db)):
    try:
        return GeoAgentEngine(db).analyze(request.vehicle_id).as_dict()
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.post('/v1/routes/generate')
def generate_routes(request: DecisionAnalysisRequest, db: Session = Depends(get_db)):
    try:
        return {"vehicle_id": request.vehicle_id, "routes": GeoAgentEngine(db).recommendation(request.vehicle_id)["routes"]}
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.post('/v1/actions/generate')
def generate_actions(request: DecisionAnalysisRequest, db: Session = Depends(get_db)):
    try:
        result = GeoAgentEngine(db).analyze(request.vehicle_id)
        return {"decision_id": result.decision_id, "actions": [item.as_dict() for item in result.actions]}
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.post('/v1/actions/evaluate')
def evaluate_actions(request: DecisionAnalysisRequest, db: Session = Depends(get_db)):
    return generate_actions(request, db)


@router.get('/v1/decisions/{decision_id}/trace')
def decision_trace(decision_id: str, db: Session = Depends(get_db)):
    decision = db.get(DecisionRecord, decision_id)
    if decision is None:
        raise HTTPException(404, 'decision not found')
    events = db.scalars(select(DecisionTraceRecord).where(DecisionTraceRecord.decision_id == decision_id).order_by(DecisionTraceRecord.created_at)).all()
    return {'decision_id': decision_id, 'status': decision.status, 'events': [{'event_type': item.event_type, 'payload': item.payload, 'created_at': item.created_at} for item in events]}


@router.get('/v1/decisions/{decision_id}')
def get_decision(decision_id: str, db: Session = Depends(get_db)):
    decision = db.get(DecisionRecord, decision_id)
    if decision is None:
        raise HTTPException(404, 'decision not found')
    return {'decision_id': decision.id, 'situation_id': decision.situation_id, 'vehicle_id': decision.vehicle_id, 'status': decision.status, 'recommended_action': decision.recommended_action, 'reasoning': decision.reasoning, 'policy': {'name': decision.policy_name, 'version': decision.policy_version}, 'created_at': decision.created_at}


@router.post('/v1/decisions/{decision_id}/approve')
def approve_decision(decision_id: str, payload: DecisionApproval, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    decision = db.get(DecisionRecord, decision_id)
    if decision is None:
        raise HTTPException(404, 'decision not found')
    decision.status = 'approved' if payload.approved else 'rejected'
    db.add(DecisionTraceRecord(decision_id=decision_id, event_type='human_approval', payload=payload.model_dump()))
    db.commit()
    return {'decision_id': decision_id, 'status': decision.status, 'selected_action_id': payload.selected_action_id or decision.recommended_action.get('action_id'), 'actor_id': payload.actor_id, 'comment': payload.comment}


@router.post('/v1/decisions/{decision_id}/reject')
def reject_decision(decision_id: str, payload: DecisionApproval, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    payload.approved = False
    return approve_decision(decision_id, payload, db, _)


@router.post('/v1/decisions/{decision_id}/outcome')
def record_outcome(decision_id: str, payload: OutcomeInput, db: Session = Depends(get_db), _: None = Depends(require_api_key)):
    if db.get(DecisionRecord, decision_id) is None:
        raise HTTPException(404, 'decision not found')
    outcome = DecisionOutcome(decision_id=decision_id, approved=True, actual_eta_minutes=payload.actual_eta_minutes, actual_risk=payload.actual_risk, result=payload.result, notes=payload.notes)
    db.add(outcome)
    decision = db.get(DecisionRecord, decision_id)
    db.add(DecisionTraceRecord(decision_id=decision_id, event_type='outcome_recorded', payload={**payload.model_dump(), 'predicted': decision.recommended_action, 'recorded_at': outcome.created_at.isoformat() if outcome.created_at else None}))
    db.commit()
    return {'outcome_id': outcome.id, 'decision_id': decision_id, 'status': 'recorded'}


@router.get('/v1/decisions/{decision_id}/feedback')
def decision_feedback(decision_id: str, db: Session = Depends(get_db)):
    decision = db.get(DecisionRecord, decision_id)
    outcome = db.scalars(select(DecisionOutcome).where(DecisionOutcome.decision_id == decision_id).order_by(DecisionOutcome.created_at.desc())).first()
    if decision is None or outcome is None:
        raise HTTPException(404, 'decision outcome not found')
    predicted_eta = decision.recommended_action.get('expected_eta_minutes')
    predicted_risk = decision.recommended_action.get('risk', {}).get('score')
    return {'decision_id': decision_id, 'predicted': {'eta_minutes': predicted_eta, 'risk': predicted_risk}, 'actual': {'eta_minutes': outcome.actual_eta_minutes, 'risk': outcome.actual_risk, 'result': outcome.result}, 'error': {'eta_minutes': abs(predicted_eta - outcome.actual_eta_minutes) if predicted_eta is not None and outcome.actual_eta_minutes is not None else None, 'risk': abs(predicted_risk - outcome.actual_risk) if predicted_risk is not None and outcome.actual_risk is not None else None}}


@router.get('/v1/agent/tools')
def agent_tools(vehicle_id: str = 'AMB-07', db: Session = Depends(get_db)):
    try:
        context = SituationEngine(db).build(vehicle_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    return GeoAgent(context, db=db).analyze()


@router.get('/v1/simulation/scenarios')
def simulation_scenarios():
    return SimulationEngine().list_scenarios()


@router.post('/v1/simulation/run')
def simulation_run(payload: SimulationRequest, db: Session = Depends(get_db)):
    try:
        return SimulationEngine().run(payload.scenario, payload.seed, db)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get('/v1/evaluation/strategies')
def evaluation_strategies():
    return EvaluationPlan().list()
