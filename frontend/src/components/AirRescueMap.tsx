import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle, Polygon, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const aircraftIcon = L.divIcon({ className: 'map-marker', html: '<span class="aircraft-marker">✈</span>', iconSize: [34, 34], iconAnchor: [17, 17] });
const mountainIcon = L.divIcon({ className: 'map-marker', html: '<span class="mountain-marker">▲</span>', iconSize: [30, 30], iconAnchor: [15, 15] });
const landingIcon = L.divIcon({ className: 'map-marker', html: '<span class="landing-marker">H</span>', iconSize: [28, 28], iconAnchor: [14, 14] });
const hospitalIcon = L.divIcon({ className: 'map-marker', html: '<span class="hospital-marker">✚</span>', iconSize: [26, 26], iconAnchor: [13, 13] });
const cartoKey = import.meta.env.VITE_CARTO_BASEMAP_API_KEY || import.meta.env.CARTO_BASEMAP_API_KEY || '';
const cartoTiles = `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png${cartoKey ? `?key=${cartoKey}` : ''}`;

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  React.useEffect(() => {
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 11 });
  }, [map, points]);
  return null;
}

export default function AirRescueMap({ plan }: { plan: any }) {
  if (!plan) return <div className="air-map-placeholder">Select a mountain region to load the rescue picture.</div>;
  const incident: [number, number] = [plan.incident.lat, plan.incident.lon];
  const lz: [number, number] = [plan.selected_landing_zone.lat, plan.selected_landing_zone.lon];
  const alt: [number, number] = [plan.alternate_landing_zone.lat, plan.alternate_landing_zone.lon];
  const hospital: [number, number] = [plan.hospital.lat, plan.hospital.lon];
  const points = [incident, lz, alt, hospital];
  const regionPolygon: [number, number][] = [
    [plan.region === 'ladakh' ? 35.0 : 31.0, plan.region === 'ladakh' ? 76.3 : 76.0],
    [plan.region === 'ladakh' ? 35.0 : 31.0, plan.region === 'ladakh' ? 79.4 : 80.4],
    [plan.region === 'ladakh' ? 32.9 : 29.2, plan.region === 'ladakh' ? 79.4 : 80.4],
    [plan.region === 'ladakh' ? 32.9 : 29.2, plan.region === 'ladakh' ? 76.3 : 76.0],
  ];
  return <MapContainer center={incident} zoom={9} scrollWheelZoom className="air-map">
    <TileLayer attribution="&copy; OpenStreetMap contributors &copy; CARTO" url={cartoTiles} />
    <FitBounds points={points} />
    <Polygon positions={regionPolygon} pathOptions={{ color: '#a987ff', weight: 1.2, fillOpacity: 0.04, dashArray: '7 8' }} />
    <Circle center={incident} radius={2500} pathOptions={{ color: '#ff5964', fillColor: '#ff5964', fillOpacity: .09, dashArray: '6 8' }} />
    <Marker position={incident} icon={mountainIcon}><Popup><b>{plan.incident.name}</b><br />Altitude {plan.incident.altitude_m.toLocaleString()} m<br />Terrain risk: {plan.terrain_risk}</Popup></Marker>
    <Marker position={lz} icon={landingIcon}><Popup><b>{plan.selected_landing_zone.name}</b><br />{plan.selected_landing_zone.status}<br />Altitude {plan.selected_landing_zone.altitude_m.toLocaleString()} m</Popup></Marker>
    <Marker position={alt} icon={landingIcon}><Popup><b>Alternate · {plan.alternate_landing_zone.name}</b><br />{plan.alternate_landing_zone.status}</Popup></Marker>
    <Marker position={hospital} icon={hospitalIcon}><Popup><b>{plan.hospital.name}</b><br />Helipad {plan.hospital.helipad}<br />Trauma {plan.hospital.trauma}</Popup></Marker>
    <Marker position={lz} icon={aircraftIcon}><Popup><b>{plan.air_ambulance.name}</b><br />Flight ETA {plan.flight_eta_min} min<br />Fuel {plan.air_ambulance.fuel_pct}%</Popup></Marker>
    <Polyline positions={[lz, incident]} pathOptions={{ color: '#a987ff', weight: 4, opacity: .95, dashArray: '10 8', className: 'air-flight-line' }} />
    <Polyline positions={[incident, hospital]} pathOptions={{ color: '#35d7e8', weight: 3, opacity: .55, dashArray: '4 9' }} />
  </MapContainer>;
}
