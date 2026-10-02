const API=import.meta.env.VITE_API_URL||'http://localhost:8000';
const API_KEY=import.meta.env.VITE_API_KEY||'';
const headers=()=>API_KEY?{'X-API-Key':API_KEY}:{};
async function parseResponse(response:Response){if(!response.ok)throw new Error(await response.text()||`Request failed (${response.status})`);return response.json()}
export async function getJSON(path:string){return parseResponse(await fetch(`${API}${path}`,{headers:headers()}))}
export async function postJSON(path:string,body:unknown){return parseResponse(await fetch(`${API}${path}`,{method:'POST',headers:{'Content-Type':'application/json',...headers()},body:JSON.stringify(body)}))}
export function wsUrl(path:string){const base=import.meta.env.VITE_WS_URL||'ws://localhost:8000';return `${base}${path}`}
