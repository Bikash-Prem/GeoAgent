export const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || '';
const headers = (): Record<string, string> => (API_KEY ? { 'X-API-Key': API_KEY } : {});

async function parseResponse(response: Response) {
  if (!response.ok) {
    let detail = '';
    try { detail = (await response.json()).detail; } catch { /* not JSON */ }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}
export async function getJSON(path: string) { return parseResponse(await fetch(`${API}${path}`, { headers: headers() })); }
export async function postJSON(path: string, body: unknown = {}) {
  return parseResponse(await fetch(`${API}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers() }, body: JSON.stringify(body) }));
}
export async function download(path: string, filename: string) {
  const r = await fetch(`${API}${path}`, { headers: headers() });
  if (!r.ok) throw new Error(`Download failed (${r.status})`);
  const url = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
export function wsUrl(path: string) { const base = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'; return `${base}${path}`; }
