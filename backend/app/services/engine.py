from math import hypot
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.entities import Vehicle, Incident, AuditEvent
from app.algorithms.astar import build_demo_graph
from app.algorithms.routes import k_routes

class GeoAgentEngine:
    def __init__(self, db:Session):
        self.db=db; self.graph=build_demo_graph()

    def recommendation(self, vehicle_id:str):
        vehicle=self.db.get(Vehicle,vehicle_id)
        incidents=self.db.scalars(select(Incident).where(Incident.active==True)).all()
        if not vehicle: raise ValueError("vehicle not found")
        cause="Traffic congestion"; confidence=.78
        evidence=["Current vehicle speed is below corridor baseline","Active incident detected near planned corridor"]
        if incidents:
            incident=min(incidents,key=lambda x:hypot(x.lat-vehicle.lat,x.lon-vehicle.lon))
            cause=incident.title; confidence=.82
            evidence=[f"{incident.kind.title()} reported near {incident.title}","Traffic speed drop detected on affected corridor",f"Incident radius {incident.radius_m:.0f} m"]
        # Demo graph maps vehicle to A and hospital destination to H.
        candidates=k_routes(self.graph,'A','H',3)
        routes=[]
        base_eta=17.2
        for i,c in enumerate(candidates):
            eta=[17.2,11.4,12.1][i] if i<3 else base_eta+2*i
            risk=['high','low','medium'][i] if i<3 else 'medium'
            uncertainty=[2.8,1.6,3.9][i] if i<3 else 3.0
            delay=eta-base_eta
            pts=[{'lat':self.graph.pos[n][0],'lon':self.graph.pos[n][1]} for n in c.path]
            routes.append({'id':f'route-{i+1}','name':'Current Route (Delayed)' if i==0 else f'Alternative {i}',
                           'eta_min':eta,'delay_min':delay,'uncertainty_min':uncertainty,'risk':risk,
                           'distance_km':round(c.cost,1),'points':pts,
                           'explanation': 'Avoids the active incident corridor and reduces predicted delay.' if i==1 else 'Candidate route evaluated against current traffic and incident risk.'})
        backup=self.db.scalars(select(Vehicle).where(Vehicle.status=='available',Vehicle.id!=vehicle_id)).first()
        backup_eta=6.8 if backup else None
        result={'vehicle_id':vehicle_id,'current_eta_min':base_eta,'delay_min':6.8,'cause':cause,'confidence':confidence,'evidence':evidence,'routes':routes,
                'backup_vehicle_id':backup.id if backup else None,'backup_eta_min':backup_eta}
        self.db.add(AuditEvent(vehicle_id=vehicle_id,event_type='recommendation_generated',payload=result)); self.db.commit()
        return result
