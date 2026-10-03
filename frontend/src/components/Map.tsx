import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Circle, Rectangle, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';

const icon = (html: string, size: number) => L.divIcon({ className: 'mk', html, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
const focusIcon = icon('<span class="mk-pulse"></span><span class="mk-core">🚑</span>', 44);
const unitIcon = (status: string) => icon(`<span class="mk-unit ${status}">🚑</span>`, 32);
const incidentIcon = (kind: string) => icon(`<span class="mk-x ${kind}">${kind === 'medical' ? '✚' : '✕'}</span>`, 34);
const whatifIcon = icon('<span class="mk-x whatif">?</span>', 34);
const hospitalIcon = (status: string) => icon(`<span class="mk-h ${status}">H</span>`, 30);
const signalIcon = (state: string, over: boolean) => icon(`<span class="mk-sig ${state.toLowerCase()} ${over ? 'over' : ''}"></span>`, 16);
const pinIcon = icon('<span class="mk-pin"></span>', 22);

export const COLORS = { delayed: '#b65e5a', recommended: '#6a9a63', planned: '#67a6c2', corridor: '#6a9a63' };

function ClickCatcher({ onClick }: { onClick?: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onClick?.(e.latlng.lat, e.latlng.lng) });
  return null;
}
function Resize() {
  const map = useMap();
  useEffect(() => { const t = setTimeout(() => map.invalidateSize(), 120); return () => clearTimeout(t); }, [map]);
  return null;
}

type Props = {
  focus?: any; vehicles?: any[]; incidents?: any[]; routes?: any[]; recommendedId?: string | null; hospitals?: any[]; signals?: any[];
  corridor?: any; cells?: any[]; ghostIncidents?: any[]; pending?: { lat: number; lon: number } | null; onMapClick?: (lat: number, lon: number) => void;
  zoom?: number; className?: string; scrollZoom?: boolean;
};

export default function MapView({ focus, vehicles = [], incidents = [], routes = [], recommendedId, hospitals = [], signals = [], corridor, cells = [], ghostIncidents = [], pending, onMapClick, zoom = 15, className = 'map', scrollZoom = false }: Props) {
  const center: [number, number] = [12.9708, 77.6005];
  return (
    <MapContainer center={center} zoom={zoom} scrollWheelZoom={scrollZoom} className={`${className} ${onMapClick ? 'pickable' : ''}`}>
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <Resize />
      <ClickCatcher onClick={onMapClick} />
      {cells.map((c, i) => (
        <Rectangle key={i} bounds={c.bounds} pathOptions={{ stroke: false, fillColor: c.eta_min == null ? '#b65e5a' : c.covered ? (c.eta_min < 6 ? '#6a9a63' : '#a9c99c') : '#e3a69f', fillOpacity: 0.42 }}>
          <Tooltip sticky>{c.eta_min == null ? 'No unit can reach this area' : `${c.unit}: ${c.eta_min.toFixed(1)} min`}</Tooltip>
        </Rectangle>
      ))}
      {corridor?.points && <Polyline positions={corridor.points.map((p: any) => [p.lat, p.lon])} pathOptions={{ color: COLORS.corridor, weight: 18, opacity: 0.22, lineCap: 'round' }} />}
      {routes.map((r, i) => (
        <Polyline key={r.id} positions={r.points.map((p: any) => [p.lat, p.lon])}
          pathOptions={{ color: r.id === recommendedId ? COLORS.recommended : i === 0 ? COLORS.delayed : COLORS.planned, weight: r.id === recommendedId ? 7 : 4,
            dashArray: i === 0 && r.id !== recommendedId ? '10 9' : undefined, opacity: r.id === recommendedId ? 1 : 0.8, lineCap: 'round' }}>
          <Tooltip sticky>{r.name} · {r.eta_min.toFixed(1)} min</Tooltip>
        </Polyline>
      ))}
      {incidents.map((i) => (
        <React.Fragment key={i.id}>
          {i.kind !== 'medical' && <Circle center={[i.lat, i.lon]} radius={i.radius_m} pathOptions={{ color: COLORS.delayed, weight: 1.5, fillColor: '#e6b5d6', fillOpacity: 0.28 }} />}
          <Marker position={[i.lat, i.lon]} icon={incidentIcon(i.kind)}>
            <Popup><b>{i.title}</b><br />{i.kind} · {i.severity} severity<br />{i.details}</Popup>
          </Marker>
        </React.Fragment>
      ))}
      {ghostIncidents.map((i) => (
        <React.Fragment key={i.id}>
          <Circle center={[i.lat, i.lon]} radius={i.radius_m} pathOptions={{ color: '#1c0f0e', weight: 1.5, dashArray: '6 6', fillColor: '#f0d34a', fillOpacity: 0.25 }} />
          <Marker position={[i.lat, i.lon]} icon={whatifIcon}><Popup><b>What-if {i.kind}</b><br />{i.severity} severity · {Math.round(i.radius_m)} m</Popup></Marker>
        </React.Fragment>
      ))}
      {signals.map((s) => (
        <Marker key={s.id} position={[s.lat, s.lon]} icon={signalIcon(s.state, s.overridden)}>
          <Tooltip direction="top">{s.name} · {s.state}{s.overridden ? ' (corridor)' : ''}</Tooltip>
        </Marker>
      ))}
      {hospitals.map((h) => (
        <Marker key={h.id} position={[h.lat, h.lon]} icon={hospitalIcon(h.status)}>
          <Popup><b>{h.name}</b><br />{h.status} · ICU {Math.round(h.icu * 100)}% in use<br />{h.specialties.join(', ')}</Popup>
        </Marker>
      ))}
      {vehicles.filter((v) => v.id !== focus?.id).map((v) => (
        <Marker key={v.id} position={[v.lat, v.lon]} icon={unitIcon(v.status)}>
          <Popup><b>{v.name}</b><br />{v.status}{v.hospital ? ` · to ${v.hospital}` : ''}</Popup>
        </Marker>
      ))}
      {focus && (
        <Marker position={[focus.lat, focus.lon]} icon={focusIcon}>
          <Popup><b>{focus.name}</b><br />{Math.round(focus.speed_kmh)} km/h · {focus.status}</Popup>
        </Marker>
      )}
      {pending && <Marker position={[pending.lat, pending.lon]} icon={pinIcon} />}
    </MapContainer>
  );
}
