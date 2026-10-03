import React, { useEffect, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import BenchmarkPanel from '../components/BenchmarkPanel';
import { Integrations, Replay } from '../components/Replay';
import { PageHead } from '../components/Shell';
import { download, getJSON } from '../lib/api';
import { ACTION_LABEL, Ops } from '../lib/ops';

const fmtS = (s: number | null) => (s == null ? '—' : s < 90 ? `${Math.round(s)} s` : `${(s / 60).toFixed(1)} min`);

export default function Evidence({ ops }: { ops: Ops }) {
  const [report, setReport] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [trace, setTrace] = useState<any>(null);
  const [hours, setHours] = useState(12);

  const load = () => Promise.all([getJSON(`/api/v1/reports/shift?hours=${hours}`), getJSON('/api/v1/decisions?limit=15'), getJSON('/api/audit')])
    .then(([r, d, a]) => { setReport(r); setDecisions(d.decisions); setAudit(a); }).catch(() => undefined);
  useEffect(() => { void load(); }, [hours, ops.status]); // eslint-disable-line
  useEffect(() => { if (open) getJSON(`/api/v1/decisions/${open}/trace`).then(setTrace).catch(() => setTrace(null)); }, [open]);

  const csv = async () => { try { await download('/api/v1/reports/decisions.csv', 'geoagentic-decisions.csv'); } catch (e: any) { ops.notify(e.message, 'warn'); } };
  const d = report?.decisions;

  return (
    <>
      <PageHead eyebrow="EVIDENCE / SHIFT · TRACE · BENCHMARK" title="Measured," accent="not claimed."
        lede="The shift report reads this deployment's own decision trace: how many calls, how fast dispatchers decided, how fast hospitals acknowledged. The benchmark tests the engine on seeded scenarios." />

      <section className="ops-section">
        <div className="section-head tight">
          <div><div className="eyebrow">SHIFT REPORT</div><h2 className="display mid">Last {hours} hours.</h2></div>
          <div className="cta-row">
            <div className="seg">{[1, 12, 24, 168].map((h) => <button key={h} className={hours === h ? 'on' : ''} onClick={() => setHours(h)}>{h === 168 ? '7 d' : `${h} h`}</button>)}</div>
            <button className="pill dark sm" onClick={csv}><Download size={14} /> Export decisions CSV</button>
          </div>
        </div>
        <div className="report-grid">
          <div className="rcard ink"><small>Decisions</small><b>{d?.total ?? '—'}</b><span>{d?.approved ?? 0} approved · {d?.rejected ?? 0} rejected · {d?.pending ?? 0} pending</span></div>
          <div className="rcard mint"><small>Median time to decide</small><b>{fmtS(d?.median_time_to_decision_s ?? null)}</b><span>generated → dispatcher approval</span></div>
          <div className="rcard"><small>Approval rate</small><b>{d?.approval_rate_pct != null ? `${d.approval_rate_pct}%` : '—'}</b><span>of reviewed recommendations</span></div>
          <div className="rcard"><small>Dispatches</small><b>{report?.operations?.dispatches ?? '—'}</b><span>{report?.operations?.green_corridors ?? 0} corridors · {report?.operations?.air_rescues ?? 0} air</span></div>
          <div className="rcard blue"><small>Hospital pre-alerts</small><b>{report?.hospital_alerts?.sent ?? '—'}</b><span>median ack {fmtS(report?.hospital_alerts?.median_ack_s ?? null)}</span></div>
          <div className="rcard"><small>Incidents logged</small><b>{report?.incidents?.logged ?? '—'}</b><span>{report?.incidents?.resolved ?? 0} resolved · {report?.operations?.what_if_runs ?? 0} what-ifs</span></div>
        </div>
      </section>

      <section className="ops-section">
        <div className="trace-layout">
          <div className="panel">
            <div className="panel-head"><h3><FileText size={16} /> Decision log</h3><small className="muted">select one to see its trace</small></div>
            <ul className="dec-list">
              {decisions.map((x) => (
                <li key={x.decision_id}>
                  <button className={open === x.decision_id ? 'on' : ''} onClick={() => setOpen(x.decision_id)}>
                    <span className={`dstat ${x.status}`}>{x.status}</span>
                    <b>{ACTION_LABEL[x.action] || x.action}</b>
                    <small>{x.vehicle_id} · {x.eta_min?.toFixed?.(1)} min · {new Date(x.created_at + 'Z').toLocaleTimeString()}</small>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="trace-panel">
            {!trace ? <p className="trace-empty">Choose a decision to replay how it was made, step by step.</p> : (
              <>
                <small className="kicker light">{trace.decision_id} · {trace.status}</small>
                {trace.events.map((e: any, i: number) => (
                  <div className="trace-row" key={i}>
                    <span className="num">{i + 1}</span>
                    <div><b>{e.event_type.replace(/_/g, ' ')}</b><p>{summarize(e)}</p></div>
                    <em>{new Date(e.created_at + 'Z').toLocaleTimeString()}</em>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </section>

      <section className="ops-section" id="replay">
        <div className="section-head tight">
          <div><div className="eyebrow">REPLAY / LAST 10 MINUTES</div><h2 className="display mid">Rewind the picture.</h2></div>
          <span className="aside-note">The control loop re-checks the decision every few seconds without writing to the log.</span>
        </div>
        <Replay ops={ops} />
      </section>

      <section className="ops-section" id="integrations">
        <div className="section-head tight">
          <div><div className="eyebrow">INTEGRATIONS</div><h2 className="display mid">Where the data comes from.</h2></div>
          <span className="aside-note">Every source is labelled; a fallback is never shown as live.</span>
        </div>
        <Integrations />
      </section>

      <section className="evidence" id="benchmark"><BenchmarkPanel /></section>

      <section className="ops-section">
        <div className="panel table-panel">
          <div className="panel-head"><h3>Audit log</h3><small className="muted">latest 25 events, all sources</small></div>
          <div className="dp-scroll"><table className="light-table audit">
            <thead><tr><th>Time</th><th>Event</th><th>Unit</th><th>Detail</th></tr></thead>
            <tbody>{audit.map((a) => <tr key={a.id}><td>{new Date(a.created_at + 'Z').toLocaleTimeString()}</td><td>{a.event_type.replace(/_/g, ' ')}</td><td>{a.vehicle_id || '—'}</td><td className="detail">{detail(a.payload)}</td></tr>)}</tbody>
          </table></div>
        </div>
      </section>
    </>
  );
}

function summarize(e: any): string {
  const p = e.payload || {};
  switch (e.event_type) {
    case 'situation': return `${p.incidents?.length ?? 0} incidents · fleet ${p.fleet?.available ?? '?'} ready · traffic ${p.traffic?.congestion_level ?? '?'}`;
    case 'evidence': return (p.items || []).map((x: any) => x.explanation).slice(0, 2).join(' ') || 'No evidence items.';
    case 'diagnosis': return `${p.cause} (${Math.round((p.confidence || 0) * 100)}% confidence)`;
    case 'predictions': return `${(p.items || []).length} ETA predictions with intervals`;
    case 'actions_evaluated': return (p.actions || []).map((a: any) => `${a.action} ${a.expected_eta_minutes?.toFixed?.(1)}m`).join(' · ');
    case 'recommendation': return `${ACTION_LABEL[p.action] || p.action}: ${p.expected_eta_minutes?.toFixed?.(1)} min`;
    case 'human_approval': return `${p.approved ? 'Approved' : 'Rejected'} by ${p.actor_id}${p.comment ? ` · ${p.comment}` : ''}`;
    case 'outcome_recorded': return `Outcome ${p.result}, actual ETA ${p.actual_eta_minutes ?? '—'} min`;
    default: return JSON.stringify(p).slice(0, 120);
  }
}
function detail(p: any): string {
  if (!p) return '';
  const keys = ['decision_id', 'incident_id', 'hospital', 'hospital_id', 'action', 'stage', 'eta_min', 'region', 'preset', 'route_name'];
  const parts = keys.filter((k) => p[k] != null).map((k) => `${k.replace('_id', '')}: ${p[k]}`);
  return parts.join(' · ') || JSON.stringify(p).slice(0, 90);
}
