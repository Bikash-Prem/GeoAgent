import { useCallback, useEffect, useRef, useState } from 'react';
import { getJSON, postJSON, wsUrl } from './api';

export type RouteT = {
  id: string; name: string; eta_min: number; delay_min: number; uncertainty_min: number; risk: string; distance_km: number;
  points: { lat: number; lon: number }[]; explanation: string; eta_lower?: number; eta_upper?: number; risk_score?: number; incidents_hit?: string[];
};
export type Rec = {
  vehicle_id: string; current_eta_min: number; delay_min: number; cause: string; confidence: number; evidence: string[]; routes: RouteT[];
  backup_vehicle_id: string | null; backup_eta_min: number | null; decision_id?: string | null; recommended_route_id?: string | null; decision?: any;
};
export type DecisionStatus = 'pending' | 'approved' | 'rejected';

export const FOCUS = 'AMB-07';
const fallbackVehicle = { id: 'AMB-07', name: 'AMB-07', status: 'active', lat: 12.9712, lon: 77.594, speed_kmh: 62, heading: 72, hospital: 'City General Hospital' };

/** Shared operational state for every page: one source of truth, refreshed by polling + the telemetry socket. */
export function useOps() {
  const [vehicles, setVehicles] = useState<any[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [hospitals, setHospitals] = useState<any[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  const [corridor, setCorridor] = useState<any>(null);
  const [rec, setRec] = useState<Rec | null>(null);
  const [status, setStatus] = useState<DecisionStatus>('pending');
  const [live, setLive] = useState(false);
  const [apiOffline, setApiOffline] = useState(false);
  const [loading, setLoading] = useState(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [notice, setNoticeRaw] = useState<{ text: string; tone: 'ok' | 'warn' } | null>(null);
  const [voiceOn, setVoiceOn] = useState(false);
  const [twin, setTwin] = useState<any>(null); // latest control-loop snapshot (read-only re-evaluation)
  const [mission, setMission] = useState<any>(null);
  const lastMissionPhase = useRef<string | null>(null);
  const spoken = useRef<Record<string, number>>({});

  const notify = useCallback((text: string, tone: 'ok' | 'warn' = 'ok') => setNoticeRaw({ text, tone }), []);
  const clearNotice = useCallback(() => setNoticeRaw(null), []);

  const speak = useCallback((message: string) => {
    if (!voiceOn || !('speechSynthesis' in window)) return;
    const now = Date.now();
    if (now - (spoken.current[message] || 0) < 30000) return; // never repeat the same line within 30 s
    spoken.current[message] = now;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(message);
    u.rate = 0.95; u.lang = 'en-IN';
    window.speechSynthesis.speak(u);
  }, [voiceOn]);

  const refresh = useCallback(async () => {
    try {
      const [v, i, h, s, c, m] = await Promise.all([
        getJSON('/api/vehicles'), getJSON('/api/incidents'), getJSON('/api/v1/hospitals'), getJSON('/api/v1/signals'), getJSON('/api/v1/corridor'), getJSON('/api/v1/mission/active'),
      ]);
      setVehicles((prev) => v.map((x: any) => {
        const p = prev.find((y) => y.id === x.id && y._live); // keep the streamed position between polls
        return p ? { ...x, lat: p.lat, lon: p.lon, speed_kmh: p.speed_kmh, heading: p.heading, _live: true } : x;
      }));
      setIncidents(i); setHospitals(h.hospitals); setSignals(s.signals); setCorridor(c.active ? c : null); setMission(m.mission || null);
      setApiOffline(false);
    } catch {
      setApiOffline(true);
      setVehicles((v) => (v.length ? v : [fallbackVehicle]));
    }
  }, []);

  const analyze = useCallback(async () => {
    setLoading(true);
    try {
      const t0 = performance.now();
      setRec(await getJSON(`/api/recommendations/${FOCUS}`));
      setLatencyMs(Math.round(performance.now() - t0));
    } catch {
      notify('The API is not reachable. Start the backend on port 8000, then select Run analysis.', 'warn');
    } finally { setLoading(false); }
  }, [notify]);

  const approveDecision = useCallback(async (approved: boolean) => {
    if (!rec?.decision_id) return;
    try {
      await postJSON(`/api/v1/decisions/${rec.decision_id}/approve`, {
        approved, selected_action_id: rec.decision?.recommended_action?.action_id, actor_id: 'dispatcher',
        comment: approved ? 'Approved from dispatcher console' : 'Rejected from dispatcher console',
      });
      setStatus(approved ? 'approved' : 'rejected');
      notify(approved ? 'Recommendation approved and written to the decision trace.' : 'Recommendation rejected and written to the decision trace.');
      if (approved) speak(`Recommendation approved for ${FOCUS}.`);
    } catch (e: any) { notify(`Decision not recorded: ${e.message}`, 'warn'); }
  }, [rec, notify, speak]);

  const act = useCallback(async (action: 'acknowledge' | 'dispatch_backup' | 'reroute', route_id?: string) => {
    try {
      await postJSON(`/api/vehicles/${FOCUS}/actions`, { action, route_id });
      notify(action === 'dispatch_backup' ? 'Backup dispatch request recorded.' : action === 'reroute' ? 'Reroute recorded.' : 'Incident acknowledged.');
    } catch (e: any) { notify(`Action not recorded: ${e.message}`, 'warn'); }
  }, [notify]);

  useEffect(() => { void refresh(); void analyze(); const t = setInterval(refresh, 2000); return () => clearInterval(t); }, [refresh, analyze]);
  useEffect(() => { setStatus('pending'); }, [rec?.decision_id]);
  useEffect(() => { if (!notice) return; const t = setTimeout(clearNotice, 6000); return () => clearTimeout(t); }, [notice, clearNotice]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    try { ws = new WebSocket(wsUrl('/ws/telemetry')); } catch { return; }
    ws.onopen = () => setLive(true);
    ws.onclose = () => setLive(false);
    ws.onerror = () => setLive(false);
    ws.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d.type === 'telemetry' && d.vehicle_id === FOCUS) {
        setVehicles((v) => v.map((x) => (x.id === FOCUS ? { ...x, lat: d.lat, lon: d.lon, speed_kmh: d.speed_kmh, heading: d.heading, _live: true } : x)));
      }
    };
    return () => ws?.close();
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const open = () => {
      try { ws = new WebSocket(wsUrl('/ws/twin')); } catch { return; }
      ws.onmessage = (e) => { try { const d = JSON.parse(e.data); if (d.type === 'TWIN_SNAPSHOT_UPDATED') setTwin(d.snapshot); } catch { /* ignore */ } };
      ws.onclose = () => { retry = setTimeout(open, 5000); };
    };
    open();
    return () => { if (retry) clearTimeout(retry); if (ws) { ws.onclose = null; ws.close(); } };
  }, []);

  useEffect(() => {
    const phase = mission?.phase || null;
    if (!phase || phase === lastMissionPhase.current) return;
    lastMissionPhase.current = phase;
    const messages: Record<string, string> = {
      dispatched: `Dispatch executed for ${mission.vehicle_name}.`,
      en_route: `${mission.vehicle_name} is en route. Estimated arrival ${mission.eta_min} minutes.`,
      on_scene: `${mission.vehicle_name} is on scene.`,
      transporting: `Patient transport started. ${mission.hospital_name || 'Receiving hospital'} has been updated.`,
      arriving: `${mission.vehicle_name} is approaching the hospital.`,
      arrived: `Mission complete. ${mission.vehicle_name} has arrived at the hospital.`,
    };
    if (messages[phase]) speak(messages[phase]);
  }, [mission, speak]);

  const drift = twin?.drift || null;
  const focus = vehicles.find((v) => v.id === FOCUS) || fallbackVehicle;
  return {
    twin, drift, mission, vehicles, incidents, hospitals, signals, corridor, rec, setRec, status, live, apiOffline, loading, latencyMs, notice, voiceOn,
    setVoiceOn, focus, notify, clearNotice, speak, refresh, analyze, approveDecision, act, setCorridor, setSignals,
  };
}
export type Ops = ReturnType<typeof useOps>;

export const pct = (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`);
export const mins = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${x.toFixed(d)} min`);
export const ACTION_LABEL: Record<string, string> = {
  continue: 'Continue current route', reroute: 'Reroute current unit', dispatch_backup: 'Dispatch backup unit',
  reroute_and_dispatch: 'Reroute + backup', continue_and_dispatch: 'Continue + backup',
};
