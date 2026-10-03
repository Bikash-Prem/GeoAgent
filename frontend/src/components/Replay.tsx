import React, { useEffect, useRef, useState } from 'react';
import { Pause, Play, RotateCcw, Radio } from 'lucide-react';
import MapView from './Map';
import { getJSON, postJSON } from '../lib/api';
import { ACTION_LABEL, Ops } from '../lib/ops';

/** Scrub through the control loop's recent snapshots: where units were, what was on the roads, what the engine advised. */
export function Replay({ ops }: { ops: Ops }) {
  const [snaps, setSnaps] = useState<any[]>([]);
  const [idx, setIdx] = useState(0);
  const [follow, setFollow] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState<{ running: boolean; interval_s: number } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = async () => {
    try {
      const h = await getJSON('/api/v1/twin/history?limit=120');
      setSnaps(h.snapshots); setLoop({ running: h.running, interval_s: h.interval_s });
      if (follow) setIdx(Math.max(0, h.snapshots.length - 1));
    } catch { /* offline */ }
  };
  useEffect(() => { void load(); }, [ops.twin?.snapshot_id]); // eslint-disable-line
  useEffect(() => {
    if (!playing) { if (timer.current) clearInterval(timer.current); return; }
    timer.current = setInterval(() => setIdx((i) => { if (i >= snaps.length - 1) { setPlaying(false); return i; } return i + 1; }), 700);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [playing, snaps.length]);

  const control = async (action: 'start' | 'stop' | 'reset') => {
    try { await postJSON('/api/v1/twin/command', { action }); await load(); ops.notify(action === 'stop' ? 'Control loop paused.' : action === 'start' ? 'Control loop running.' : 'Replay history cleared.'); }
    catch (e: any) { ops.notify(e.message, 'warn'); }
  };

  const s = snaps[idx];
  const focus = s?.vehicles?.find((v: any) => v.id === 'AMB-07');
  const rec = s?.recommendation;
  return (
    <div className="replay">
      <div className="replay-map map-panel">
        <MapView className="map tall" focus={focus} vehicles={s?.vehicles || []} incidents={s?.incidents || []} routes={s?.routes || []} recommendedId={rec?.route_id} hospitals={ops.hospitals} />
        {s && <div className="map-hint"><Radio size={14} /> {new Date(s.at).toLocaleTimeString()} · tick {s.tick}{s.drift ? ' · drift flagged' : ''}</div>}
      </div>
      <aside className="side-stack">
        <div className="panel">
          <div className="panel-head"><h3>Replay</h3><span className={`src-badge ${loop?.running ? 'live' : 'demo'}`}>{loop?.running ? `loop every ${loop.interval_s}s` : 'loop paused'}</span></div>
          {snaps.length === 0 ? <p className="muted">The control loop has not recorded a snapshot yet. It records one every few seconds while the API runs.</p> : (
            <>
              <label className="range scrub">Moment <b>{idx + 1} / {snaps.length}</b>
                <input type="range" min={0} max={snaps.length - 1} value={idx} onChange={(e) => { setIdx(Number(e.target.value)); setFollow(Number(e.target.value) === snaps.length - 1); }} />
              </label>
              <div className="cta-row">
                <button className="pill dark sm" onClick={() => { if (idx >= snaps.length - 1) setIdx(0); setFollow(false); setPlaying(!playing); }}>{playing ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Play</>}</button>
                <button className="pill light sm" onClick={() => { setFollow(true); setIdx(snaps.length - 1); }}>Live</button>
              </div>
            </>
          )}
        </div>
        {rec && (
          <div className={`panel ${s.drift ? 'verdict changed' : ''}`}>
            <small className="kicker">ENGINE ADVICE AT THAT MOMENT</small>
            <h3 className="replay-action">{ACTION_LABEL[rec.action] || rec.action}</h3>
            <p className="muted">{rec.route_name} · {rec.eta_min.toFixed(1)} min (likely {rec.eta_lower.toFixed(1)}–{rec.eta_upper.toFixed(1)}) · {String(rec.risk).toLowerCase()} risk · {rec.diagnosis}</p>
            <p className="muted">{s.incidents.length} active incidents · {s.vehicles.filter((v: any) => v.status === 'available').length} units ready{s.logged_decision ? ` · log: ${s.logged_decision.id} (${s.logged_decision.status})` : ''}</p>
          </div>
        )}
        <div className="cta-row">
          <button className="pill light sm" onClick={() => control(loop?.running ? 'stop' : 'start')}>{loop?.running ? <><Pause size={13} /> Pause loop</> : <><Play size={13} /> Resume loop</>}</button>
          <button className="pill light sm" onClick={() => control('reset')}><RotateCcw size={13} /> Clear history</button>
        </div>
      </aside>
    </div>
  );
}

export function Integrations() {
  const [providers, setProviders] = useState<any[]>([]);
  useEffect(() => {
    const load = () => getJSON('/api/v1/twin/providers').then((d) => setProviders(d.providers)).catch(() => undefined);
    void load(); const t = setInterval(load, 15000); return () => clearInterval(t);
  }, []);
  return (
    <div className="int-grid">
      {providers.map((p) => (
        <article key={p.name} className={`int ${p.mode}`}>
          <div className="int-top"><small>{p.name}</small><span className={`src-badge ${p.mode}`}>{p.mode}</span></div>
          <h3>{p.source}</h3>
          <p>{p.detail}</p>
          {p.last && <p className={`int-last ${p.last.available ? '' : 'bad'}`}>{p.last.available ? `Last sync ${new Date(p.last.observed_at).toLocaleTimeString()}${p.last.count != null ? ` · ${p.last.count} records` : ''}` : `Last sync failed: ${p.last.message}`}</p>}
          {p.mode !== 'live' && <p className="int-how">{HOW[p.name]}</p>}
        </article>
      ))}
    </div>
  );
}
const HOW: Record<string, string> = {
  routing: 'Set GOOGLE_ROUTES_API_KEY (or ROUTING_PROVIDER=mapbox + MAPBOX_ACCESS_TOKEN) for real-road routes.',
  traffic: 'Set TRAFFIC_PROVIDER=tomtom + TOMTOM_API_KEY for live flow speed and incident import.',
  fleet: 'Set FLEET_PROVIDER=traccar, FLEET_API_URL and TRACCAR_DEVICE_MAP for live GPS.',
};
