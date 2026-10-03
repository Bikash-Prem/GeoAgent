import React, { useState } from 'react';
import { ArrowRight, Check, Menu, Volume2, VolumeX, X, AlertTriangle } from 'lucide-react';
import type { Ops } from '../lib/ops';

export type Page = 'home' | 'command' | 'response' | 'air' | 'whatif' | 'fleet' | 'evidence';
export const PAGES: { id: Page; label: string }[] = [
  { id: 'home', label: 'Overview' }, { id: 'command', label: 'Command' }, { id: 'response', label: 'Response' },
  { id: 'air', label: 'Air rescue' }, { id: 'whatif', label: 'What-if' }, { id: 'fleet', label: 'Coverage' }, { id: 'evidence', label: 'Evidence' },
];
export const href = (p: Page) => (p === 'home' ? '#/' : `#/${p}`);

export function Nav({ page, ops }: { page: Page; ops: Ops }) {
  const [open, setOpen] = useState(false);
  return (
    <header className="nav">
      <a className="wordmark" href="#/">GEO<i>·</i>AGENTIC</a>
      <nav className={`nav-links ${open ? 'open' : ''}`} aria-label="Main">
        {PAGES.map((p) => (
          <a key={p.id} href={href(p.id)} className={page === p.id ? 'active' : ''} aria-current={page === p.id ? 'page' : undefined} onClick={() => setOpen(false)}>{p.label}</a>
        ))}
      </nav>
      <div className="nav-right">
        <span className={`status-pill ${ops.live ? 'on' : ''}`}><b />{ops.apiOffline ? 'API offline' : ops.live ? 'Live telemetry' : 'Replay mode'}</span>
        <button className={`round ghost ${ops.voiceOn ? 'on' : ''}`} onClick={() => ops.setVoiceOn(!ops.voiceOn)} aria-pressed={ops.voiceOn} title={ops.voiceOn ? 'Voice announcements on' : 'Voice announcements off'}>
          {ops.voiceOn ? <Volume2 size={15} /> : <VolumeX size={15} />}
        </button>
        <a className="pill dark sm nav-cta" href="#/command">Open command <ArrowRight size={14} /></a>
        <button className="round ghost menu-btn" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Menu">{open ? <X size={16} /> : <Menu size={16} />}</button>
      </div>
    </header>
  );
}

export function Toast({ ops }: { ops: Ops }) {
  if (!ops.notice) return null;
  return (
    <div className={`toast ${ops.notice.tone === 'warn' ? 'warn' : ''}`} role="status">
      {ops.notice.tone === 'warn' ? <AlertTriangle size={15} /> : <Check size={15} />} {ops.notice.text}
      <button onClick={ops.clearNotice} aria-label="Dismiss">×</button>
    </div>
  );
}

export function PageHead({ eyebrow, title, accent, lede, image, alt, children }: { eyebrow: string; title: string; accent: string; lede: string; image?: string; alt?: string; children?: React.ReactNode }) {
  return (
    <section className={`page-head ${image ? 'with-art' : ''}`}>
      <div className="page-head-copy">
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="display page-title">{title}<br /><span className="g">{accent}</span></h1>
        <p className="lede">{lede}</p>
        {children}
      </div>
      {image && <figure className="page-art"><img src={image} alt={alt || ''} /></figure>}
    </section>
  );
}

export function Footer({ ops }: { ops: Ops }) {
  return (
    <footer className="foot">
      <div className="foot-grid">
        <div>
          <div className="wordmark">GEO<i>·</i>AGENTIC</div>
          <h3 className="display foot-tag">Decide faster.</h3>
          <p>Observe, predict and compare responses with evidence, with a dispatcher always making the final call.</p>
        </div>
        <nav className="foot-links">{PAGES.map((p) => <a key={p.id} href={href(p.id)}>{p.label}</a>)}</nav>
        <div className="foot-status">
          <small>SYSTEM STATUS</small>
          <h4>{ops.apiOffline ? 'API offline.' : 'All systems operational.'}<br />{ops.vehicles.filter((v) => v.status === 'available').length} units ready.</h4>
          <div className="pill-input">
            <span>{ops.live ? 'Live telemetry connected' : 'Telemetry replaying'}</span>
            <a href="#/command" aria-label="Open command"><ArrowRight size={15} /></a>
          </div>
        </div>
      </div>
      <div className="foot-bottom">
        <span>© 2026 GeoAgentic · v3.0 control plane</span>
        <span>Decision support, not an autonomous authority. Signal control and aviation values are simulated.</span>
      </div>
    </footer>
  );
}
