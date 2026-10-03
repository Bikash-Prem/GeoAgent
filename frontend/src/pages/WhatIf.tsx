import React, { useEffect, useState } from 'react';
import { ArrowRight, FlaskConical, MapPin, Trash2 } from 'lucide-react';
import MapView from '../components/Map';
import { PageHead } from '../components/Shell';
import { getJSON, postJSON } from '../lib/api';
import { ACTION_LABEL, Ops } from '../lib/ops';

const TITLES: Record<string, string> = {
  accident_congestion: 'Crash on the route', road_closure: 'Road closed', traffic_spike: 'Traffic doubles',
  competing_emergencies: 'Second emergency', clear_roads: 'Roads clear',
};

function Outcome({ title, o, tone }: { title: string; o: any; tone: string }) {
  return (
    <article className={`outcome ${tone}`}>
      <small>{title}</small>
      <h3>{ACTION_LABEL[o.action] || o.action}</h3>
      <div className="outcome-eta">{o.eta_min.toFixed(1)}<span> min</span></div>
      <p>likely {o.eta_lower.toFixed(1)}–{o.eta_upper.toFixed(1)} min · {o.route_name} · <span className={`risk ${o.risk}`}>{o.risk}</span></p>
      <p className="muted">Delay chance {Math.round(o.delay_probability * 100)}% · backup {o.backup_vehicle_id || (o.backup_considered ? `${o.backup_considered} held` : 'none available')}</p>
    </article>
  );
}

export default function WhatIf({ ops }: { ops: Ops }) {
  const [presets, setPresets] = useState<any[]>([]);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState('');
  const [custom, setCustom] = useState<any[]>([]);
  const [kind, setKind] = useState('closure');

  useEffect(() => { getJSON('/api/v1/whatif/presets').then(setPresets).catch(() => setPresets(Object.keys(TITLES).map((id) => ({ id, description: '' })))); }, []);

  const run = async (preset: string) => {
    setBusy(preset);
    try {
      const r = await postJSON('/api/v1/whatif', { vehicle_id: ops.focus.id, preset, incidents: preset === 'custom' ? custom : [] });
      setResult(r);
    } catch (e: any) { ops.notify(`Scenario did not run: ${e.message}`, 'warn'); } finally { setBusy(''); }
  };
  const sc = result?.scenario;

  return (
    <>
      <PageHead eyebrow="WHAT-IF LAB / COUNTERFACTUALS" title="Ask what happens" accent="before it happens."
        lede="Each scenario runs the real planner, ETA model and policy on a copy of the live situation. Live incidents, the fleet and the decision log are never touched." />

      <section className="ops-section">
        <div className="scenario-grid">
          {presets.map((p) => (
            <button key={p.id} className={`scenario ${result?.preset === p.id ? 'on' : ''}`} onClick={() => run(p.id)} disabled={!!busy}>
              <FlaskConical size={18} />
              <b>{TITLES[p.id] || p.id}</b>
              <span>{p.description}</span>
              <em>{busy === p.id ? 'Running…' : 'Run'} <ArrowRight size={13} /></em>
            </button>
          ))}
        </div>

        <div className="whatif-layout">
          <div className="map-panel">
            <MapView className="map tall" focus={ops.focus} incidents={ops.incidents.filter((i) => !(result?.removed || []).includes(i.id))} routes={sc?.routes || ops.rec?.routes || []}
              recommendedId={sc?.route_id || ops.rec?.recommended_route_id} hospitals={ops.hospitals} ghostIncidents={[...(result?.injected || []), ...custom.map((c, i) => ({ ...c, id: `pending-${i}` }))]}
              onMapClick={(lat, lon) => setCustom([...custom, { kind, severity: 'high', lat, lon, radius_m: kind === 'traffic' ? 320 : 220 }])} scrollZoom />
            <div className="map-hint"><MapPin size={14} /> Click the map to drop your own {kind}. {custom.length > 0 && `${custom.length} placed.`}</div>
          </div>
          <aside className="side-stack">
            <div className="panel">
              <div className="panel-head"><h3>Build your own</h3></div>
              <div className="seg">{['accident', 'closure', 'traffic'].map((k) => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{k}</button>)}</div>
              <div className="cta-row">
                <button className="pill dark sm" disabled={!custom.length || !!busy} onClick={() => run('custom')}>Run my scenario</button>
                <button className="pill light sm" disabled={!custom.length} onClick={() => setCustom([])}><Trash2 size={13} /> Clear</button>
              </div>
            </div>
            {result ? (
              <div className={`panel verdict ${result.decision_changed ? 'changed' : ''}`}>
                <small className="kicker">{result.decision_changed ? 'DECISION CHANGES' : 'DECISION HOLDS'}</small>
                <p className="verdict-text">{result.summary}</p>
                <div className="outcomes">
                  <Outcome title="Now" o={result.baseline} tone="now" />
                  <Outcome title="If this happens" o={result.scenario} tone="then" />
                </div>
                <p className="fine">Nothing was written to the decision log. Run it for real from Command if the situation develops.</p>
              </div>
            ) : (
              <div className="panel"><p className="muted">Pick a scenario above. The map then shows the routes the engine would plan in that world.</p></div>
            )}
          </aside>
        </div>
      </section>
    </>
  );
}
