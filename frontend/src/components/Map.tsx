import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle, Polygon, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const ambulanceIcon = L.divIcon({ className:'map-marker', html:'<span class="ambulance-marker">🚑</span>', iconSize:[38,38], iconAnchor:[19,19] });
const incidentIcon = L.divIcon({ className:'map-marker', html:'<span class="incident-marker">!</span>', iconSize:[30,30], iconAnchor:[15,15] });
const fleetIcon = L.divIcon({ className:'map-marker', html:'<span class="fleet-marker">•</span>', iconSize:[22,22], iconAnchor:[11,11] });
const hospitalIcon = L.divIcon({ className:'map-marker', html:'<span class="hospital-marker">✚</span>', iconSize:[26,26], iconAnchor:[13,13] });
const signalIcon = (state:string, overridden:boolean) => L.divIcon({ className:'map-marker', html:`<span class="signal-marker ${state.toLowerCase()} ${overridden?'override':''}"><i></i><i></i><i></i></span>`, iconSize:[24,24], iconAnchor:[12,12] });
const cartoKey = import.meta.env.VITE_CARTO_BASEMAP_API_KEY || import.meta.env.CARTO_BASEMAP_API_KEY || '';
const cartoTiles = `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png${cartoKey ? `?key=${cartoKey}` : ''}`;

function FitBounds({points}:{points:[number,number][]}) { const map=useMap(); React.useEffect(()=>{ if(points.length>1) map.fitBounds(L.latLngBounds(points),{padding:[28,28],maxZoom:14}); },[map,points]); return null; }

export default function MapView({vehicle,vehicles=[],incidents=[],routes=[],selectedRoute,onSelectRoute,hospitals=[],signals=[],corridor}:any){
  const [animatedPosition,setAnimatedPosition]=React.useState<[number,number]|null>(vehicle?[vehicle.lat,vehicle.lon]:null);
  React.useEffect(()=>{
    const pts=(routes.find((r:any)=>r.id===selectedRoute)||routes[0])?.points||[];
    if(!vehicle || pts.length<2){setAnimatedPosition(vehicle?[vehicle.lat,vehicle.lon]:null);return;}
    let idx=0, t=0;
    const timer=setInterval(()=>{ const a=pts[idx],b=pts[Math.min(idx+1,pts.length-1)]; t+=.12; if(t>=1){idx=Math.min(idx+1,pts.length-2);t=0;} const p=pts[Math.min(idx,pts.length-1)],q=pts[Math.min(idx+1,pts.length-1)]; setAnimatedPosition([p.lat+(q.lat-p.lat)*t,p.lon+(q.lon-p.lon)*t]); },500);
    return()=>clearInterval(timer);
  },[vehicle?.id,selectedRoute,routes]);
  const center:[number,number]=animatedPosition||[19.0178,72.8478];
  const routePoints=routes.flatMap((r:any)=>(r.points||[]).map((p:any)=>[p.lat,p.lon] as [number,number]));
  const corridorPoints=(corridor?.points||[]).map((p:any)=>[p.lat,p.lon] as [number,number]);
  const mumbaiBoundary:[number,number][]=[[19.271,72.775],[19.231,72.786],[19.190,72.797],[19.155,72.815],[19.122,72.826],[19.078,72.818],[19.028,72.811],[18.985,72.800],[18.945,72.814],[18.915,72.829],[18.900,72.850],[18.910,72.875],[18.950,72.890],[19.005,72.900],[19.065,72.905],[19.125,72.900],[19.180,72.884],[19.225,72.860],[19.271,72.825]];
  const all:[number,number][]=[center,...routePoints,...corridorPoints,...incidents.map((i:any)=>[i.lat,i.lon] as [number,number]),...hospitals.map((h:any)=>[h.lat,h.lon] as [number,number])];
  return <MapContainer center={center} zoom={12} scrollWheelZoom className="map">
    <TileLayer attribution="&copy; OpenStreetMap contributors &copy; CARTO" url={cartoTiles} />
    <FitBounds points={all}/>
    <Polygon positions={mumbaiBoundary} pathOptions={{color:'#35d7e8',weight:1.5,fillColor:'#35d7e8',fillOpacity:.035,dashArray:'6 7'}} />
    {vehicle&&<Marker position={center} icon={ambulanceIcon}><Popup><b>{vehicle.name}</b><br/>Live dispatch vehicle · {vehicle.speed_kmh?.toFixed?.(1)??vehicle.speed_kmh} km/h</Popup></Marker>}
    {vehicles.filter((v:any)=>v.id!==vehicle?.id).map((v:any)=><Marker key={v.id} position={[v.lat,v.lon]} icon={fleetIcon}><Popup><b>{v.name||v.id}</b><br/>{v.status} · {v.speed_kmh} km/h</Popup></Marker>)}
    {incidents.map((i:any)=><React.Fragment key={i.id}><Marker position={[i.lat,i.lon]} icon={incidentIcon}><Popup><b>{i.title}</b><br/>{i.details}</Popup></Marker><Circle center={[i.lat,i.lon]} radius={i.radius_m} pathOptions={{color:'#ff5e61',fillOpacity:.1}}/></React.Fragment>)}
    {hospitals.map((h:any)=><Marker key={h.id} position={[h.lat,h.lon]} icon={hospitalIcon}><Popup><b>{h.name}</b><br/>ICU {Math.round(h.icu*100)}% · ER {Math.round(h.er*100)}%<br/><b>{h.trauma}</b></Popup></Marker>)}
    {signals.map((s:any)=><Marker key={s.id} position={[s.lat,s.lon]} icon={signalIcon(s.state,s.overridden)}><Popup><b>{s.name}</b><br/>{s.state}{s.overridden?' · CORRIDOR OVERRIDE':''}</Popup></Marker>)}
    {corridorPoints.length>1&&<><Polyline positions={corridorPoints} pathOptions={{color:'#24ff75',weight:14,opacity:.18,className:'green-corridor-glow'}}/><Polyline positions={corridorPoints} pathOptions={{color:'#35ff7a',weight:5,opacity:.95}}/></>}
    {vehicle&&incidents[0]&&<Polyline positions={[center,[incidents[0].lat,incidents[0].lon]]} pathOptions={{color:'#ff4657',weight:3,opacity:.7,dashArray:'4 8'}}/>}
    {routes.map((r:any,index:number)=>{const pos=(r.points||[]).map((p:any)=>[p.lat,p.lon] as [number,number]); if(!pos.length)return null; const active=selectedRoute===r.id; return <Polyline key={r.id} positions={pos} eventHandlers={{click:()=>onSelectRoute?.(r.id)}} pathOptions={{color:active?'#35d7e8':index===0?'#ff5964':'#7e8b97',weight:active?6:4,opacity:active?1:.72,dashArray:'9 8'}}/>})}
  </MapContainer>
}
