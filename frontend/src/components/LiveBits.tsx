import React from 'react';
import { AlertTriangle, RefreshCw, Satellite } from 'lucide-react';
import { ACTION_LABEL, Ops } from '../lib/ops';

const routeName = (id: string | null) => (!id ? 'no route' : id === 'route-1' ? 'current route' : `alternative ${Number(id.split('-')[1]) - 1}`);

/** Banner shown when the control loop's fresh re-evaluation no longer matches the decision in the log. */
export function DriftBanner({ ops }: { ops: Ops }) {
  const d = ops.drift;
  if (!d) return null;
  const sign = d.eta_change_min > 0 ? '+' : '';
  const changed = d.was.action !== d.now.action || d.was.route_id !== d.now.route_id;
  return (
    <div className="drift" role="alert">
      <AlertTriangle size={18} />
      <div>
        <b>Conditions changed since {d.logged_decision_id}</b>
        <p>{changed
          ? `It was "${ACTION_LABEL[d.was.action] || d.was.action}" on the ${routeName(d.was.route_id)}. The engine would now advise "${ACTION_LABEL[d.now.action] || d.now.action}" on the ${routeName(d.now.route_id)}, ETA ${sign}${d.eta_change_min.toFixed(1)} min.`
          : `Same action, but the expected arrival moved ${sign}${d.eta_change_min.toFixed(1)} min.`}{d.logged_status === 'approved' ? ' The approved plan may need review.' : ''}</p>
      </div>
      <button className="pill dark sm" onClick={ops.analyze} disabled={ops.loading}><RefreshCw size={14} className={ops.loading ? 'spin' : ''} /> Re-analyze</button>
    </div>
  );
}

/** Where the routes came from: a live map provider or the built-in demo graph. */
export function SourceBadge({ source }: { source?: any }) {
  if (!source) return null;
  const live = source.mode === 'live';
  const label = live ? `${String(source.source).replace(/^\w/, (c: string) => c.toUpperCase())} real-road routes` : source.mode === 'fallback' ? 'Provider down · demo graph' : 'Demo road graph';
  return <span className={`src-badge ${source.mode}`} title={source.reason || ''}><Satellite size={12} /> {label}</span>;
}
