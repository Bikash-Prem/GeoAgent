import React, { useEffect, useState } from 'react';
import { Check, CloudSun, Fuel, Mountain, Plane, Wind, X } from 'lucide-react';
import AirRescueMap from '../components/AirRescueMap';
import { PageHead } from '../components/Shell';
import { getJSON, postJSON } from '../lib/api';
import { Ops } from '../lib/ops';

const REGIONS = [['himachal', 'Himachal Pradesh'], ['uttarakhand', 'Uttarakhand'], ['ladakh', 'Ladakh']];

export default function Air({ ops }: { ops: Ops }) {
  const [region, setRegion] = useState('himachal');
  const [plan, setPlan] = useState<any>(null);
  const [wx, setWx] = useState<{ wind_kmh?: number; visibility_km?: number; cloud_base_m?: number }>({});
  const [tasked, setTasked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setWx({}); setTasked(null); }, [region]);
  useEffect(() => {
    const q = new URLSearchParams({ region });
    Object.entries(wx).forEach(([k, v]) => v != null && q.set(k, String(v)));
    const t = setTimeout(() => getJSON(`/api/v1/air-rescue/plan?${q}`).then(setPlan).catch(() => ops.notify('Air rescue planner is not reachable.', 'warn')), 150);
    return () => clearTimeout(t);
  }, [region, wx]); // eslint-disable-line

  const execute = async () => {
    setBusy(true);
    try {
      const d = await postJSON('/api/v1/air-rescue/execute', { region, weather: wx });
      setTasked(d.air_ambulance.name);
      ops.notify(`${d.air_ambulance.name} tasked to ${d.selected_landing_zone.name}. Recorded in the audit trail.`);
      ops.speak(`Air rescue tasked. ${d.air_ambulance.name}, estimated time to patient ${Math.round(d.flight_eta_min)} minutes.`);
    } catch (e: any) { ops.notify(e.message, 'warn'); } finally { setBusy(false); }
  };
  const w = plan?.weather;
  const blocked = plan?.checks_failed?.length > 0;

  return (
    <>
      <PageHead eyebrow="AIR RESCUE / HIMALAYAN REGIONS" title="When the road ends," accent="go airborne." image="/images/air-rescue.svg" alt="Rescue helicopter over snow-capped mountains"
        lede="GeoAgentic picks the aircraft and landing zone that reach the patient soonest, then checks wind, visibility, cloud base, altitude ceiling and fuel range before it lets you task the flight." />

      <section className="ops-section">
        <div className="seg big" role="tablist">{REGIONS.map(([id, label]) => <button key={id} role="tab" aria-selected={region === id} className={region === id ? 'on' : ''} onClick={() => setRegion(id)}><Mountain size={14} /> {label}</button>)}</div>
        <div className="air-layout">
          <div className="map-panel"><AirRescueMap plan={plan} />
            {plan && <div className={`air-verdict ${blocked ? 'no' : 'yes'}`}>{blocked ? <X size={15} /> : <Check size={15} />} {plan.decision}</div>}
          </div>
          <aside className="side-stack">
            <div className="panel">
              <div className="panel-head"><div><small className="kicker">CASUALTY</small><h3>{plan?.incident?.name || '—'}</h3></div><span className="tag">{plan?.terrain_risk} terrain</span></div>
              <p className="muted">{plan?.incident?.details}</p>
              <div className="kv">
                <div><small>Aircraft</small><b>{plan?.air_ambulance?.name}</b><span>{plan?.air_ambulance?.base}</span></div>
                <div><small>To patient</small><b>{plan ? `${plan.flight_eta_min} min` : '—'}</b><span>incl. start-up & approach</span></div>
                <div><small>Landing zone</small><b>{plan?.selected_landing_zone?.name}</b><span>{plan?.selected_landing_zone?.altitude_m?.toLocaleString()} m · {plan?.selected_landing_zone?.status?.toLowerCase()}</span></div>
                <div><small>Feasibility</small><b>{plan ? `${Math.round(plan.landing_feasibility * 100)}%` : '—'}</b><span>{plan?.oxygen_required ? 'oxygen on board' : 'no oxygen needed'}</span></div>
                <div><small>To hospital</small><b>{plan ? `${plan.to_hospital_min} min` : '—'}</b><span>{plan?.hospital?.name}</span></div>
                <div><small><Fuel size={11} /> Mission</small><b>{plan ? `${plan.mission_km} km` : '—'}</b><span>fuel {plan?.air_ambulance?.fuel_pct}% · range {plan?.air_ambulance?.range_km} km</span></div>
              </div>
            </div>
            <div className="panel">
              <div className="panel-head"><h3><CloudSun size={16} /> Conditions at the zone</h3><span className={`hstat ${w?.status === 'FLYABLE' ? 'READY' : w?.status === 'NO-FLY' ? 'DIVERT' : 'LIMITED'}`}>{w?.status}</span></div>
              <p className="muted">Enter the latest pilot or met report to re-check the plan.</p>
              <div className="form">
                <label className="range"><Wind size={12} /> Wind <b>{w?.wind_kmh} km/h</b><input type="range" min={0} max={80} value={w?.wind_kmh ?? 0} onChange={(e) => setWx({ ...wx, wind_kmh: Number(e.target.value) })} /></label>
                <label className="range">Visibility <b>{w?.visibility_km} km</b><input type="range" min={0} max={15} step={0.5} value={w?.visibility_km ?? 0} onChange={(e) => setWx({ ...wx, visibility_km: Number(e.target.value) })} /></label>
                <label className="range">Cloud base <b>{w?.cloud_base_m?.toLocaleString()} m</b><input type="range" min={1000} max={8000} step={100} value={w?.cloud_base_m ?? 0} onChange={(e) => setWx({ ...wx, cloud_base_m: Number(e.target.value) })} /></label>
              </div>
              <ul className="checks">
                {(plan?.checks_failed || []).map((c: string) => <li key={c} className="fail"><X size={13} />{c}</li>)}
                {(plan?.checks_passed || []).map((c: string) => <li key={c}><Check size={13} />{c}</li>)}
              </ul>
              <button className="pill dark full" disabled={!plan || blocked || busy || !!tasked} onClick={execute}>
                <Plane size={15} /> {tasked ? `${tasked} tasked` : blocked ? 'Flight blocked by checks' : busy ? 'Tasking…' : 'Task air ambulance'}
              </button>
            </div>
          </aside>
        </div>
        {plan && (
          <div className="panel table-panel">
            <div className="panel-head"><h3>Every option considered</h3><small className="muted">sorted by time to patient, penalised by feasibility</small></div>
            <div className="dp-scroll"><table className="light-table">
              <thead><tr><th>Aircraft</th><th>Landing zone</th><th>To patient</th><th>Feasibility</th><th>Status</th></tr></thead>
              <tbody>{plan.options.map((o: any, i: number) => <tr key={i} className={i === 0 ? 'best' : ''}><td>{o.unit}</td><td>{o.landing_zone}</td><td>{o.eta_min} min</td><td>{Math.round(o.feasibility * 100)}%</td><td>{o.blocked ? <span className="risk high">blocked</span> : <span className="risk low">ok</span>}</td></tr>)}</tbody>
            </table></div>
            <p className="fine">{plan.simulation_note}</p>
          </div>
        )}
      </section>
    </>
  );
}
