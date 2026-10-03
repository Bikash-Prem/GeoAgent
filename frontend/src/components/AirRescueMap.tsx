import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle, useMap } from 'react-leaflet';
import L from 'leaflet';

const icon = (cls: string, text: string, size = 30) => L.divIcon({ className: 'mk', html: `<span class="mk-air ${cls}">${text}</span>`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });

function Fit({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = points.map((p) => p.join(',')).join('|');
  useEffect(() => { if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 11 }); }, [key]); // eslint-disable-line
  return null;
}

export default function AirRescueMap({ plan }: { plan: any }) {
  if (!plan) return <div className="air-map empty">Choose a region to load the rescue picture.</div>;
  const inc: [number, number] = [plan.incident.lat, plan.incident.lon];
  const lz: [number, number] = [plan.selected_landing_zone.lat, plan.selected_landing_zone.lon];
  const alt: [number, number] = [plan.alternate_landing_zone.lat, plan.alternate_landing_zone.lon];
  const hosp: [number, number] = [plan.hospital.lat, plan.hospital.lon];
  const base: [number, number] = [plan.air_ambulance.base_lat, plan.air_ambulance.base_lon];
  return (
    <MapContainer center={inc} zoom={9} scrollWheelZoom={false} className="air-map">
      <TileLayer attribution="&copy; OpenStreetMap contributors, SRTM · &copy; OpenTopoMap (CC-BY-SA)" url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png" maxZoom={15} />
      <Fit points={[inc, lz, alt, hosp, base]} />
      <Circle center={inc} radius={1800} pathOptions={{ color: '#b65e5a', weight: 1.5, fillColor: '#e6b5d6', fillOpacity: 0.3, dashArray: '6 6' }} />
      <Polyline positions={[base, lz]} pathOptions={{ color: '#1c0f0e', weight: 3, dashArray: '10 8' }} />
      <Polyline positions={[lz, hosp]} pathOptions={{ color: '#6a9a63', weight: 4, opacity: 0.9 }} />
      <Marker position={base} icon={icon('base', '✈', 34)}><Popup><b>{plan.air_ambulance.name}</b><br />Base: {plan.air_ambulance.base}<br />Fuel {plan.air_ambulance.fuel_pct}%</Popup></Marker>
      <Marker position={inc} icon={icon('inc', '▲', 32)}><Popup><b>{plan.incident.name}</b><br />{plan.incident.altitude_m.toLocaleString()} m · terrain {plan.terrain_risk}</Popup></Marker>
      <Marker position={lz} icon={icon('lz', 'H')}><Popup><b>{plan.selected_landing_zone.name}</b><br />{plan.selected_landing_zone.status} · {plan.selected_landing_zone.altitude_m.toLocaleString()} m</Popup></Marker>
      <Marker position={alt} icon={icon('lz alt', 'H')}><Popup><b>Alternate: {plan.alternate_landing_zone.name}</b><br />{plan.alternate_landing_zone.status}</Popup></Marker>
      <Marker position={hosp} icon={icon('hosp', '✚')}><Popup><b>{plan.hospital.name}</b><br />Helipad {plan.hospital.helipad} · trauma {plan.hospital.trauma}</Popup></Marker>
    </MapContainer>
  );
}
