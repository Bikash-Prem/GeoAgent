import React from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle } from 'react-leaflet';
import L from 'leaflet';

const unitIcon = L.divIcon({
  className: 'mk',
  html: '<span class="mk-pulse"></span><span class="mk-core">🚑</span>',
  iconSize: [44, 44],
  iconAnchor: [22, 22],
});
const incidentIcon = L.divIcon({
  className: 'mk',
  html: '<span class="mk-x">✕</span>',
  iconSize: [34, 34],
  iconAnchor: [17, 17],
});

const COLORS = { delayed: '#b65e5a', recommended: '#6a9a63', planned: '#67a6c2' };

export default function MapView({ vehicle, incidents, routes }: { vehicle: any; incidents: any[]; routes: any[] }) {
  const center: [number, number] = [12.9718, 77.6005];
  return (
    <MapContainer center={center} zoom={14} scrollWheelZoom={false} className="map">
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {vehicle && (
        <Marker position={[vehicle.lat, vehicle.lon]} icon={unitIcon}>
          <Popup>
            <b>{vehicle.name}</b>
            <br />
            {vehicle.speed_kmh} km/h · {vehicle.status}
          </Popup>
        </Marker>
      )}
      {incidents.map((i) => (
        <span key={i.id}>
          <Marker position={[i.lat, i.lon]} icon={incidentIcon}>
            <Popup>
              <b>{i.title}</b>
              <br />
              {i.details}
            </Popup>
          </Marker>
          <Circle center={[i.lat, i.lon]} radius={i.radius_m} pathOptions={{ color: COLORS.delayed, weight: 1.5, fillColor: '#e6b5d6', fillOpacity: 0.28 }} />
        </span>
      ))}
      {routes.map((r, i) => (
        <Polyline
          key={r.id}
          positions={r.points.map((p: any) => [p.lat, p.lon])}
          pathOptions={{
            color: i === 1 ? COLORS.recommended : i === 0 ? COLORS.delayed : COLORS.planned,
            weight: i === 1 ? 7 : 4,
            dashArray: i === 0 ? '10 9' : undefined,
            opacity: i === 1 ? 1 : 0.8,
            lineCap: 'round',
          }}
        />
      ))}
    </MapContainer>
  );
}
