import React, { useState } from 'react';
import { Check, MapPin, Plus, RefreshCw } from 'lucide-react';
import MapView from '../components/Map';
import CommandBar from '../components/CommandBar';
import DecisionPanel from '../components/DecisionPanel';
import { PageHead } from '../components/Shell';
import { DriftBanner, SourceBadge } from '../components/LiveBits';
import { postJSON } from '../lib/api';
import { Ops } from '../lib/ops';

const KINDS = [
  { id: 'medical', label: 'Medical call', note: 'needs an ambulance' },
  { id: 'accident', label: 'Accident', note: 'needs an ambulance, slows traffic' },
  { id: 'closure', label: 'Road closure', note: 'slows traffic' },
  { id: 'traffic', label: 'Traffic jam', note: 'slows traffic' },
];

export default function Command({ ops }: { ops: Ops }) {
  const { rec, focus, incidents, vehicles } = ops;
  const [picking, setPicking] = useState(false);
  const [point, setPoint] = useState<{ lat: number; lon: number } | null>(null);
  const [form, setForm] = useState({ kind: 'medical', severity: 'high', title: '', radius_m: 180 });
  const [busy, setBusy] = useState(false);
  const routes = rec?.routes || [];
  const recommendedId = rec?.recommended_route_id || routes[0]?.id;

  const logIncident = async () => {
    if (!point) return;
    setBusy(true);
    try {
      const title = form.title.trim() || `${KINDS.find((k) => k.id === form.kind)?.label} reported`;
      const inc = await postJSON('/api/v1/incidents', { ...form, title, lat: point.lat, lon: point.lon });
      ops.notify(`${inc.id} logged. The decision engine re-analyzed with it.`);
      ops.speak(`New ${form.severity} severity ${form.kind} logged.`);
      setPoint(null); setPicking(false); setForm({ ...form, title: '' });
      await ops.refresh(); await ops.analyze();
    } catch (e: any) { ops.notify(`Incident not logged: ${e.message}`, 'warn'); } finally { setBusy(false); }
  };
  const resolve = async (id: string) => {
    try { await postJSON(`/api/v1/incidents/${id}/resolve`); ops.notify(`${id} resolved. Routes recalculated.`); await ops.refresh(); await ops.analyze(); }
    catch (e: any) { ops.notify(`Could not resolve: ${e.message}`, 'warn'); }
  };

  return (
    <>
      <PageHead eyebrow="COMMAND / LIVE PICTURE" title="Everything moving," accent="in one view." lede="Log calls straight onto the map, ask GeoAgent in plain words, and approve the decision it can prove. Every change re-runs the same engine." />

      <section className="drift-wrap"><DriftBanner ops={ops} /></section>

      <section className="cmd-layout">
        <div className="map-panel">
          <MapView className="map tall" focus={focus} vehicles={vehicles} incidents={incidents} routes={routes} recommendedId={recommendedId}
            hospitals={ops.hospitals} signals={ops.signals} corridor={ops.corridor} pending={point}
            onMapClick={picking ? (lat, lon) => setPoint({ lat, lon }) : undefined} scrollZoom />
          <div className="legend">
            <span><i style={{ background: '#b65e5a' }} />Current</span>
            <span><i style={{ background: '#67a6c2' }} />Alternative</span>
            <span><i style={{ background: '#6a9a63' }} />Recommended</span>
            <span><i className="sq" />Hospital</span>
          </div>
          {picking && <div className="map-hint"><MapPin size={14} /> {point ? 'Location set. Fill in the call and log it.' : 'Click the map where the call is.'}</div>}
        </div>

        <aside className="side-stack">
          <div className="panel">
            <div className="panel-head"><h3>Log a call</h3><button className={`pill sm ${picking ? 'dark' : 'light'}`} onClick={() => { setPicking(!picking); setPoint(null); }}>{picking ? 'Cancel' : <><Plus size={14} /> New</>}</button></div>
            {!picking ? <p className="muted">Start a new call, then click its location on the map.</p> : (
              <div className="form">
                <div className="seg">{KINDS.map((k) => <button key={k.id} className={form.kind === k.id ? 'on' : ''} onClick={() => setForm({ ...form, kind: k.id })} title={k.note}>{k.label}</button>)}</div>
                <label>What happened<input value={form.title} maxLength={160} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Two-wheeler collision, rider unconscious" /></label>
                <div className="row2">
                  <label>Severity<select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
                  <label>Affected radius<select value={form.radius_m} onChange={(e) => setForm({ ...form, radius_m: Number(e.target.value) })}>{[100, 180, 250, 350].map((r) => <option key={r} value={r}>{r} m</option>)}</select></label>
                </div>
                <small className="muted">{point ? `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}` : 'No location yet'}</small>
                <button className="pill dark sm full" disabled={!point || busy} onClick={logIncident}>{busy ? 'Logging…' : 'Log call'}</button>
              </div>
            )}
          </div>
          <div className="panel">
            <div className="panel-head"><h3>Active incidents</h3><span className="count">{incidents.length}</span></div>
            {incidents.length === 0 && <p className="muted">No active incidents. The roads are clear.</p>}
            <ul className="inc-list">
              {incidents.map((i) => (
                <li key={i.id}>
                  <span className={`sev ${i.severity}`} />
                  <div><b>{i.title}</b><small>{i.id} · {i.kind} · {i.severity}</small></div>
                  <button className="round sm" onClick={() => resolve(i.id)} title="Mark resolved" aria-label={`Resolve ${i.id}`}><Check size={14} /></button>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </section>

      <section className="console" id="console">
        <div className="section-head tight">
          <div><div className="eyebrow">CONSOLE / ASK · SEE THE OPTIONS · APPROVE</div><h2 className="display mid">Ask in plain words.</h2></div>
          <button className="pill light sm" onClick={ops.analyze} disabled={ops.loading}><RefreshCw size={14} className={ops.loading ? 'spin' : ''} /> Re-analyze</button>
        </div>
        <div className="console-grid">
          <CommandBar vehicleId={focus.id} onResult={(res) => { if (res.recommendation) ops.setRec(res.recommendation); ops.speak(res.answer.split('. ')[0]); }} />
          <DecisionPanel rec={rec} status={ops.status} onDecide={ops.approveDecision} />
        </div>
      </section>

      <section className="routes" id="routes">
        <div className="route-headline"><div className="eyebrow">ROUTE COMPARISON / ETA · DELAY · UNCERTAINTY · RISK</div><SourceBadge source={(rec as any)?.routing_source} /></div>
        <div className="route-grid">
          {routes.length === 0 && <div className="route-empty">Waiting for GeoAgent to generate routes…</div>}
          {routes.map((r, i) => (
            <article key={r.id} className={`route-card ${r.id === recommendedId ? 'picked' : ''}`}>
              <div className="route-top"><span className={`rdot r${i}`} /><b>{r.name}</b>{r.id === recommendedId && <em>Recommended</em>}</div>
              <div className="route-eta">{r.eta_min.toFixed(1)}<span> min</span></div>
              {r.eta_lower != null && r.eta_upper != null && <small className="interval">likely {r.eta_lower.toFixed(1)}–{r.eta_upper.toFixed(1)} min</small>}
              <dl>
                <div><dt>Δ Delay</dt><dd className={r.delay_min <= 0 ? 'good' : 'bad'}>{r.delay_min > 0 ? '+' : ''}{r.delay_min.toFixed(1)}m</dd></div>
                <div><dt>Uncertainty</dt><dd>±{r.uncertainty_min.toFixed(1)}m</dd></div>
                <div><dt>Distance</dt><dd>{r.distance_km?.toFixed?.(1) ?? '—'} km</dd></div>
                <div><dt>Risk</dt><dd><span className={`risk ${r.risk}`}>{r.risk}</span></dd></div>
              </dl>
              {r.incidents_hit && r.incidents_hit.length > 0 && <div className="hits">{r.incidents_hit.map((id) => <span key={id}>{id}</span>)}</div>}
              <p className="route-why">{r.explanation}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
