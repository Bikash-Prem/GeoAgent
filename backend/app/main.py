import asyncio, time, uuid
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import select
from app.core.config import settings
from app.db.session import Base, engine, SessionLocal
from app.models.entities import Vehicle, Incident, Telemetry
from app.models import intelligence as intelligence_models
from app.models.intelligence import Mission
from app.models import operations as operations_models  # registers hospital / alert / dispatch tables
from app.services.operations import seed_hospitals
from app.algorithms.astar import build_demo_graph
from app.algorithms.geometry import metres
from app.services.risk import to_free_flow_graph
from app.services.situation import SituationEngine
from app.services.trajectory import TrajectoryEngine
from app.api.routes import router
from app.api.operations_routes import router as operations_router
from app.services.control_loop import ControlLoop
from app.services.providers.adapters import TraccarFleetProvider
from app.services.providers.registry import fleet_provider

def seed_database():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(Vehicle).limit(1)) is None:
            db.add_all([
              Vehicle(id='AMB-07',name='AMB-07',status='available',lat=12.9712,lon=77.5940,speed_kmh=0,heading=72,hospital=None),
              Vehicle(id='AMB-12',name='AMB-12',status='available',lat=12.9655,lon=77.5905,speed_kmh=0,heading=0,hospital=None),
              Vehicle(id='AMB-03',name='AMB-03',status='available',lat=12.9780,lon=77.6100,speed_kmh=0,heading=0,hospital=None)])
        if db.scalar(select(Incident).limit(1)) is None:
            db.add_all([
              Incident(id='INC-204',kind='accident',severity='high',title='Accident on Main St.',lat=12.9731,lon=77.5997,radius_m=220,details='Multi-vehicle collision; lane closure reported.'),
              Incident(id='INC-205',kind='closure',severity='medium',title='Road closure · 06:00–10:00',lat=12.9718,lon=77.6012,radius_m=150,details='Temporary lane closure.'),
              Incident(id='INC-206',kind='traffic',severity='medium',title='Heavy traffic corridor',lat=12.9705,lon=77.5988,radius_m=350,details='Average speed down 68% from baseline.')])
        db.commit()
        seed_hospitals(db)

@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_database()
    app.state.control_loop = ControlLoop(SessionLocal)
    if settings.twin_tick_hz > 0:
        await app.state.control_loop.start()
    yield
    await app.state.control_loop.stop()

app=FastAPI(title='GeoAgentic Emergency Response Copilot',version='3.0.0',docs_url='/docs' if settings.docs_enabled else None,redoc_url=None,lifespan=lifespan)
allowed_hosts=[x.strip() for x in settings.allowed_hosts.split(',') if x.strip()]
if allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(',')],allow_credentials=False,allow_methods=['GET','POST','OPTIONS'],allow_headers=['Content-Type','X-API-Key','X-Request-ID'])
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.middleware('http')
async def security_headers(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'geolocation=(self), microphone=(self), camera=()'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Response-Time-Ms'] = str(round((time.perf_counter() - started) * 1000, 2))
    return response

app.include_router(router)
app.include_router(operations_router)

@app.get('/')
def root():
    return {'service': 'geoagentic-api', 'status': 'ok', 'docs': '/docs', 'health': '/api/health', 'ui': 'http://localhost:5173'}

class ConnectionManager:
    def __init__(self):self.connections=[]
    async def connect(self,ws):await ws.accept();self.connections.append(ws)
    def disconnect(self,ws):
        if ws in self.connections:self.connections.remove(ws)
    async def broadcast(self,msg):
        for ws in list(self.connections):
            try: await ws.send_json(msg)
            except: self.disconnect(ws)
manager=ConnectionManager()

# Telemetry socket is now a read-only stream of the current operational state.
# The local control loop advances an active dispatch mission; Traccar can replace that
# movement with real GPS without changing the frontend contract.
@app.websocket('/ws/telemetry')
async def telemetry(ws:WebSocket):
    await manager.connect(ws)
    try:
        while True:
            with SessionLocal() as db:
                rows = db.scalars(select(Vehicle).order_by(Vehicle.id)).all()
                for v in rows:
                    await ws.send_json({
                        'type':'telemetry','vehicle_id':v.id,'lat':v.lat,'lon':v.lon,'speed_kmh':v.speed_kmh,
                        'heading':v.heading,'timestamp':v.updated_at.isoformat(),'source':'traccar' if isinstance(fleet_provider(), TraccarFleetProvider) else 'local-mission'
                    })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


@app.websocket('/ws/twin')
async def twin_stream(ws: WebSocket):
    """Control-loop snapshots: fresh read-only recommendation, decision drift, provider status."""
    await ws.accept()
    loop: ControlLoop = app.state.control_loop
    queue = loop.subscribe()
    try:
        if loop.latest:
            await ws.send_json({'type': 'TWIN_SNAPSHOT_UPDATED', 'snapshot': loop.latest})
        while True:
            await ws.send_json({'type': 'TWIN_SNAPSHOT_UPDATED', 'snapshot': await queue.get()})
    except WebSocketDisconnect:
        pass
    finally:
        loop.unsubscribe(queue)
