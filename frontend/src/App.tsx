import React, { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, ArrowRight, Check, Clock3, GitCompare, MapPinned, Play, RotateCcw, Shield, Truck, X, Radio, Volume2, VolumeX, Siren, Hospital, TrafficCone, Zap, Plane, Mountain, Wind, Navigation, Gauge, Fuel, CloudSun } from 'lucide-react';
import MapView from './components/Map';
import AirRescueMap from './components/AirRescueMap';
import { getJSON, postJSON, wsUrl } from './lib/api';

type Route = { id: string; name: string; eta_min: number; delay_min: number; uncertainty_min: number; risk: string; distance_km: number; points: { lat: number; lon: number }[]; explanation: string };
type Rec = { decision_id: string; reasoning: string; vehicle_id: string; current_eta_min: number; delay_min: number; cause: string; confidence: number; evidence: string[]; routes: Route[]; backup_vehicle_id: string | null; backup_eta_min: number | null; decision?: any };
type View = 'command' | 'incident' | 'decision' | 'whatif' | 'fleet' | 'simulation' | 'analytics' | 'audit' | 'air';

const views: { id: View; label: string }[] = [
  { id: 'command', label: 'Command Center' }, { id: 'incident', label: 'Situation Room' }, { id: 'decision', label: 'Decision Studio' },
  { id: 'whatif', label: 'What-If Lab' }, { id: 'fleet', label: 'Fleet Intelligence' }, { id: 'air', label: 'Mountain Air Rescue' }, { id: 'simulation', label: 'Replay' }, { id: 'analytics', label: 'Analytics' }, { id: 'audit', label: 'Audit' },
];

function Metric({ label, value, note }: { label: string; value: string | number; note?: string }) { return <div className="metric"><small>{label}</small><strong>{value}</strong>{note && <span>{note}</span>}</div>; }
function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: string }) { return <span className={`badge ${tone}`}>{children}</span>; }

