import React, { useEffect, useState } from 'react';
import { Truck } from 'lucide-react';
import MapView from '../components/Map';
import { PageHead } from '../components/Shell';
import { getJSON } from '../lib/api';
import { Ops } from '../lib/ops';

export default function Fleet({ ops }: { ops: Ops }) {
  const [target, setTarget] = useState(10);
  const [cov, setCov] = useState<any>(null);
  const statuses = ops.vehicles.map((v) => v.status).join();
  useEffect(() => {
    const t = setTimeout(() => getJSON(`/api/v1/coverage?target_min=${target}`).then(setCov).catch(() => setCov(null)), 200);
    return () => clearTimeout(t);
  }, [target, statuses, ops.incidents.length]);

  return (
    <>
      <PageHead eyebrow="FLEET & COVERAGE" title="Every dispatch" accent="leaves a gap." image="/images/coverage.svg" alt="Map grid showing reachable areas"
        lede="Coverage is the share of the city a free ambulance can still reach in time, on today's roads. Check it before you spend a backup unit." />

      <section className="ops-section">
        <div className="fleet-grid">
          {ops.vehicles.map((v) => (
            <article key={v.id} className={`unit ${v.status}`}>
              <div className="unit-top"><Truck size={18} /><span className={`ustat ${v.status}`}>{v.status === 'available' ? 'ready' : 'on mission'}</span></div>
              <h3>{v.name}</h3>
              <dl><div><dt>Speed</dt><dd>{Math.round(v.speed_kmh)} km/h</dd></div><div><dt>Heading to</dt><dd>{v.hospital || '—'}</dd></div><div><dt>Position</dt><dd>{v.lat.toFixed(4)}, {v.lon.toFixed(4)}</dd></div></dl>
            </article>
          ))}
        </div>

        <div className="cov-layout">
          <div className="map-panel">
            <MapView className="map tall" focus={ops.focus} vehicles={ops.vehicles} incidents={ops.incidents} hospitals={ops.hospitals} cells={cov?.cells || []} zoom={15} scrollZoom />
            <div className="legend"><span><i style={{ background: '#6a9a63' }} />Fast</span><span><i style={{ background: '#a9c99c' }} />In target</span><span><i style={{ background: '#e3a69f' }} />Too slow</span></div>
          </div>
          <aside className="side-stack">
            <div className="panel big-number">
              <small className="kicker">COVERED WITHIN {target} MIN</small>
              <div className="num-xl">{cov ? cov.coverage_pct : '—'}<span>%</span></div>
              <p className="muted">Mean reach {cov?.mean_eta_min ?? '—'} min · worst {cov?.worst_eta_min ?? '—'} min · {cov?.available_units?.length ?? 0} units ready</p>
              <label className="range">Response target <b>{target} min</b><input type="range" min={5} max={15} value={target} onChange={(e) => setTarget(Number(e.target.value))} /></label>
            </div>
            <div className="panel">
              <div className="panel-head"><h3>If we commit…</h3></div>
              {(cov?.impact || []).length === 0 && <p className="muted">No ready units. Coverage cannot drop further; close an assignment to restore it.</p>}
              <ul className="impact">
                {(cov?.impact || []).map((x: any) => (
                  <li key={x.vehicle_id}>
                    <b>{x.vehicle_id}</b>
                    <div className="impact-bar"><i style={{ width: `${x.coverage_after_pct}%` }} /></div>
                    <span>{x.coverage_after_pct}% left <em>−{x.drop_pct}</em></span>
                    <small>worst reach becomes {x.worst_eta_after_min ?? '—'} min</small>
                  </li>
                ))}
              </ul>
              <p className="fine">The dispatch ranking uses this as a tie-breaker, so equal ETAs favour the unit whose absence hurts least.</p>
            </div>
          </aside>
        </div>
      </section>
    </>
  );
}
