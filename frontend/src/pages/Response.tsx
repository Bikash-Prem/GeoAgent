import React, { useCallback, useEffect, useState } from 'react';
import { Ambulance, BellRing, Check, Hospital, Power, Radio, TrafficCone, Zap } from 'lucide-react';
import { PageHead } from '../components/Shell';
import { getJSON, postJSON } from '../lib/api';
import { Ops, mins, pct } from '../lib/ops';

const DISPATCHABLE = new Set(['medical', 'accident']);

function Bar({ value, label }: { value: number; label: string }) {
  const tone = value >= 0.85 ? 'bad' : value >= 0.6 ? 'mid' : 'ok';
  return <div className="bar"><span>{label}</span><div><i className={tone} style={{ width: `${Math.round(value * 100)}%` }} /></div><b>{pct(value)}</b></div>;
}

export default function Response({ ops }: { ops: Ops }) {
  const calls = ops.incidents.filter((i) => DISPATCHABLE.has(i.kind));
  const [callId, setCallId] = useState<string>('');
  const [plan, setPlan] = useState<any>(null);
  const [planError, setPlanError] = useState('');
  const [assignments, setAssignments] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<any>({});
  const [busy, setBusy] = useState('');

  const loadSide = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([getJSON('/api/v1/dispatch/assignments'), getJSON('/api/v1/hospitals/alerts')]);
      setAssignments(a.assignments); setAlerts(b.alerts);
    } catch { /* API offline; the toast already says so */ }
  }, []);
  const loadPlan = useCallback(async (id: string) => {
    setPlanError('');
    try { setPlan(await getJSON(`/api/v1/dispatch/plan${id ? `?incident_id=${id}` : ''}`)); }
    catch (e: any) { setPlan(null); setPlanError(e.message); }
  }, []);

  useEffect(() => { void loadSide(); const t = setInterval(loadSide, 8000); return () => clearInterval(t); }, [loadSide]);
  useEffect(() => { void loadPlan(callId); }, [callId, ops.vehicles.map((v) => v.status).join(), ops.hospitals.map((h) => h.status).join()]); // eslint-disable-line

  const execute = async () => {
    if (!plan) return;
    setBusy('dispatch');
    try {
      const d = await postJSON('/api/v1/dispatch/execute', { incident_id: plan.incident.id });
      if (d.corridor) { ops.setCorridor(d.corridor); ops.setSignals(d.corridor.signals || []); }
      ops.notify(`${d.ambulance.name} dispatched to ${d.incident.title}. ${d.hospital?.name || 'Hospital'} pre-alerted. Green corridor activated.`);
      if (d.corridor) ops.speak(`Green corridor activated for ${d.ambulance.name}. ${d.corridor.intersections} intersections are cleared.`);
      setCallId(''); await ops.refresh(); await loadSide();
    } catch (e: any) { ops.notify(`Dispatch not executed: ${e.message}`, 'warn'); } finally { setBusy(''); }
  };
  const complete = async (id: string) => {
    try { await postJSON(`/api/v1/dispatch/assignments/${id}/complete`); ops.notify(`${id} closed. Unit back in service.`); await ops.refresh(); await loadSide(); }
    catch (e: any) { ops.notify(e.message, 'warn'); }
  };
  const toggleCorridor = async () => {
    setBusy('corridor');
    try {
      if (ops.corridor) {
        const d = await postJSON(`/api/v1/corridor/${ops.corridor.id}/deactivate`);
        ops.setCorridor(null); ops.setSignals(d.signals); ops.notify('Green corridor released. Signals back on their normal cycle.');
      } else {
        const d = await postJSON('/api/v1/corridor/activate', { vehicle_id: ops.focus.id });
        ops.setCorridor(d); ops.setSignals(d.signals);
        ops.notify(`Green corridor active on ${d.route_name}: ${d.intersections} intersections held green.`);
        ops.speak(`Green corridor activated for ${ops.focus.name}. ${d.intersections} intersections cleared.`);
      }
    } catch (e: any) { ops.notify(`Corridor not changed: ${e.message}`, 'warn'); } finally { setBusy(''); }
  };
  const ack = async (id: number) => {
    try { await postJSON(`/api/v1/hospitals/alerts/${id}/ack`, { actor: 'er-desk' }); await loadSide(); ops.notify('Alert acknowledged by the hospital desk.'); }
    catch (e: any) { ops.notify(e.message, 'warn'); }
  };
  const update = async (a: any) => {
    try {
      await postJSON('/api/v1/hospitals/alerts', { hospital_id: a.hospital_id, vehicle_id: a.vehicle_id, incident_id: a.incident_id, stage: 'en_route', priority: a.priority, condition: a.condition, eta_min: a.eta_min ? Math.max(1, a.eta_min - 5) : null, note: 'Patient on board, en route' });
      await loadSide(); ops.notify('En-route update sent to the hospital.');
    } catch (e: any) { ops.notify(e.message, 'warn'); }
  };
  const saveHospital = async (id: string) => {
    try { await postJSON(`/api/v1/hospitals/${id}/capacity`, draft); setEditing(null); await ops.refresh(); ops.notify('Hospital capacity updated. Dispatch choices use it immediately.'); }
    catch (e: any) { ops.notify(e.message, 'warn'); }
  };
  const hospitalName = (id: string) => ops.hospitals.find((h) => h.id === id)?.name || id;
  const golden = plan ? Math.min(1, plan.call_to_care_min / 60) : 0;

  return (
    <>
      <PageHead eyebrow="RESPONSE / DISPATCH · CORRIDOR · HOSPITALS" title="Send the right unit." accent="Warn the right door." image="/images/ambulance.jpg" alt="Ambulance responding on a city street"
        lede="Units are ranked by routed ETA on today's roads, not straight-line distance. Hospitals by transport time, specialty and live ICU load. Nothing moves until you press the button." />

      <section className="ops-section">
        <div className="section-head tight"><div><div className="eyebrow">AI DISPATCH</div><h2 className="display mid">Who goes, and where to.</h2></div></div>
        <div className="dispatch-grid">
          <div className="panel">
            <div className="panel-head"><h3>Open calls</h3><span className="count">{calls.length}</span></div>
            <div className="call-list">
              <button className={callId === '' ? 'on' : ''} onClick={() => setCallId('')}><b>Most urgent unassigned</b><small>picked by severity, then newest</small></button>
              {calls.map((c) => <button key={c.id} className={callId === c.id ? 'on' : ''} onClick={() => setCallId(c.id)}><span className={`sev ${c.severity}`} /><b>{c.title}</b><small>{c.id} · {c.kind}</small></button>)}
            </div>
            <a className="link small" href="#/command">Log a new call on the map →</a>
          </div>

          <div className="panel dark-panel">
            {planError && <div className="empty-state"><h3>No plan right now</h3><p>{planError === 'no available ambulance' ? 'Every ambulance is committed. Close a finished assignment to free a unit.' : planError === 'no open emergency call needs a unit' ? 'All open calls already have a unit. Log a new call from Command.' : planError}</p></div>}
            {plan && (
              <>
                <div className="plan-top">
                  <div><small>CALL</small><h3>{plan.incident.title}</h3><span className={`risk ${plan.incident.severity}`}>{plan.incident.severity}</span> <span className="tag">{plan.incident.kind}</span></div>
                  <Ambulance size={28} />
                </div>
                <div className="plan-stats">
                  <div><small>Unit</small><b>{plan.ambulance.name}</b><span>{mins(plan.response_eta_min)} to scene</span></div>
                  <div><small>Hospital</small><b>{plan.hospital?.name || 'None accepting'}</b><span>{plan.hospital ? `${mins(plan.transport_min)} transport` : '—'}</span></div>
                  <div><small>Decision margin</small><b>{plan.decision_margin_min != null ? `${plan.decision_margin_min.toFixed(1)} min` : 'only unit'}</b><span>vs next-best unit</span></div>
                  <div><small>Coverage after</small><b>{plan.coverage_after_pct != null ? `${plan.coverage_after_pct}%` : '—'}</b><span>of area within target</span></div>
                </div>
                <div className="golden">
                  <div className="golden-head"><span>Golden hour</span><b>{plan.call_to_care_min} min call-to-care · {plan.golden_hour_remaining_min >= 0 ? `${plan.golden_hour_remaining_min} min spare` : `${-plan.golden_hour_remaining_min} min over`}</b></div>
                  <div className="golden-bar"><i style={{ width: `${(plan.response_eta_min / 60) * 100}%` }} className="a" /><i style={{ width: `${(plan.on_scene_min / 60) * 100}%` }} className="b" /><i style={{ width: `${(plan.transport_min / 60) * 100}%` }} className="c" /></div>
                  <div className="golden-key"><span><i className="a" />Response</span><span><i className="b" />On scene ({plan.on_scene_min}m)</span><span><i className="c" />Transport</span></div>
                </div>
                <div className="dp-scroll">
                  <table className="light-table">
                    <thead><tr><th>Unit</th><th>Routed ETA</th><th>Coverage cost</th></tr></thead>
                    <tbody>{plan.unit_options.map((o: any, i: number) => <tr key={o.vehicle_id} className={i === 0 ? 'best' : ''}><td>{o.name}</td><td>{mins(o.eta_min)}</td><td>−{o.coverage_drop_pct}% area</td></tr>)}</tbody>
                  </table>
                </div>
                <ul className="reasons">{plan.hospital_options.map((h: any, i: number) => <li key={h.id} className={i === 0 ? 'best' : ''}><b>{h.name}</b> <span className={`hstat ${h.status}`}>{h.status}</span><small>{h.reasons.join(' · ')}</small></li>)}</ul>
                <button className="pill light full" onClick={execute} disabled={busy === 'dispatch'}><Zap size={15} /> {busy === 'dispatch' ? 'Dispatching…' : `Dispatch ${plan.ambulance.name} and pre-alert`}</button>
              </>
            )}
          </div>

          <div className="panel">
            <div className="panel-head"><h3>Assignments</h3><span className="count">{assignments.filter((a) => a.status === 'assigned').length}</span></div>
            {assignments.length === 0 && <p className="muted">No units dispatched in this session yet.</p>}
            <ul className="assign-list">
              {assignments.map((a) => (
                <li key={a.id} className={a.status}>
                  <div><b>{a.vehicle_id} → {a.incident_id}</b><small>{a.id} · {hospitalName(a.hospital_id)} · {a.status}</small></div>
                  {a.status === 'assigned' && <button className="pill light sm" onClick={() => complete(a.id)}>Close</button>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="ops-section corridor-section">
        <figure className="corridor-art"><img src="/images/corridor.svg" alt="Traffic lights held green for an ambulance" /></figure>
        <div className="corridor-copy">
          <div className="eyebrow">SMART GREEN CORRIDOR</div>
          <h2 className="display mid">{ops.corridor ? 'Corridor is open.' : 'Hold the lights.'}</h2>
          <p className="lede small">{ops.corridor
            ? `${ops.corridor.intersections} intersections on ${ops.corridor.route_name} are held green for ${ops.corridor.vehicle_id}. Estimated red-light waiting removed: ${ops.corridor.est_wait_avoided_min} min (assumes ${ops.corridor.assumption}).`
            : `Hold every signal on ${ops.focus.name}'s recommended route at green. The route comes from the decision engine, so it follows reroutes automatically.`}</p>
          <button className={`pill ${ops.corridor ? 'light' : 'dark'}`} onClick={toggleCorridor} disabled={busy === 'corridor'}>
            {ops.corridor ? <><Power size={15} /> Release corridor</> : <><TrafficCone size={15} /> Activate corridor</>}
          </button>
          <div className="signal-grid">
            {ops.signals.map((s) => <div key={s.id} className={`sig ${s.state.toLowerCase()} ${s.overridden ? 'over' : ''}`}><i />{s.name}<small>{s.overridden ? 'held' : s.state.toLowerCase()}</small></div>)}
          </div>
          <p className="fine">Signal controller is simulated in this build. Connecting a real ATCS needs the city's controller API.</p>
        </div>
      </section>

      <section className="ops-section">
        <div className="section-head tight">
          <div><div className="eyebrow">HOSPITAL NETWORK</div><h2 className="display mid">Know the bed before you leave.</h2></div>
          <span className="aside-note"><Hospital size={14} /> Capacity is edited by each hospital desk.</span>
        </div>
        <div className="hosp-layout">
          <div className="hosp-grid">
            {ops.hospitals.map((h) => (
              <article key={h.id} className={`hosp ${h.status}`}>
                <div className="hosp-top"><div><b>{h.name}</b><small>{h.specialties.join(' · ')}{h.helipad ? ' · helipad' : ''}</small></div><span className={`hstat ${h.status}`}>{h.status}</span></div>
                {editing === h.id ? (
                  <div className="form">
                    {(['icu', 'er', 'oxygen'] as const).map((k) => (
                      <label key={k} className="range">{k.toUpperCase()} in use <b>{pct(draft[k])}</b><input type="range" min={0} max={1} step={0.01} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: Number(e.target.value) })} /></label>
                    ))}
                    <label className="check"><input type="checkbox" checked={draft.accepting} onChange={(e) => setDraft({ ...draft, accepting: e.target.checked })} /> Accepting patients</label>
                    <div className="cta-row"><button className="pill dark sm" onClick={() => saveHospital(h.id)}>Save</button><button className="pill light sm" onClick={() => setEditing(null)}>Cancel</button></div>
                  </div>
                ) : (
                  <>
                    <Bar label="ICU" value={h.icu} /><Bar label="ER" value={h.er} /><Bar label="O₂" value={h.oxygen} />
                    <div className="hosp-foot"><small>{h.source === 'hospital_desk' ? 'Updated by hospital desk' : 'Demo seed values'}</small><button className="link small" onClick={() => { setEditing(h.id); setDraft({ icu: h.icu, er: h.er, oxygen: h.oxygen, accepting: h.accepting }); }}>Update</button></div>
                  </>
                )}
              </article>
            ))}
          </div>
          <div className="panel inbox">
            <div className="panel-head"><h3><BellRing size={16} /> Pre-alert inbox</h3><span className="count">{alerts.filter((a) => !a.acknowledged).length}</span></div>
            {alerts.length === 0 && <p className="muted">Pre-alerts appear here the moment a unit is dispatched.</p>}
            <ul className="alert-list">
              {alerts.map((a) => (
                <li key={a.id} className={a.acknowledged ? 'acked' : ''}>
                  <div className="alert-top"><span className={`risk ${a.priority}`}>{a.stage.replace('_', ' ')}</span><b>{hospitalName(a.hospital_id)}</b></div>
                  <p>{a.note || a.condition} {a.eta_min != null && <>· ETA {a.eta_min} min</>}</p>
                  <div className="alert-actions">
                    {a.acknowledged ? <small><Check size={12} /> Acknowledged by {a.acknowledged_by}</small> : <button className="pill dark sm" onClick={() => ack(a.id)}>Acknowledge</button>}
                    {a.stage === 'pre_alert' && <button className="pill light sm" onClick={() => update(a)}><Radio size={13} /> Send en-route update</button>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </>
  );
}