export default function App() {
  const [view, setView] = useState<View>('command');
  const [vehicles, setVehicles] = useState<any[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [rec, setRec] = useState<Rec | null>(null);
  const [snapshot, setSnapshot] = useState<any>(null);
  const [selectedRoute, setSelectedRoute] = useState<string>('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [simulation, setSimulation] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [hospitals, setHospitals] = useState<any[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  const [corridor, setCorridor] = useState<any>(null);
  const [dispatchPlan, setDispatchPlan] = useState<any>(null);
  const [voiceOn, setVoiceOn] = useState(true);
  const [lastVoice, setLastVoice] = useState<Record<string,number>>({});
  const [airRescue, setAirRescue] = useState<any>(null);
  const [airRegion, setAirRegion] = useState('himachal');

  const selectedVehicle = useMemo(() => vehicles.find(v => v.id === 'AMB-07') || vehicles[0], [vehicles]);

  const load = async () => {
    setLoading(true);
    try {
      const fetchOne = async <T,>(path: string) => {
        try { return await getJSON(path) as T; }
        catch (e: any) { throw new Error(`${path}: ${e?.message || 'request failed'}`); }
      };
      const [v, i, h, sig, cor, plan, air] = await Promise.all([
        fetchOne<any[]>('/api/vehicles'),
        fetchOne<any[]>('/api/incidents'),
        fetchOne<any>('/api/v1/hospitals'),
        fetchOne<any>('/api/v1/signals'),
        fetchOne<any>('/api/v1/corridor'),
        fetchOne<any>('/api/v1/dispatch/plan'),
        fetchOne<any>('/api/v1/air-rescue/plan?region=' + airRegion),
      ]);
      setVehicles(v); setIncidents(i); setHospitals(h.hospitals || []); setSignals(sig.signals || []); setCorridor(cor.active ? cor : null); setDispatchPlan(plan); setAirRescue(air);
      const analysis = await postJSON('/api/v1/decisions/analyze', { vehicle_id: v.find((x: any) => x.id === 'AMB-07')?.id || v[0]?.id || 'AMB-07' });
      setRec(toRec(analysis));
      setSelectedRoute(analysis.recommended_action?.route_id || analysis.alternatives?.[0]?.route_id || '');
      setNotice('Situation analyzed from the current local data state.');
    } catch (e: any) {
      setNotice(`Backend unavailable: ${e?.message || 'check localhost:8000'}`);
    } finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, []);
  useEffect(() => { getJSON('/api/v1/air-rescue/plan?region=' + airRegion).then(setAirRescue).catch(() => undefined); }, [airRegion]);
  useEffect(() => {
    const socket = new WebSocket(wsUrl('/ws/twin'));
    socket.onmessage = e => { try { const d = JSON.parse(e.data); if (d.type === 'TWIN_SNAPSHOT_UPDATED') setSnapshot(d.snapshot); } catch {} };
    return () => socket.close();
  }, []);
  useEffect(() => { getJSON('/api/audit').then(setAudit).catch(() => undefined); }, [notice]);

  const toRec = (d: any): Rec => {
    const all = [d.recommended_action, ...(d.alternatives || [])];
    const routes = all.filter((a: any) => a.route_id).map((a: any) => ({ id: a.route_id, name: a.route_id, eta_min: a.expected_eta_minutes, delay_min: a.delay_min || 0, uncertainty_min: a.eta_uncertainty?.upper - a.eta_uncertainty?.lower || 0, risk: String(a.risk?.level || 'unknown').toLowerCase(), distance_km: a.distance_km || 0, points: a.points || [], explanation: a.route_explanation || 'Evaluated by the decision engine.' }));
    return { decision_id: d.decision_id, reasoning: d.reasoning, vehicle_id: d.situation.vehicle_id, current_eta_min: routes[0]?.eta_min || d.expected_eta_minutes, delay_min: routes[0]?.delay_min || 0, cause: d.situation.diagnosis, confidence: d.situation.diagnosis_confidence, evidence: d.evidence.map((x: any) => x.explanation), routes, backup_vehicle_id: all.find((a: any) => a.action === 'dispatch_backup')?.vehicle_id || null, backup_eta_min: all.find((a: any) => a.action === 'dispatch_backup')?.expected_eta_minutes || null, decision: d };
  };

  const approve = async (approved: boolean, actionId?: string) => {
    if (!rec) return;
    try {
      await postJSON(`/api/v1/decisions/${rec.decision_id}/${approved ? 'approve' : 'reject'}`, { approved, selected_action_id: actionId, actor_id: 'dispatcher', comment: approved ? 'Approved from local command center' : 'Rejected from local command center' });
      setNotice(approved ? 'Decision approved and written to the audit trail.' : 'Decision rejected and written to the audit trail.');
      setView('audit');
    } catch (e: any) { setNotice(`Approval failed: ${e?.message || 'API error'}`); }
  };

  const runWhatIf = async (scenario: string) => {
    try { setSimulation(await postJSON('/api/v1/simulation/run', { scenario, seed: 7 })); setView('whatif'); } catch (e: any) { setNotice(`Simulation failed: ${e?.message || 'API error'}`); }
  };

  const routeList = rec?.routes || [];
  const activeRoute = routeList.find(r => r.id === selectedRoute) || routeList[0];
  const fleetAvailable = vehicles.filter(v => v.status === 'available').length;
  const currentSnapshot = snapshot?.decision ? toRec(snapshot.decision) : rec;
  const speak = (message:string) => { if(!voiceOn || !('speechSynthesis' in window)) return; const now=Date.now(); if(now-(lastVoice[message]||0)<30000) return; window.speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(message); u.rate=.92; u.pitch=.88; u.volume=.9; window.speechSynthesis.speak(u); setLastVoice(x=>({...x,[message]:now})); };
  const activateCorridor = async () => { try { const d=await postJSON('/api/v1/corridor/activate',{vehicle_id:selectedVehicle?.id||'AMB-07'}); setCorridor(d); setSignals(d.signals||[]); setNotice('Green corridor activated. Signal override simulation is live.'); speak(`Green corridor activated for ${selectedVehicle?.name||'the ambulance'}.`); } catch(e:any){setNotice(e?.message||'Corridor activation failed');} };
  const executeDispatch = async () => { try { const d=await postJSON('/api/v1/dispatch/execute',{}); setDispatchPlan(d); setNotice(`AI dispatch executed: ${d.ambulance.name} → ${d.hospital.name}`); speak(`Dispatch executed. ${d.ambulance.name} is responding to the emergency.`); } catch(e:any){setNotice(e?.message||'Dispatch failed');} };
  const executeAirRescue = async () => { try { const d=await postJSON('/api/v1/air-rescue/execute',{region:airRegion}); setAirRescue(d); setNotice(`Air rescue activated: ${d.air_ambulance.name} → ${d.incident.name}`); speak(`Mountain air rescue activated for ${d.incident.name}. Flight ETA ${Math.round(d.flight_eta_min)} minutes.`); } catch(e:any){ setNotice(e?.message||'Air rescue dispatch failed'); } };
  const alertHospital = async (number:number) => { if(!dispatchPlan) return; const a=await postJSON('/api/v1/hospitals/alert',{hospital_id:dispatchPlan.hospital.id,vehicle_id:dispatchPlan.ambulance.id,eta_min:dispatchPlan.response_eta_min,incident:dispatchPlan.incident,alert_number:number}); setNotice(`Hospital alert #${number} sent to ${a.hospital}.`); speak(`Hospital alert ${number} sent to ${a.hospital}. ETA ${Math.round(a.eta_min)} minutes.`); };
  useEffect(()=>{ if(rec) speak(`Emergency analysis ready. Current diagnosis: ${rec.cause}.`); },[rec?.decision_id]);
  useEffect(()=>{ if(!dispatchPlan) return; const timer=setInterval(()=>void alertHospital(2),300000); return()=>clearInterval(timer); },[dispatchPlan?.ambulance?.id]);

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">G</span><div><b>GEOAGENTIC</b><small>Emergency Decision Intelligence</small></div></div>
      <div className="system-state"><span className="live-dot" /> LIVE MUMBAI CONTROL PLANE <span className="divider" /> {loading ? 'SYNCING' : 'READY'} <button className="voice-toggle" onClick={()=>setVoiceOn(x=>!x)}>{voiceOn?<Volume2 size={14}/>:<VolumeX size={14}/>} {voiceOn?'VOICE ON':'VOICE OFF'}</button></div>
    </header>
    <nav className="nav-tabs">{views.map(v => <button key={v.id} className={view === v.id ? 'active' : ''} onClick={() => setView(v.id)}>{v.label}</button>)}<button className="refresh" onClick={() => void load()}><RotateCcw size={15} /> Refresh</button></nav>
    {notice && <div className="notice">{notice}</div>}

    <main className="main">
      {view === 'command' && <>
        <section className="home-hero"><div className="home-hero-copy"><p className="eyebrow">GEOAGENTIC · EMERGENCY DECISION INTELLIGENCE</p><h1>From the road<br /><em>to the rescue.</em></h1><p className="lead">One operational intelligence layer for urban ambulances, green corridors, hospitals and high-altitude air rescue.</p><div className="home-hero-actions"><button className="primary" onClick={() => setView('decision')}>Open command center <ArrowRight size={16} /></button><button className="secondary" onClick={() => setView('air')}><Plane size={16} /> Mountain air rescue</button></div><div className="home-hero-status"><Badge tone="good">LIVE CONTROL PLANE</Badge><span>Ground + air emergency response</span></div></div><div className="home-hero-image"><img src="/ambulance-hero.png" alt="Emergency ambulance responding through a city intersection"/><div className="hero-image-caption"><span className="live-dot" /> AI dispatch · green corridor · hospital coordination</div></div></section>
        <section className="metrics"><Metric label="ACTIVE UNIT" value={selectedVehicle?.id || '—'} note={selectedVehicle ? `${selectedVehicle.speed_kmh.toFixed?.(0) ?? selectedVehicle.speed_kmh} km/h` : ''} /><Metric label="ACTIVE INCIDENTS" value={incidents.length} note="from incident registry" /><Metric label="AVAILABLE BACKUP" value={fleetAvailable} note="persisted fleet state" /><Metric label="ROUTING SOURCE" value={snapshot?.providers?.find((p: any) => p.name === 'google-routes')?.mode?.toUpperCase() || snapshot?.providers?.find((p: any) => p.name === 'routing')?.mode?.toUpperCase() || 'LOCAL'} note="provider status" /></section>
        <section className="map-grid"><div className="map-card"><div className="section-head"><div><p className="eyebrow">SITUATION MAP · MUMBAI</p><h2>Live operational picture</h2></div><Badge tone="neutral">CARTO DARK MATTER</Badge></div><MapView vehicle={selectedVehicle} vehicles={vehicles} incidents={incidents} routes={routeList} selectedRoute={selectedRoute} onSelectRoute={setSelectedRoute} hospitals={hospitals} signals={signals} corridor={corridor} /></div><aside className="side-card"><p className="eyebrow">CURRENT DIAGNOSIS</p><h2>{rec?.cause || 'Awaiting analysis'}</h2><p>{rec?.reasoning || 'Run an analysis to produce a grounded decision trace.'}</p><div className="evidence-list">{rec?.evidence.map((e, i) => <div key={i}><span>✓</span>{e}</div>)}</div><button className="secondary full" onClick={() => setView('incident')}>Open situation room <ArrowRight size={15} /></button></aside></section>
        <section className="feature-grid"><div className="feature-card corridor-card"><div className="feature-icon"><TrafficCone size={20}/></div><div><p className="eyebrow">SMART GREEN CORRIDOR</p><h3>{corridor?.active?'CORRIDOR ACTIVE':'CORRIDOR STANDBY'}</h3><p>{corridor?.active?`${signals.filter((s:any)=>s.overridden).length} intersections overridden to GREEN.`:'Activate signal priority along the selected emergency route.'}</p></div><button className="primary" onClick={activateCorridor}>{corridor?.active?'Re-activate':'Activate corridor'}</button></div><div className="feature-card"><div className="feature-icon"><Siren size={20}/></div><div><p className="eyebrow">AI VOICE EMERGENCY ASSISTANT</p><h3>{voiceOn?'VOICE ENABLED':'VOICE MUTED'}</h3><p>Browser-native announcements for dispatch, corridor activation, hospital alerts and ETA changes.</p></div><button className="secondary" onClick={()=>speak('GeoAgentic emergency assistant is online.')}>Test voice</button></div></section>
        <section className="air-rescue-teaser"><div className="air-rescue-teaser-copy"><p className="eyebrow">NEW · MOUNTAIN AIR RESCUE</p><h2>When roads disappear, the response plan goes airborne.</h2><p>GeoAgentic evaluates altitude, wind, visibility, terrain risk, landing-zone feasibility, helicopter fuel and trauma-centre readiness before recommending an air ambulance response.</p><div className="air-mini-stats"><span><Mountain size={15}/> {airRescue?.region_name || 'Himalayan regions'}</span><span><Wind size={15}/> {airRescue?.weather?.wind_kmh ?? '—'} km/h</span><span><Gauge size={15}/> {airRescue?.incident?.altitude_m?.toLocaleString?.() ?? '—'} m</span></div></div><button className="primary" onClick={()=>setView('air')}>Open air rescue desk <Plane size={16}/></button></section>
        <section className="three-col"><div className="panel"><div className="section-head"><h3>Hospital readiness</h3><Hospital size={18}/></div>{hospitals.map(h=><div className="hospital-row" key={h.id}><b>{h.name}</b><Badge tone={h.trauma==='READY'?'good':h.trauma==='LIMITED'?'warn':'danger'}>{h.trauma}</Badge><div className="bars"><span style={{width:`${h.icu*100}%`}}/><span style={{width:`${h.er*100}%`}}/><span style={{width:`${h.oxygen*100}%`}}/></div><small>ICU {Math.round(h.icu*100)}% · ER {Math.round(h.er*100)}% · O₂ {Math.round(h.oxygen*100)}%</small></div>)}</div><div className="panel"><div className="section-head"><h3>AI dispatch engine</h3><Zap size={18}/></div>{dispatchPlan&&<><Metric label="NEAREST UNIT" value={dispatchPlan.ambulance.name}/><Metric label="TARGET HOSPITAL" value={dispatchPlan.hospital.name}/><Metric label="RESPONSE ETA" value={`${dispatchPlan.response_eta_min} min`}/><Metric label="SURVIVAL MODEL" value={`${Math.round(dispatchPlan.survival_probability*100)}%`} note="local decision-model simulation"/><Metric label="DISPATCH CONFIDENCE" value={`${Math.round(dispatchPlan.dispatch_confidence*100)}%`}/></>}<button className="primary full" onClick={executeDispatch}>Execute AI Dispatch <Zap size={15}/></button></div><div className="panel"><div className="section-head"><h3>Smart hospital alerts</h3><Radio size={18}/></div><p className="muted">Alert #1 fires on dispatch. Alert #2 is the en-route update after five minutes.</p><div className="alert-stack"><button className="secondary full" onClick={()=>void alertHospital(1)}>Send Alert #1 · Immediate</button><button className="secondary full" onClick={()=>void alertHospital(2)}>Send Alert #2 · &gt; 5 min</button></div></div></section>
      </>}

      {view === 'incident' && <Page title="Emergency Situation Room" eyebrow="WHAT IS HAPPENING?" subtitle="Evidence is separated from diagnosis so the dispatcher can inspect the basis of the decision."><div className="two-col"><section className="panel"><h3>Incident registry</h3>{incidents.map(i => <div className="incident-row" key={i.id}><div><Badge tone={i.severity === 'high' ? 'danger' : 'warn'}>{i.severity}</Badge><b>{i.title}</b><small>{i.kind} · {i.radius_m}m radius · {i.id}</small></div><span>{i.details}</span></div>)}</section><section className="panel"><h3>Diagnosis</h3><div className="big-value">{rec?.cause || '—'}</div><div className="confidence"><span>Confidence</span><b>{rec ? Math.round(rec.confidence * 100) : 0}%</b></div><h4>Evidence</h4>{rec?.evidence.map((e, i) => <div className="evidence-line" key={i}><Check size={15} />{e}</div>)}</section></div><div className="panel timeline"><h3>Decision pipeline</h3>{['Observe','Diagnose','Predict','Simulate','Recommend','Human review'].map((x, i) => <div key={x} className="timeline-step"><span>{i + 1}</span><b>{x}</b><small>{i < 4 ? 'complete' : i === 4 ? 'ready' : 'dispatcher required'}</small></div>)}</div></Page>}

      {view === 'decision' && <Page title="Decision Studio" eyebrow="WHAT CAN WE DO?" subtitle="Compare the actions before committing one to the audit trail."><div className="decision-grid"><section className="panel"><div className="section-head"><div><h3>Candidate routes</h3><p>Provider route geometry + GeoAgentic risk evaluation</p></div><Badge tone="neutral">{routeList.length} candidates</Badge></div>{routeList.map(r => <button key={r.id} onClick={() => setSelectedRoute(r.id)} className={`route-option ${selectedRoute === r.id ? 'selected' : ''}`}><div><b>{r.name}</b><small>{r.explanation}</small></div><strong>{r.eta_min.toFixed(1)}m</strong><Badge tone={r.risk === 'low' ? 'good' : r.risk === 'high' ? 'danger' : 'warn'}>{r.risk}</Badge></button>)}<MapView vehicle={selectedVehicle} vehicles={vehicles} incidents={incidents} routes={routeList} selectedRoute={selectedRoute} onSelectRoute={setSelectedRoute} hospitals={hospitals} signals={signals} corridor={corridor} /></section><section className="panel"><p className="eyebrow">RECOMMENDATION</p><div className="recommendation"><Badge tone="good">{rec?.decision?.recommended_action?.action || '—'}</Badge><div className="big-eta">{rec?.decision?.expected_eta_minutes?.toFixed?.(1) || '—'} <span>min</span></div><p>{rec?.reasoning}</p></div><div className="compare-grid"><Metric label="RISK" value={rec?.decision?.risk?.level || '—'} /><Metric label="UNCERTAINTY" value={rec?.decision?.eta_uncertainty ? `±${((rec.decision.eta_uncertainty.upper - rec.decision.eta_uncertainty.lower) / 2).toFixed(1)}m` : '—'} /><Metric label="BACKUP" value={rec?.backup_vehicle_id || 'none'} /></div><div className="approval"><button className="primary" onClick={() => approve(true, rec?.decision?.recommended_action?.action_id)}>Approve recommendation <Check size={16} /></button><button className="secondary" onClick={() => approve(false)}>Reject <X size={16} /></button></div><button className="link-button" onClick={() => setView('audit')}>Why / why not →</button></section></div></Page>}

      {view === 'whatif' && <Page title="What-If Lab" eyebrow="WHAT HAPPENS IF WE DO IT?" subtitle="Run deterministic scenarios without mutating the live operational database."><div className="scenario-grid">{[['accident_congestion','Accident worsens'],['road_closure','Road closure'],['traffic_spike','Traffic spike'],['competing_emergencies','Competing emergencies']].map(([id,label]) => <button className="scenario-card" key={id} onClick={() => void runWhatIf(id)}><GitCompare size={20} /><b>{label}</b><span>Run scenario</span></button>)}</div>{simulation && <section className="panel result-panel"><div className="section-head"><div><p className="eyebrow">SIMULATION RESULT</p><h3>{simulation.scenario_id}</h3></div><Badge tone="good">deterministic · seed {simulation.seed}</Badge></div><div className="event-list">{simulation.events?.map((e: string) => <div key={e}><span>•</span>{e}</div>)}</div><pre>{JSON.stringify(simulation.state, null, 2)}</pre></section>}</Page>}

      {view === 'fleet' && <Page title="Fleet Intelligence" eyebrow="RESOURCE CONSEQUENCES" subtitle="Fleet state is operational evidence. Backup decisions expose their coverage trade-off."><section className="fleet-grid">{vehicles.map(v => <div className="vehicle-card" key={v.id}><div className="vehicle-top"><Truck size={18} /><Badge tone={v.status === 'available' ? 'good' : 'neutral'}>{v.status}</Badge></div><h3>{v.name}</h3><div className="vehicle-data"><span>GPS</span><b>{v.lat.toFixed(5)}, {v.lon.toFixed(5)}</b><span>Speed</span><b>{v.speed_kmh.toFixed(1)} km/h</b><span>Updated</span><b>{new Date(v.updated_at).toLocaleTimeString()}</b></div></div>)}</section><section className="panel"><h3>Backup counterfactual</h3><p>Current decision exposes <b>{rec?.backup_vehicle_id || 'no backup'}</b> with an estimated response of <b>{rec?.backup_eta_min ? `${rec.backup_eta_min.toFixed(1)} min` : '—'}</b>. Coverage impact is calculated from available fleet state rather than a fixed constant.</p></section></Page>}

      {view === 'simulation' && <Page title="Emergency Replay" eyebrow="REPLAY THE DECISION" subtitle="Use the same local data path to inspect how the situation and decision evolve over the control-loop snapshots."><section className="panel"><div className="section-head"><div><h3>Replay clock</h3><p>{snapshot?.scenario_id || 'emergency_response'} · {snapshot?.simulation_time?.toFixed?.(0) || 0}s</p></div><button className="secondary" onClick={() => postJSON('/api/v1/twin/command', { action: 'reset', scenario_id: 'emergency_response' }).then(() => setNotice('Replay reset.'))}><RotateCcw size={15} /> Reset</button></div><div className="replay-steps">{(snapshot?.timeline || []).map((s: any) => <div key={s.label} className={s.status}><span>{s.status === 'complete' ? '✓' : s.status === 'active' ? '●' : '○'}</span>{s.label.replace('_',' ')}</div>)}</div><div className="replay-actions"><button className="primary" onClick={() => postJSON('/api/v1/twin/command', { action: 'start', speed: 1 })}><Play size={15} /> Start</button><button className="secondary" onClick={() => postJSON('/api/v1/twin/command', { action: 'stop', speed: 1 })}>Pause</button></div></section></Page>}

      {view === 'air' && <Page title="Mountain Air Rescue Desk" eyebrow="AIRBORNE EMERGENCY RESPONSE" subtitle="A dedicated decision layer for incidents where altitude, terrain and road access make ground response unreliable. All aviation values below are local simulation data; dispatch authority remains human-controlled."><div className="air-region-tabs">{[['himachal','Himachal Pradesh'],['uttarakhand','Uttarakhand'],['ladakh','Ladakh']].map(([id,label]) => <button key={id} className={airRegion===id?'active':''} onClick={()=>setAirRegion(id)}><Mountain size={15}/>{label}</button>)}</div><div className="air-layout"><section className="panel air-map-panel"><div className="section-head"><div><p className="eyebrow">MOUNTAIN SITUATION MAP</p><h3>{airRescue?.incident?.name || 'Loading rescue area'}</h3></div><Badge tone={airRescue?.decision?.includes('RECOMMENDED')?'good':'warn'}>{airRescue?.decision || 'ANALYZING'}</Badge></div><AirRescueMap plan={airRescue}/></section><section className="panel air-decision-panel"><div className="air-unit-head"><div className="air-unit-icon"><Plane size={22}/></div><div><p className="eyebrow">AIR AMBULANCE</p><h3>{airRescue?.air_ambulance?.name || '—'}</h3><small>{airRescue?.air_ambulance?.crew || '—'}</small></div></div><div className="air-metrics"><Metric label="FLIGHT ETA" value={airRescue ? `${airRescue.flight_eta_min} min` : '—'} note="local flight-time simulation"/><Metric label="LANDING FEASIBILITY" value={airRescue ? `${Math.round(airRescue.landing_feasibility*100)}%` : '—'} note={airRescue?.selected_landing_zone?.status || '—'}/><Metric label="FUEL" value={airRescue ? `${airRescue.air_ambulance.fuel_pct}%` : '—'} note={`range ${airRescue?.air_ambulance?.range_km || '—'} km`}/><Metric label="TERRAIN" value={airRescue?.terrain_risk || '—'} note={`altitude ${airRescue?.incident?.altitude_m?.toLocaleString?.() || '—'} m`}/></div><div className="weather-card"><div><CloudSun size={18}/><b>Flight conditions</b></div><span><Wind size={14}/> {airRescue?.weather?.wind_kmh} km/h</span><span>Visibility {airRescue?.weather?.visibility_km} km</span><span>Cloud base {airRescue?.weather?.cloud_base_m?.toLocaleString?.()} m</span><Badge tone={airRescue?.weather?.status==='FLYABLE'?'good':'warn'}>{airRescue?.weather?.status}</Badge></div><div className="landing-card"><p className="eyebrow">LANDING ZONE DECISION</p><h4>{airRescue?.selected_landing_zone?.name}</h4><p>{airRescue?.selected_landing_zone?.surface} · {airRescue?.selected_landing_zone?.altitude_m?.toLocaleString?.()} m · {airRescue?.selected_landing_zone?.status}</p><p className="muted">Alternate: <b>{airRescue?.alternate_landing_zone?.name}</b> · {airRescue?.alternate_landing_zone?.status}</p></div><div className="hospital-air-card"><p className="eyebrow">TRAUMA DESTINATION</p><h4>{airRescue?.hospital?.name}</h4><div><Badge tone={airRescue?.hospital?.trauma==='READY'?'good':'warn'}>{airRescue?.hospital?.trauma}</Badge><span>ICU {airRescue?.hospital?.icu ? Math.round(airRescue.hospital.icu*100) : '—'}%</span><span>Helipad {airRescue?.hospital?.helipad}</span></div></div><div className="constraint-list">{(airRescue?.constraints || []).map((c:string)=><div key={c}><Check size={14}/>{c}</div>)}</div><button className="primary full air-dispatch" onClick={executeAirRescue}><Plane size={16}/> Execute AI Air Rescue</button></section></div></Page>}

      {view === 'analytics' && <Page title="Response Intelligence" eyebrow="DID IT WORK?" subtitle="Measured values come from recorded decisions and outcomes; no synthetic success claims are shown."><div className="metrics"><Metric label="DECISIONS RECORDED" value={audit.filter(x => x.event_type === 'decision_generated').length} /><Metric label="APPROVAL EVENTS" value={audit.filter(x => x.event_type === 'action:approve' || x.event_type === 'human_approval').length} /><Metric label="ACTIVE INCIDENTS" value={incidents.length} /><Metric label="FLEET UNITS" value={vehicles.length} /></div><section className="panel"><h3>Operational events</h3>{audit.slice(0,12).map((a:any) => <div className="audit-row" key={a.id}><span>{new Date(a.created_at).toLocaleTimeString()}</span><b>{a.event_type}</b><code>{JSON.stringify(a.payload)}</code></div>)}</section></Page>}

      {view === 'audit' && <Page title="Decision & AI Audit" eyebrow="WHY THIS DECISION?" subtitle="Every generated decision records its evidence, routing source, actions, policy and human approval state."><section className="panel"><div className="audit-hero"><Shield size={28} /><div><h3>{rec?.decision_id || 'No decision selected'}</h3><p>{rec?.reasoning}</p></div></div>{audit.slice(0,20).map((a:any) => <div className="audit-row" key={a.id}><span>{new Date(a.created_at).toLocaleString()}</span><b>{a.event_type}</b><code>{JSON.stringify(a.payload)}</code></div>)}</section></Page>}
    </main>
    <footer><span>GEOAGENTIC · local company-ready control plane</span><span>Decision support — human dispatcher remains the authority.</span></footer>
  </div>;
}

function Page({ title, eyebrow, subtitle, children }: { title: string; eyebrow: string; subtitle: string; children: React.ReactNode }) { return <><section className="page-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="lead">{subtitle}</p></section>{children}</>; }
