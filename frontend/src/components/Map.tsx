import{MapContainer,TileLayer,Marker,Popup,Polyline,Circle}from'react-leaflet';import L from'leaflet';import React,{useEffect,useMemo}from'react';
const ambulance=L.divIcon({className:'ambulance-marker',html:'🚑',iconSize:[30,30],iconAnchor:[15,15]});
const incident=L.divIcon({className:'incident-marker',html:'⚠️',iconSize:[30,30],iconAnchor:[15,15]});
export default function Map({vehicle,incidents,routes}:{vehicle:any,incidents:any[],routes:any[]}){
 const center:[number,number]=[12.9718,77.6005];
 return <MapContainer center={center} zoom={14} scrollWheelZoom className="map"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
  {vehicle&&<Marker position={[vehicle.lat,vehicle.lon]} icon={ambulance}><Popup><b>{vehicle.name}</b><br/>{vehicle.speed_kmh} km/h · {vehicle.status}</Popup></Marker>}
  {incidents.map(i=><span key={i.id}><Marker position={[i.lat,i.lon]} icon={incident}><Popup><b>{i.title}</b><br/>{i.details}</Popup></Marker><Circle center={[i.lat,i.lon]} radius={i.radius_m} pathOptions={{color:'#ef4444',fillOpacity:.08}}/></span>)}
  {routes.map((r,i)=><Polyline key={r.id} positions={r.points.map((p:any)=>[p.lat,p.lon])} pathOptions={{color:i===1?'#10b981':i===0?'#ef4444':'#3b82f6',weight:i===1?6:4,dashArray:i===0?'10 8':undefined,opacity:i===1?1:.75}}/>)}
 </MapContainer>
}
