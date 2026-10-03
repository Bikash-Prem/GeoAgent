import React, { useState } from 'react';
import { getJSON } from '../lib/api';

const NAMES: Record<string, string> = {
  static_shortest: 'Static shortest path',
  incident_aware_routing: 'Incident-aware routing',
  geoagentic_policy: 'GeoAgentic policy',
};
const STATUS: Record<string, string> = { met: 'Met', not_met: 'Not met', not_measured: 'Not measured' };

export default function BenchmarkPanel() {
  const [data, setData] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    setBusy(true);
    setError('');
    try {
      setData(await getJSON('/api/v1/evaluation/run?n=300&seed=7'));
    } catch (e) {
      setError('Benchmark could not run. Check that the API is up.');
    } finally {
      setBusy(false);
    }
  };

  const r = data?.routing;
  return (
    <div className="bm">
      <div className="bm-top">
        <div>
          <div className="eyebrow">EVIDENCE / SYNTHETIC BENCHMARK</div>
          <h2 className="display mid">Measured, <span className="g">not claimed.</span></h2>
          <p className="bm-note">The real planner, predictor and policy run on 300 seeded scenarios. The world is simulated, so this shows the logic is sound, not field performance.</p>
        </div>
        <button className="pill dark sm" onClick={run} disabled={busy}>{busy ? 'Running…' : data ? 'Re-run' : 'Run benchmark'}</button>
      </div>
      {error && <p className="cmd-error">{error}</p>}
      {data && (
        <>
          <div className="bm-targets">
            {data.targets.map((t: any) => (
              <div key={t.metric} className={`bm-card ${t.status}`}>
                <small>{t.metric}</small>
                <b>{t.value}</b>
                <span>Target {t.target} · {STATUS[t.status]}</span>
              </div>
            ))}
          </div>
          <div className="dp-scroll">
            <table>
              <thead><tr><th>Strategy</th><th>Mean arrival</th><th>Late &gt; {r.target_min} min</th><th>Route risk</th><th>vs static</th></tr></thead>
              <tbody>
                {Object.entries(r.strategies).map(([k, v]: [string, any]) => (
                  <tr key={k} className={k === 'geoagentic_policy' ? 'best' : ''}>
                    <td>{NAMES[k]}</td><td>{v.mean_min.toFixed(1)} min</td><td>{v.late_over_target_pct}%</td><td>{v.mean_route_risk.toFixed(2)}</td><td>{v.mean_reduction_vs_static_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="bm-note">
            ETA interval coverage: {r.eta.interval_coverage_pct}% raw → {r.eta.calibration.test_coverage_calibrated_interval_pct}% after calibration (target {r.eta.calibration.level_pct}%) ·
            ETA error {r.eta.rmse_min} min vs {r.eta.baseline_free_flow_rmse_min} min for a free-flow-only estimate · harmful reroutes {r.harmful_reroute_rate_pct}% · backup hedge used {r.backup_hedge_rate_pct}%.
          </p>
          <ul className="bm-caveats">{data.caveats.map((c: string) => <li key={c}>{c}</li>)}</ul>
        </>
      )}
    </div>
  );
}
