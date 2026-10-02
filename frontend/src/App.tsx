import React, { useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, Check, Navigation, Ambulance, RefreshCw } from 'lucide-react';
import MapView from './components/Map';
import { getJSON, postJSON, wsUrl } from './lib/api';

type RouteT = {
  id: string;
  name: string;
  eta_min: number;
  delay_min: number;
  uncertainty_min: number;
  risk: string;
  distance_km: number;
  points: any[];
  explanation: string;
};
type Rec = {
  vehicle_id: string;
  current_eta_min: number;
  delay_min: number;
  cause: string;
  confidence: number;
  evidence: string[];
  routes: RouteT[];
  backup_vehicle_id: string | null;
  backup_eta_min: number | null;
};

const fallbackVehicle = {
  id: 'AMB-07',
  name: 'AMB-07',
  status: 'active',
  lat: 12.9712,
  lon: 77.594,
  speed_kmh: 62,
  heading: 72,
  hospital: 'City General Hospital',
};

const STEPS = ['DETECT', 'DIAGNOSE', 'PREDICT', 'SIMULATE', 'RECOMMEND', 'APPROVE'];

const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

export default function App() {
  const [vehicles, setVehicles] = useState<any[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [selected] = useState('AMB-07');
  const [rec, setRec] = useState<Rec | null>(null);
  const [live, setLive] = useState(false);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [apiOffline, setApiOffline] = useState(false);

  useEffect(() => {
    Promise.all([getJSON('/api/vehicles'), getJSON('/api/incidents')])
      .then(([v, i]) => {
        setVehicles(v);
        setIncidents(i);
        setApiOffline(false);
      })
      .catch(() => {
        setVehicles([fallbackVehicle]);
        setIncidents([]);
        setApiOffline(true);
      });
  }, []);

  useEffect(() => {
    const ws = new WebSocket(wsUrl('/ws/telemetry'));
    ws.onopen = () => setLive(true);
    ws.onclose = () => setLive(false);
    ws.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d.vehicle_id === 'AMB-07') setVehicles((v) => v.map((x) => (x.id === 'AMB-07' ? { ...x, ...d } : x)));
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(''), 6000);
    return () => clearTimeout(t);
  }, [notice]);

  const vehicle = vehicles.find((v) => v.id === selected) || fallbackVehicle;

  const analyze = async () => {
    setLoading(true);
    try {
      setRec(await getJSON(`/api/recommendations/${selected}`));
      setNotice('GeoAgent analysis complete · evidence refreshed');
    } catch (e) {
      setNotice('API unavailable · showing the last known scenario');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    analyze();
  }, [selected]);

  const act = async (action: string, route_id?: string) => {
    try {
      await postJSON(`/api/vehicles/${selected}/actions`, { action, route_id });
      setNotice(
        action === 'reroute'
          ? 'Reroute approval recorded in audit trail'
          : action === 'dispatch_backup'
          ? 'Backup dispatch request recorded'
          : 'Incident acknowledged'
      );
    } catch (e) {
      setNotice('Action could not be recorded · check the API connection');
    }
  };

  const routes = rec?.routes || [];
  const recommended = routes.find((r) => r.id === 'route-2') || routes[1];
  const eta = rec ? rec.current_eta_min.toFixed(1) : '17.2';
  const altEta = recommended?.eta_min?.toFixed(1) || '11.4';
  const saved = rec && recommended ? Math.max(0, rec.current_eta_min - recommended.eta_min).toFixed(1) : '5.8';
  const confidence = rec ? Math.round(rec.confidence * 100) : 82;
  const incidentCount = incidents.length || 3;
  const evidence = rec?.evidence || ['Traffic speed dropped 68%', 'Incident detected 220m ahead', 'Lane closure reported'];
  const cause = rec?.cause || 'Accident on Main St.';

  const trace: [string, string][] = [
    ['Detect', 'Route deviation identified'],
    ['Diagnose', cause],
    ['Predict', `${eta} min current ETA`],
    ['Recommend', `${altEta} min alternative`],
  ];

  return (
    <div className="page">
      {/* ───── Header ───── */}
      <header className="nav">
        <a className="wordmark" href="#top" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>
          GEO<i>·</i>AGENTIC
        </a>
        <nav className="nav-links">
          <button onClick={() => go('why')}>Why</button>
          <button onClick={() => go('decide')}>Decide</button>
          <button onClick={() => go('routes')}>Routes</button>
          <button onClick={() => go('trace')}>Trace</button>
        </nav>
        <div className="nav-right">
          <span className={`status-pill ${live ? 'on' : ''}`}>
            <b />
            {live ? 'Live telemetry' : 'Replay mode'}
          </span>
          <button className="pill dark sm" onClick={() => go('decide')}>
            Open command <ArrowRight size={14} />
          </button>
        </div>
      </header>

      {notice && (
        <div className={`toast ${apiOffline ? 'warn' : ''}`} role="status">
          <Check size={15} /> {apiOffline ? 'API unavailable · replaying the seeded command scenario' : notice}
          <button onClick={() => setNotice('')} aria-label="Dismiss">×</button>
        </div>
      )}

      {/* ───── Hero ───── */}
      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">EMERGENCY / DECISIONS / IMPACT</div>
          <div className="blob" />
          <h1 className="display hero-title">
            Spot it.
            <br />
            Explain it.
            <br />
            <span className="g">Decide it.</span>
          </h1>
          <p className="lede">
            A practical place to run emergency response, compare real options, and stop treating dispatch like something you only watch.
          </p>
          <div className="cta-row">
            <button className="pill dark" onClick={analyze} disabled={loading}>
              {loading ? 'Analyzing…' : 'Run analysis'} <ArrowRight size={16} />
            </button>
            <button className="pill light" onClick={() => act('acknowledge')}>
              Acknowledge incident <ArrowUpRight size={15} />
            </button>
          </div>
        </div>

        <div className="hero-map">
          <MapView vehicle={vehicle} incidents={incidents} routes={routes} />
          <div className="legend">
            <span><i style={{ background: '#67a6c2' }} />Planned</span>
            <span><i style={{ background: '#b65e5a' }} />Delayed</span>
            <span><i style={{ background: '#6a9a63' }} />Recommended</span>
          </div>
          <div className="float-card">
            <span className="dot" />
            <h4>Ready to respond?</h4>
            <p>Everything starts with one real signal.</p>
            <div className="readout">
              <div><small>Unit</small><b>{vehicle.name}</b></div>
              <div><small>Speed</small><b>{Math.round(vehicle.speed_kmh)} km/h</b></div>
              <div><small>ETA</small><b className="brick">{eta} min</b></div>
            </div>
          </div>
        </div>
      </section>

      {/* ───── Ticker ───── */}
      <div className="ticker" aria-hidden="true">
        <div className="ticker-track">
          {[...STEPS, ...STEPS, ...STEPS, ...STEPS].map((s, i) => (
            <span key={i}>{s}<em>|</em></span>
          ))}
        </div>
      </div>

      {/* ───── Manifesto ───── */}
      <section className="manifesto" id="why">
        <div className="deco circle" />
        <div className="deco square" />
        <div className="man-copy">
          <div className="eyebrow">THE MANIFESTO</div>
          <h2 className="display big">
            You don't need another map pin.
            <br />
            <span className="g">You need a decision.</span>
          </h2>
          <p className="small-note">Compare actions, not just routes.</p>
        </div>
        <div className="collage">
          <article className="tile blue">
            <small>01</small>
            <h3>Units</h3>
            <p>1 active · 2 available</p>
          </article>
          <article className="tile dark">
            <small>02</small>
            <h3>{eta}<span> min</span></h3>
            <p>{vehicle.name} · current ETA</p>
          </article>
          <article className="tile brick">
            <small>03</small>
            <h3>{incidentCount}<span> incidents</span></h3>
            <p>1 high severity</p>
          </article>
          <article className="tile sage">
            <small>04</small>
            <h3>{rec ? `+${rec.delay_min.toFixed(1)}` : '—'}<span> min</span></h3>
            <p>Current delay · latency 1.8s</p>
          </article>
        </div>
      </section>

      {/* ───── Decide ───── */}
      <section className="decide" id="decide">
        <div className="section-head">
          <div>
            <div className="eyebrow">DECIDE</div>
            <h2 className="display big">
              Decide your
              <br />
              <span className="g">way in.</span>
            </h2>
          </div>
          <span className="aside-note">Evidence first. Human final.</span>
        </div>

        <div className="duo">
          <article className="card mint">
            <div className="card-top">
              <small>01 / DIAGNOSE</small>
              <span className="conf">{confidence}% confidence</span>
            </div>
            <h3 className="display card-title">
              Understand <span className="g">why.</span>
            </h3>
            <p className="cause">{cause}</p>
            <ul className="evidence">
              {evidence.map((x, i) => (
                <li key={i}><Check size={14} />{x}</li>
              ))}
            </ul>
            <div className="card-foot">
              <span>GeoAgent · Evidence-grounded</span>
              <button className="round" onClick={analyze} disabled={loading} aria-label="Refresh analysis">
                <RefreshCw size={15} className={loading ? 'spin' : ''} />
              </button>
            </div>
          </article>

          <article className="card beige">
            <span className="deco-x">✕</span>
            <div className="card-top">
              <small>02 / DECIDE</small>
              <span className="conf alt">Reroute current unit</span>
            </div>
            <h3 className="display card-title">
              Choose with <span className="g">proof.</span>
            </h3>
            <div className="rec-line">
              <span>{recommended?.name || 'Alternative 1'}</span>
              <strong>{altEta} min</strong>
              <em>↓ {saved} min</em>
            </div>
            <p className="rec-note">The alternative avoids the incident corridor and carries lower predicted risk.</p>
            <div className="cta-row">
              <button className="pill dark sm" disabled={loading} onClick={() => act('reroute', recommended?.id)}>
                <Navigation size={14} /> Approve reroute
              </button>
              <button className="pill light sm" disabled={loading} onClick={() => act('dispatch_backup')}>
                <Ambulance size={14} /> Dispatch {rec?.backup_vehicle_id || 'AMB-12'}
                {rec?.backup_eta_min != null && <span className="mini"> · {rec.backup_eta_min.toFixed(1)}m</span>}
              </button>
            </div>
          </article>
        </div>
      </section>

      {/* ───── Routes ───── */}
      <section className="routes" id="routes">
        <div className="eyebrow">ROUTE COMPARISON / ETA · DELAY · UNCERTAINTY · RISK</div>
        <div className="route-grid">
          {routes.length === 0 && <div className="route-empty">Waiting for GeoAgent to generate routes…</div>}
          {routes.map((r, i) => (
            <article key={r.id} className={`route-card ${i === 1 ? 'picked' : ''}`}>
              <div className="route-top">
                <span className={`rdot r${i}`} />
                <b>{r.name}</b>
                {i === 1 && <em>Recommended</em>}
              </div>
              <div className="route-eta">{r.eta_min.toFixed(1)}<span> min</span></div>
              <dl>
                <div><dt>Δ Delay</dt><dd className={r.delay_min < 0 ? 'good' : 'bad'}>{r.delay_min > 0 ? '+' : ''}{r.delay_min.toFixed(1)}m</dd></div>
                <div><dt>Uncertainty</dt><dd>±{r.uncertainty_min.toFixed(1)}m</dd></div>
                <div><dt>Distance</dt><dd>{r.distance_km?.toFixed?.(1) ?? '—'} km</dd></div>
                <div><dt>Risk</dt><dd><span className={`risk ${r.risk}`}>{r.risk}</span></dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>

      {/* ───── Trace ───── */}
      <section className="trace" id="trace">
        <div className="trace-card">
          <small>FEATURED TRACE</small>
          <small className="sub">DETECT · DIAGNOSE · PREDICT · RECOMMEND</small>
          <h2 className="display mid">
            See how the
            <br />
            decision
            <br />
            <span className="g">comes together.</span>
          </h2>
          <button className="link" onClick={() => go('decide')}>Open the decision <ArrowRight size={14} /></button>
        </div>
        <div className="trace-panel">
          {trace.map(([a, b], i) => (
            <div className="trace-row" key={a}>
              <span className="num">{i + 1}</span>
              <div>
                <b>{a}</b>
                <p>{b}</p>
              </div>
              <em>{i === 3 ? 'Ready' : 'Complete'}</em>
            </div>
          ))}
          <div className="chips">
            <span>Human-in-the-loop</span>
            <span>Audit trail</span>
            <span>Restricted tools</span>
          </div>
        </div>
      </section>

      {/* ───── Closing CTA ───── */}
      <section className="closer">
        <div className="deco circle" />
        <span className="deco-x big-x">✕</span>
        <div className="eyebrow center">GEOAGENTIC</div>
        <h2 className="display huge">
          Stop guessing.
          <br />
          <span className="g">Start deciding.</span>
        </h2>
        <button className="pill dark" onClick={() => act('reroute', recommended?.id)}>
          Approve reroute <ArrowRight size={16} />
        </button>
      </section>

      {/* ───── Footer ───── */}
      <footer className="foot">
        <div className="foot-grid">
          <div>
            <div className="wordmark">GEO<i>·</i>AGENTIC</div>
            <h3 className="display foot-tag">Decide faster.</h3>
            <p>Observe, predict and compare responses with evidence, with a dispatcher always making the final call.</p>
          </div>
          <nav className="foot-links">
            <button onClick={() => go('why')}>Why</button>
            <button onClick={() => go('decide')}>Decide</button>
            <button onClick={() => go('routes')}>Routes</button>
            <button onClick={() => go('trace')}>Trace</button>
          </nav>
          <div className="foot-status">
            <small>SYSTEM STATUS</small>
            <h4>{apiOffline ? 'Replay mode.' : 'All systems operational.'}<br />No noise.</h4>
            <div className="pill-input">
              <span>{live ? 'Live telemetry connected' : 'Telemetry replaying'}</span>
              <button onClick={() => act('acknowledge')} aria-label="Acknowledge incident"><ArrowRight size={15} /></button>
            </div>
          </div>
        </div>
        <div className="foot-bottom">
          <span>© 2026 GeoAgentic · v2.0 control plane</span>
          <span>Decision support, not an autonomous authority.</span>
        </div>
      </footer>
    </div>
  );
}
