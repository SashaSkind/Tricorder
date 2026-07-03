import { useEffect, useMemo, useRef, useState } from 'react';

/* ─────────────────────────── API ─────────────────────────── */

const CONV = 'tricorder-session';

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'makers-conversation-id': CONV },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text().catch(() => '')}`);
  return res.json() as Promise<T>;
}

interface Patient { name: string; age: number; sex: string; mrn: string }
interface Vertebra { level: string; prob: number; flagged: boolean }
interface CaseSummary {
  study_uid: string; accession: string; patient: Patient;
  indication: string; acquired: string; n_slices: number; expected_positive: boolean;
}
interface Critical {
  is_critical: boolean; level: string | null; confidence: number;
  fracture_type: string | null; key_slice: number | null; slice_range: number[] | null; threshold: number;
}
interface TLEvent { type: string; ts: string; to?: string; responder?: string; level?: string; confidence?: number; overall?: number }
interface Detection { model: string; n_slices: number; patient_overall: number; vertebrae: Vertebra[]; wall_ms: number; critical: Critical }
interface Alert { to: string; to_phone: string; level: string; fracture_type: string; confidence: number; key_slice: number; body: string }
interface AnalyzeResult {
  study_uid: string; accession: string; patient: Patient; indication: string; acquired: string;
  order: { ordering_provider: string; role: string; phone: string; department: string; pager: string };
  detection: Detection; critical: Critical; paged: boolean;
  impression: string; impression_source: string; alert?: Alert; timeline: TLEvent[]; error?: string;
  sms?: { channel: string; sent: boolean };
}
interface AckResult { acknowledged: boolean; ack: TLEvent; turnaround_seconds: number | null; timeline: TLEvent[] }

/* ─────────────────────────── CT viewer ─────────────────────────── */

function CTViewer({ result }: { result: AnalyzeResult }) {
  const c = result.critical;
  const positive = c.is_critical && c.key_slice != null;
  const levelOrder = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7'];
  const idx = c.level ? levelOrder.indexOf(c.level) : 1;
  const boxY = 96 + idx * 4;

  return (
    <div className="ct-wrap">
      <div className="ct-hud">
        <span>AXIAL · {result.acquired.split('·')[0].trim()}</span>
        <span>SLICE {positive ? c.key_slice : '—'}/{result.detection.n_slices} · W1800 L400</span>
      </div>
      <svg viewBox="0 0 320 260" width="100%" style={{ display: 'block' }}>
        <defs>
          <radialGradient id="tissue" cx="50%" cy="46%" r="55%">
            <stop offset="0%" stopColor="#6b7688" />
            <stop offset="55%" stopColor="#39424f" />
            <stop offset="100%" stopColor="#11161d" />
          </radialGradient>
          <radialGradient id="bone" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="#f2f4f7" />
            <stop offset="70%" stopColor="#c3ccd6" />
            <stop offset="100%" stopColor="#7f8b99" />
          </radialGradient>
        </defs>
        <rect width="320" height="260" fill="#05070b" />
        <ellipse cx="160" cy="130" rx="96" ry="86" fill="url(#tissue)" opacity="0.95" />
        <ellipse cx="160" cy="130" rx="96" ry="86" fill="none" stroke="#0a0e14" strokeWidth="2" />
        <ellipse cx="160" cy="96" rx="16" ry="12" fill="#04060a" />
        <circle cx="122" cy="120" r="7" fill="#20293a" />
        <circle cx="198" cy="120" r="7" fill="#20293a" />
        <ellipse cx="160" cy={boxY + 14} rx="30" ry="22" fill="url(#bone)" />
        <ellipse cx="160" cy={boxY + 34} rx="13" ry="11" fill="#04060a" stroke="#2b3547" strokeWidth="1.5" />
        <ellipse cx="120" cy={boxY + 20} rx="14" ry="9" fill="url(#bone)" opacity="0.9" />
        <ellipse cx="200" cy={boxY + 20} rx="14" ry="9" fill="url(#bone)" opacity="0.9" />
        {positive && (
          <>
            <line x1="150" y1={boxY + 8} x2="172" y2={boxY + 22} stroke="#ff5964" strokeWidth="2.2" />
            <rect x="126" y={boxY - 12} width="68" height="52" rx="4" fill="none"
              stroke="#ff5964" strokeWidth="2" strokeDasharray="5 4" />
            <rect x="126" y={boxY - 26} width="96" height="14" rx="3" fill="#ff5964" />
            <text x="130" y={boxY - 15} fontFamily="'JetBrains Mono', monospace" fontSize="10" fill="#0a0e14" fontWeight="700">
              {c.level} · {Math.round(c.confidence * 100)}% FRACTURE
            </text>
          </>
        )}
        <line x1="160" y1="8" x2="160" y2="252" stroke="#35d0ba" strokeWidth="0.5" opacity="0.25" />
        <line x1="8" y1="130" x2="312" y2="130" stroke="#35d0ba" strokeWidth="0.5" opacity="0.25" />
      </svg>
    </div>
  );
}

/* ─────────────────────────── Phone ─────────────────────────── */

function Phone({ result, acked, ackTurnaround, onAck, acking }: {
  result: AnalyzeResult; acked: boolean; ackTurnaround: number | null;
  onAck: () => void; acking: boolean;
}) {
  if (!result.paged || !result.alert) {
    return (
      <div className="phone">
        <div className="phone-notch" />
        <div className="phone-empty">
          No page sent.<br />Study screened negative — the ordering physician is not interrupted.
        </div>
      </div>
    );
  }
  const a = result.alert;
  return (
    <div className="phone">
      <div className="phone-notch" />
      <div className="phone-head">
        <div className="phone-av">🩺</div>
        <div>
          <div className="phone-name">{a.to}</div>
          <div className="phone-sub">{result.order.role} · {a.to_phone}</div>
        </div>
      </div>
      <div className="phone-body">
        <div className="sms">
          <span className="sms-tag">🚨 CRITICAL RESULT · Tricorder</span>
          {a.body}
          <span className="sms-link">↳ view slice {a.key_slice} · tricorder.app/s/{result.accession}</span>
        </div>
        <div className="sms-time">
          {result.sms?.channel === 'twilio' && result.sms?.sent
            ? `delivered via Twilio · to ${a.to_phone}`
            : 'delivered · in-app demo (add Twilio creds for real SMS)'}
        </div>
        {acked && (
          <>
            <div className="sms sms-out">ACK — reviewed, neurosurgery paged. Thanks.</div>
            <div className="sms-time">
              acknowledged{ackTurnaround != null ? ` · ${ackTurnaround}s after page` : ''}
            </div>
          </>
        )}
      </div>
      {!acked ? (
        <>
          <button className="ack-btn" onClick={onAck} disabled={acking}>
            {acking ? 'Sending…' : 'Reply “ACK” ✓'}
          </button>
          <div className="phone-hint">The ER physician taps to acknowledge → hits the webhook</div>
        </>
      ) : (
        <div className="phone-hint">✓ Reply captured by the /ack webhook</div>
      )}
    </div>
  );
}

/* ─────────────────────────── Timeline ─────────────────────────── */

function fmt(ts: string) {
  try { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  catch { return ts; }
}

function Timeline({ events }: { events: TLEvent[] }) {
  const label = (e: TLEvent): [string, string] => {
    switch (e.type) {
      case 'paged': return ['n-page', `Paged ${e.to} via SMS — ${e.level} finding`];
      case 'acknowledged': return ['n-ack', `Acknowledged by ${e.responder}`];
      case 'screened_negative': return ['n-neg', `Screened negative (${Math.round((e.overall ?? 0) * 100)}%) — no page`];
      default: return ['n-detect', e.type];
    }
  };
  return (
    <div className="timeline">
      <div className="sec-title">Closed-loop audit trail</div>
      {events.length === 0 && <div style={{ color: 'var(--muted-2)', fontSize: 12.5 }}>No events yet.</div>}
      {events.map((e, i) => {
        const [cls, text] = label(e);
        return (
          <div className="tl-item" key={i}>
            <div className={`tl-node ${cls}`} />
            <div className="tl-txt"><div className="t">{text}</div><div className="ts">{fmt(e.ts)}</div></div>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────── Steps ─────────────────────────── */

const STEP_LABELS = [
  'Loading CT cervical-spine study',
  'Running fracture-detection model',
  'Localizing fracture level & key slice',
  'Generating ER impression · AI Gateway',
  'Paging ordering physician',
];

function Steps({ active }: { active: number }) {
  return (
    <div className="steps">
      {STEP_LABELS.map((s, i) => {
        const cls = i < active ? 'done' : i === active ? 'run' : '';
        return (
          <div className={`step ${cls}`} key={i}>
            <div className="step-ic">{i < active ? '✓' : i + 1}</div>{s}
          </div>
        );
      })}
    </div>
  );
}

/* ─────────────────────────── App ─────────────────────────── */

type Phase = 'idle' | 'analyzing' | 'done';

export default function App() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [step, setStep] = useState(0);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [acked, setAcked] = useState(false);
  const [acking, setAcking] = useState(false);
  const [turnaround, setTurnaround] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    post<{ cases: CaseSummary[] }>('/cases', {})
      .then(d => setCases(d.cases))
      .catch(e => setError(String(e)));
  }, []);

  const selectStudy = (uid: string) => {
    timers.current.forEach(clearTimeout);
    setSelected(uid); setPhase('idle'); setResult(null); setAcked(false);
    setTurnaround(null); setStep(0); setError(null);
  };

  const runAnalyze = async () => {
    if (!selected) return;
    setError(null); setPhase('analyzing'); setStep(0); setResult(null); setAcked(false); setTurnaround(null);

    timers.current.forEach(clearTimeout);
    timers.current = STEP_LABELS.map((_, i) =>
      window.setTimeout(() => setStep(i + 1), 550 * (i + 1)));

    try {
      const [res] = await Promise.all([
        post<AnalyzeResult>('/analyze', { study_uid: selected }),
        new Promise(r => setTimeout(r, 550 * (STEP_LABELS.length + 1))),
      ]);
      if (res.error) throw new Error(res.error);
      setResult(res);
      setPhase('done');
    } catch (e) {
      setError(String(e)); setPhase('idle');
    }
  };

  const doAck = async () => {
    if (!result) return;
    setAcking(true);
    try {
      const r = await post<AckResult>('/ack', {
        study_uid: result.study_uid,
        responder: result.order.ordering_provider,
        reply: 'ACK',
      });
      setAcked(true);
      setTurnaround(r.turnaround_seconds ?? null);
      setResult({ ...result, timeline: r.timeline });
    } catch (e) {
      setError(String(e));
    } finally {
      setAcking(false);
    }
  };

  const badge = (cs: CaseSummary) => {
    if (result && selected === cs.study_uid && phase === 'done') {
      if (!result.paged) return <span className="study-badge badge-clear">SCREENED · CLEAR</span>;
      if (acked) return <span className="study-badge badge-ack">ACKNOWLEDGED</span>;
      return <span className="study-badge badge-critical">CRITICAL · PAGED</span>;
    }
    return <span className="study-badge badge-pending">PENDING READ</span>;
  };

  const selectedCase = useMemo(() => cases.find(c => c.study_uid === selected), [cases, selected]);

  return (
    <>
      <header className="app-header">
        <div className="logo-mark">✚</div>
        <div className="brand">
          <h1>Tricorder</h1>
          <p>Closed-loop critical-findings agent · cervical-spine CT</p>
        </div>
        <div className="header-spacer" />
        <span className="pill"><span className="dot" /> EdgeOne Makers · live</span>
      </header>

      <div className="layout">
        {/* ── Worklist ── */}
        <div>
          <div className="col-title">Incoming worklist</div>
          <div className="worklist">
            {cases.map(cs => (
              <button key={cs.study_uid}
                className={`study-card ${selected === cs.study_uid ? 'active' : ''}`}
                onClick={() => selectStudy(cs.study_uid)}>
                <div className="row1">
                  <span className="name">{cs.patient.name}</span>
                  <span className="acc">{cs.accession}</span>
                </div>
                <div className="demo">{cs.patient.age}{cs.patient.sex} · {cs.indication}</div>
                {badge(cs)}
              </button>
            ))}
            {cases.length === 0 && !error && <div style={{ color: 'var(--muted-2)', fontSize: 13 }}>Loading studies…</div>}
          </div>
        </div>

        {/* ── Main ── */}
        <div className="panel">
          {!selectedCase && (
            <div className="empty">
              <div style={{ fontSize: 34 }}>🖖</div>
              <div className="big">Select a cervical-spine CT study to run Tricorder</div>
              <div>Detect → localize → impression → page ER → close the loop</div>
            </div>
          )}

          {selectedCase && (
            <>
              <div className="detail-head">
                <div>
                  <h2>{selectedCase.patient.name} · {selectedCase.patient.age}{selectedCase.patient.sex}</h2>
                  <div className="sub">{selectedCase.acquired}</div>
                </div>
                {phase !== 'analyzing' && (
                  <button className="run-btn" onClick={runAnalyze}>
                    {phase === 'done' ? '↻ Re-run Tricorder' : '▶ Run Tricorder'}
                  </button>
                )}
              </div>

              <div className="meta-grid">
                <div><div className="k">MRN</div><div className="v">{selectedCase.patient.mrn}</div></div>
                <div><div className="k">Accession</div><div className="v">{selectedCase.accession}</div></div>
                <div style={{ gridColumn: '1 / -1' }}><div className="k">Indication</div><div className="v">{selectedCase.indication}</div></div>
              </div>

              {phase === 'analyzing' && <Steps active={step} />}

              {error && <div className="err">{error}</div>}

              {phase === 'done' && result && (
                <>
                  <div className={`alert ${result.paged ? 'critical' : 'clear'}`}>
                    <div className="a-top">
                      {result.paged
                        ? <>🚨 CRITICAL · {result.critical.fracture_type} at {result.critical.level}</>
                        : <>✓ No critical finding</>}
                      {result.paged && <span style={{ fontFamily: 'var(--mono)', fontSize: 12, marginLeft: 'auto', opacity: .85 }}>
                        {Math.round(result.critical.confidence * 100)}% · slice {result.critical.key_slice}
                      </span>}
                    </div>
                    <div className="a-body">{result.impression}</div>
                    <div className="a-src">
                      impression: {result.impression_source === 'llm' ? 'EdgeOne AI Gateway' : 'clinical template (set AI_GATEWAY_API_KEY for LLM)'} ·
                      model: {result.detection.model} · {result.detection.wall_ms}ms
                    </div>
                  </div>

                  <div className="grid-2">
                    <div>
                      <div className="sec-title">Flagged axial slice</div>
                      <CTViewer result={result} />
                    </div>
                    <div>
                      <div className="sec-title">Per-vertebra probability (C1–C7)</div>
                      <div className="vbars">
                        {result.detection.vertebrae.map(v => (
                          <div key={v.level} className={`vbar ${v.flagged ? 'hot' : ''}`}>
                            <span className="lvl">{v.level}</span>
                            <span className="track"><span className="fill" style={{ width: `${Math.max(3, v.prob * 100)}%` }} /></span>
                            <span className="pct">{Math.round(v.prob * 100)}%</span>
                          </div>
                        ))}
                      </div>
                      <div style={{ marginTop: 14 }} className="sec-title">Ordering physician</div>
                      <div className="meta-grid" style={{ margin: 0 }}>
                        <div><div className="k">Attending</div><div className="v">{result.order.ordering_provider}</div></div>
                        <div><div className="k">Contact</div><div className="v">{result.order.phone}</div></div>
                      </div>
                    </div>
                  </div>

                  <Timeline events={result.timeline} />
                  {acked && (
                    <div className="loop-badge">
                      <div className="big">✓ Loop closed — critical result acknowledged</div>
                      <div className="small">
                        page → ack{turnaround != null ? ` in ${turnaround}s` : ''} · documented for ACR compliance
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>

        {/* ── Phone ── */}
        <div>
          <div className="col-title">ER physician · mobile</div>
          {phase === 'done' && result
            ? <Phone result={result} acked={acked} ackTurnaround={turnaround} onAck={doAck} acking={acking} />
            : (
              <div className="phone">
                <div className="phone-notch" />
                <div className="phone-empty">The critical-finding text appears here once you run Tricorder on a positive study.</div>
              </div>
            )}
        </div>
      </div>
    </>
  );
}
