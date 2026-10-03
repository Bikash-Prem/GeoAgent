import React, { useRef, useState } from 'react';
import { Mic, Send } from 'lucide-react';
import { postJSON } from '../lib/api';

type CommandResult = {
  intent: string;
  answer: string;
  mode: string;
  tools_used: string[];
  grounded_on: string[];
  recommendation?: any;
};

const SUGGESTIONS = ['Show the best alternative route for AMB-07', 'Why is AMB-07 delayed?', 'Compare all routes', 'Is a backup ambulance needed?', 'Which hospital has ICU capacity?'];

export default function CommandBar({ vehicleId, onResult }: { vehicleId: string; onResult: (r: CommandResult) => void }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [result, setResult] = useState<CommandResult | null>(null);
  const [error, setError] = useState('');
  const recognizer = useRef<any>(null);
  const SR = typeof window !== 'undefined' ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;

  const send = async (value: string) => {
    const t = value.trim();
    if (!t) return;
    setBusy(true);
    setError('');
    try {
      const res: CommandResult = await postJSON('/api/v1/agent/command', { text: t, vehicle_id: vehicleId });
      setResult(res);
      onResult(res);
    } catch (e) {
      setError('GeoAgent could not answer. Check that the API is running and the vehicle ID exists.');
    } finally {
      setBusy(false);
    }
  };

  const listen = () => {
    if (!SR) return;
    if (listening) {
      recognizer.current?.stop();
      return;
    }
    const r = new SR();
    r.lang = 'en-IN';
    r.interimResults = false;
    r.onresult = (e: any) => {
      const spoken = e.results[0][0].transcript;
      setText(spoken);
      send(spoken);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recognizer.current = r;
    setListening(true);
    r.start();
  };

  return (
    <div className="cmd">
      <div className="cmd-input">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send(text)}
          placeholder={listening ? 'Listening…' : 'Type or speak a command, e.g. “Show the best alternative route for AMB-07”'}
          aria-label="Dispatcher command"
        />
        {SR && (
          <button className={`round ${listening ? 'live' : ''}`} onClick={listen} aria-label="Speak a command" title="Voice command">
            <Mic size={15} />
          </button>
        )}
        <button className="round dark" onClick={() => send(text)} disabled={busy} aria-label="Send command">
          <Send size={15} />
        </button>
      </div>
      <div className="cmd-chips">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => { setText(s); send(s); }} disabled={busy}>{s}</button>
        ))}
      </div>
      {error && <p className="cmd-error">{error}</p>}
      {result && (
        <div className="cmd-answer" role="status">
          <p>{result.answer}</p>
          <div className="cmd-meta">
            <span>{result.mode}</span>
            {result.tools_used.map((t) => <span key={t}>{t}</span>)}
            {result.grounded_on.length > 0 && <span>grounded on {result.grounded_on.length} evidence items</span>}
            <span>human approval required</span>
          </div>
        </div>
      )}
    </div>
  );
}
