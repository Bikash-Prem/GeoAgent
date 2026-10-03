import React from 'react';
import { Check, X } from 'lucide-react';

const LABEL: Record<string, string> = {
  continue: 'Continue on current route',
  reroute: 'Reroute current unit',
  dispatch_backup: 'Dispatch backup unit',
  reroute_and_dispatch: 'Reroute + dispatch backup',
  continue_and_dispatch: 'Continue + dispatch backup',
};

export default function DecisionPanel({ rec, status, onDecide }: { rec: any; status: 'pending' | 'approved' | 'rejected'; onDecide: (approved: boolean) => void }) {
  const d = rec?.decision;
  if (!d) return <div className="dp empty">Run an analysis or ask GeoAgent to see the decision.</div>;
  const top = d.recommended_action;
  const rows = [top, ...d.alternatives];
  return (
    <div className="dp">
      <div className="dp-head">
        <div>
          <small>RECOMMENDED ACTION</small>
          <h3>{LABEL[top.action] || top.action}</h3>
        </div>
        <span className={`dp-status ${status}`}>{status === 'pending' ? 'Awaiting dispatcher' : status}</span>
      </div>
      <p className="dp-reason">{d.reasoning}</p>
      <div className="dp-scroll">
        <table>
          <thead>
            <tr><th>Action</th><th>ETA (interval)</th><th>Risk</th><th>Delay prob.</th><th>Coverage</th></tr>
          </thead>
          <tbody>
            {rows.map((a: any, i: number) => (
              <tr key={a.action_id} className={i === 0 ? 'best' : ''}>
                <td>{LABEL[a.action] || a.action}{a.backup_vehicle_id ? ` · ${a.backup_vehicle_id}` : ''}</td>
                <td>{a.expected_eta_minutes.toFixed(1)} <small>({a.eta_uncertainty.lower.toFixed(1)}–{a.eta_uncertainty.upper.toFixed(1)})</small></td>
                <td><span className={`risk ${a.risk.level.toLowerCase()}`}>{a.risk.level.toLowerCase()}</span></td>
                <td>{Math.round(a.delay_probability * 100)}%</td>
                <td>{a.fleet_coverage_change === 0 ? '—' : `${Math.round(a.fleet_coverage_change * 100)}% units`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="cta-row">
        <button className="pill dark sm" disabled={status !== 'pending'} onClick={() => onDecide(true)}><Check size={14} /> Approve</button>
        <button className="pill light sm" disabled={status !== 'pending'} onClick={() => onDecide(false)}><X size={14} /> Reject</button>
      </div>
      <p className="dp-foot">Policy {d.model_versions.policy} · ETA model {d.model_versions.eta} (heuristic baseline) · every step is written to the decision trace.</p>
    </div>
  );
}
