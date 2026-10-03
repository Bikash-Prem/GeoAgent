import React from 'react';
import { ArrowRight, ArrowUpRight, Check, Navigation, Ambulance, RefreshCw } from 'lucide-react';
import MapView from '../components/Map';
import { ACTION_LABEL, Ops } from '../lib/ops';
import { DriftBanner } from '../components/LiveBits';

const STEPS = ['DETECT', 'DIAGNOSE', 'PREDICT', 'SIMULATE', 'RECOMMEND', 'APPROVE'];

const MODULES = [
  { href: '#/response', img: '/images/ambulance.jpg', alt: 'Ambulance on a city street', tone: 'photo', title: 'Ground response', text: 'Dispatch the right unit to the right hospital, with routed ETAs and the coverage cost shown up front.' },
  { href: '#/response', img: '/images/corridor.svg', alt: 'Traffic lights turned green along a road', tone: 'mint', title: 'Green corridor', text: 'Turn every signal on the recommended route green and see the waiting time it removes.' },
  { href: '#/response', img: '/images/hospital.svg', alt: 'Hospital with an ambulance arriving', tone: 'blue', title: 'Hospital network', text: 'Live bed and ICU load from each hospital desk, pre-alerts the ER can acknowledge.' },
  { href: '#/air', img: '/images/air-rescue.svg', alt: 'Helicopter over mountains', tone: 'olive', title: 'Mountain air rescue', text: 'When roads run out: aircraft, landing zone, weather limits and fuel range in one call.' },
  { href: '#/fleet', img: '/images/coverage.svg', alt: 'Coverage grid map', tone: 'paper', title: 'Coverage guard', text: 'See which neighbourhoods lose a fast response before you commit another unit.' },
];

export default function Home({ ops }: { ops: Ops }) {
  const { rec, focus, incidents, vehicles, loading, status } = ops;
  const routes = rec?.routes || [];
  const recommendedId = rec?.recommended_route_id || routes[0]?.id;
  const recommended = routes.find((r) => r.id === recommendedId) || routes[0];
  const eta = rec ? rec.current_eta_min.toFixed(1) : '—';
  const altEta = recommended?.eta_min?.toFixed(1) || '—';
  const saved = rec && recommended ? Math.max(0, rec.current_eta_min - recommended.eta_min).toFixed(1) : '—';
  const confidence = rec ? Math.round(rec.confidence * 100) : 0;
  const cause = rec?.cause || 'Waiting for analysis';
  const actionLabel = ACTION_LABEL[rec?.decision?.recommended_action?.action] || 'Awaiting analysis';
  const trace: [string, string][] = [
    ['Detect', `${incidents.length} active incidents in the registry`],
    ['Diagnose', cause],
    ['Predict', `${eta} min on the current route · ${altEta} min recommended`],
    ['Recommend', actionLabel],
  ];

  return (
    <>
      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">EMERGENCY / DECISIONS / IMPACT</div>
          <div className="blob" />
          <h1 className="display hero-title">Spot it.<br />Explain it.<br /><span className="g">Decide it.</span></h1>
          <p className="lede">A practical place to run emergency response, compare real options, and stop treating dispatch like something you only watch.</p>
          <div className="cta-row">
            <button className="pill dark" onClick={ops.analyze} disabled={loading}>{loading ? 'Analyzing…' : 'Run analysis'} <ArrowRight size={16} /></button>
            <a className="pill light" href="#/command">Open live command <ArrowUpRight size={15} /></a>
          </div>
        </div>
        <div className="hero-map">
          <MapView focus={focus} vehicles={vehicles} incidents={incidents} routes={routes} recommendedId={recommendedId} hospitals={ops.hospitals} corridor={ops.corridor} />
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
              <div><small>Unit</small><b>{focus.name}</b></div>
              <div><small>Speed</small><b>{Math.round(focus.speed_kmh)} km/h</b></div>
              <div><small>ETA</small><b className="brick">{eta} min</b></div>
            </div>
          </div>
        </div>
      </section>

      <div className="ticker" aria-hidden="true">
        <div className="ticker-track">{[...STEPS, ...STEPS, ...STEPS, ...STEPS].map((s, i) => <span key={i}>{s}<em>|</em></span>)}</div>
      </div>

      <section className="manifesto" id="why">
        <div className="deco circle" /><div className="deco square" />
        <div className="man-copy">
          <div className="eyebrow">THE MANIFESTO</div>
          <h2 className="display big">You don't need another map pin.<br /><span className="g">You need a decision.</span></h2>
          <p className="small-note">Compare actions, not just routes.</p>
        </div>
        <div className="collage">
          <article className="tile blue"><small>Fleet</small><h3>{vehicles.filter((v) => v.status === 'available').length}<span> ready</span></h3><p>{vehicles.filter((v) => v.status === 'active').length} on mission · {vehicles.length} total</p></article>
          <article className="tile dark"><small>{focus.name}</small><h3>{eta}<span> min</span></h3><p>current ETA to {focus.hospital || 'hospital'}</p></article>
          <article className="tile brick"><small>Registry</small><h3>{incidents.length}<span> incidents</span></h3><p>{incidents.filter((i) => i.severity === 'high').length} high severity</p></article>
          <article className="tile sage"><small>Delay</small><h3>{rec ? `+${rec.delay_min.toFixed(1)}` : '—'}<span> min</span></h3><p>vs free-flow · {ops.latencyMs != null ? `${ops.latencyMs} ms analysis` : 'measuring'}</p></article>
        </div>
      </section>

      <section className="decide" id="decide">
        <DriftBanner ops={ops} />
        <div className="section-head">
          <div>
            <div className="eyebrow">DECIDE</div>
            <h2 className="display big">Decide your<br /><span className="g">way in.</span></h2>
          </div>
          <span className="aside-note">Evidence first. Human final.</span>
        </div>
        <div className="duo">
          <article className="card mint">
            <div className="card-top"><small>DIAGNOSE</small><span className="conf">{confidence}% confidence</span></div>
            <h3 className="display card-title">Understand <span className="g">why.</span></h3>
            <p className="cause">{cause}</p>
            <ul className="evidence">{(rec?.evidence || []).map((x, i) => <li key={i}><Check size={14} />{x}</li>)}</ul>
            <div className="card-foot">
              <span>GeoAgent · Evidence-grounded</span>
              <button className="round" onClick={ops.analyze} disabled={loading} aria-label="Refresh analysis"><RefreshCw size={15} className={loading ? 'spin' : ''} /></button>
            </div>
          </article>
          <article className="card beige">
            <span className="deco-x">✕</span>
            <div className="card-top"><small>DECIDE</small><span className="conf alt">{actionLabel}</span></div>
            <h3 className="display card-title">Choose with <span className="g">proof.</span></h3>
            <div className="rec-line"><span>{recommended?.name || 'Alternative 1'}</span><strong>{altEta} min</strong><em>↓ {saved} min</em></div>
            <p className="rec-note">{rec?.decision?.reasoning || 'Run an analysis to see the evidence-based recommendation.'}</p>
            <div className="cta-row">
              <button className="pill dark sm" disabled={loading || !rec?.decision_id || status !== 'pending'} onClick={() => ops.approveDecision(true)}>
                <Navigation size={14} /> {status === 'pending' ? 'Approve recommendation' : status === 'approved' ? 'Approved' : 'Rejected'}
              </button>
              <button className="pill light sm" disabled={loading || !rec?.backup_vehicle_id} onClick={() => ops.act('dispatch_backup')}>
                <Ambulance size={14} /> Dispatch {rec?.backup_vehicle_id || 'backup'}{rec?.backup_eta_min != null && <span className="mini"> · {rec.backup_eta_min.toFixed(1)}m</span>}
              </button>
            </div>
          </article>
        </div>
      </section>

      <section className="platform" id="platform">
        <div className="section-head">
          <div>
            <div className="eyebrow">ONE PLATFORM</div>
            <h2 className="display big">From the road<br /><span className="g">to the rescue.</span></h2>
          </div>
          <span className="aside-note">Ground, hospital and air on the same live picture.</span>
        </div>
        <div className="module-grid">
          {MODULES.map((m, i) => (
            <a key={m.title} href={m.href} className={`module ${m.tone} ${i === 0 ? 'wide' : ''}`}>
              <figure><img src={m.img} alt={m.alt} loading="lazy" /></figure>
              <div className="module-copy">
                <h3>{m.title}</h3>
                <p>{m.text}</p>
                <span className="module-go">Open <ArrowUpRight size={14} /></span>
              </div>
            </a>
          ))}
        </div>
      </section>

      <section className="trace" id="trace">
        <div className="trace-card">
          <small>FEATURED TRACE</small>
          <small className="sub">DETECT · DIAGNOSE · PREDICT · RECOMMEND</small>
          <h2 className="display mid">See how the<br />decision<br /><span className="g">comes together.</span></h2>
          <a className="link" href="#/evidence">Open the decision trace <ArrowRight size={14} /></a>
        </div>
        <div className="trace-panel">
          {trace.map(([a, b], i) => (
            <div className="trace-row" key={a}>
              <span className="num">{i + 1}</span>
              <div><b>{a}</b><p>{b}</p></div>
              <em>{i === 3 ? (status === 'pending' ? 'Ready' : status) : 'Complete'}</em>
            </div>
          ))}
          <div className="chips"><span>Human-in-the-loop</span><span>Audit trail</span><span>Restricted tools</span></div>
        </div>
      </section>

      <section className="closer">
        <div className="deco circle" /><span className="deco-x big-x">✕</span>
        <div className="eyebrow center">GEOAGENTIC</div>
        <h2 className="display huge">Stop guessing.<br /><span className="g">Start deciding.</span></h2>
        <div className="cta-row center">
          <button className="pill dark" disabled={!rec?.decision_id || status !== 'pending'} onClick={() => ops.approveDecision(true)}>Approve recommendation <ArrowRight size={16} /></button>
          <a className="pill light" href="#/whatif">Try a what-if <ArrowUpRight size={15} /></a>
        </div>
      </section>
    </>
  );
}
