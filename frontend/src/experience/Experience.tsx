import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { get, inr, label, pct, post, riskColor, type RadarLite, type Scenario, type Score, type ScoredCustomer, type Summary, type Twin } from './data'
import { bindScroll } from './scroll'
import './experience.css'

const BackgroundScene = lazy(() => import('./BackgroundScene'))
const RiskGalaxy = lazy(() => import('./RiskGalaxy'))
const ActionBars3D = lazy(() => import('./ActionBars3D'))

const LOOP = [
  ['Detect', 'Revenue-risk model scores every failed payment, invoice and checkout.'],
  ['Diagnose', 'Root-cause engine reads stored evidence: method mismatch, liquidity, friction.'],
  ['Predict', 'Action model estimates recovery probability for nine interventions.'],
  ['Simulate', 'Economics engine nets out cost, friction and organic recovery.'],
  ['Govern', 'Deterministic Policy Guard decides ALLOW, BLOCK or ESCALATE.'],
  ['Execute', 'Payment links, retries and messages through provider adapters.'],
  ['Verify', 'Recovery is only counted once the payment is confirmed.'],
  ['Measure', 'Incrementality model separates assisted from organic recovery.'],
]

function useInView<T extends Element>(threshold = 0.25) {
  const ref = useRef<T>(null); const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current; if (!el) return
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect() } }, { threshold })
    io.observe(el); return () => io.disconnect()
  }, [threshold])
  return [ref, seen] as const
}

function Counter({ value, format, duration = 1600 }: { value?: number | null; format: (v: number) => string; duration?: number }) {
  const [ref, seen] = useInView<HTMLSpanElement>(0.4); const [shown, setShown] = useState(0)
  useEffect(() => {
    if (!seen || value == null) return
    const start = performance.now(); let raf = 0
    const step = (t: number) => { const k = Math.min(1, (t - start) / duration); setShown(value * (1 - Math.pow(1 - k, 3))); if (k < 1) raf = requestAnimationFrame(step) }
    raf = requestAnimationFrame(step); return () => cancelAnimationFrame(raf)
  }, [seen, value, duration])
  return <span ref={ref}>{value == null ? '—' : format(shown)}</span>
}

function Reveal({ children, className = '', delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const [ref, seen] = useInView<HTMLDivElement>(0.15)
  return <div ref={ref} className={`reveal ${seen ? 'in' : ''} ${className}`} style={{ transitionDelay: `${delay}ms` }}>{children}</div>
}

function Tilt({ children, className = '' }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  return <div ref={ref} className={`tilt ${className}`}
    onPointerMove={(e) => { const r = ref.current!.getBoundingClientRect(); const x = (e.clientX - r.left) / r.width - 0.5; const y = (e.clientY - r.top) / r.height - 0.5; ref.current!.style.transform = `perspective(900px) rotateX(${-y * 8}deg) rotateY(${x * 10}deg) translateZ(0)`; ref.current!.style.setProperty('--mx', `${(x + 0.5) * 100}%`); ref.current!.style.setProperty('--my', `${(y + 0.5) * 100}%`) }}
    onPointerLeave={() => { ref.current!.style.transform = '' }}>{children}</div>
}

const DEFAULT: Scenario = { amount: 18000, customer_lifetime_value: 52000, historical_payment_success_rate: 0.7, historical_recovery_rate: 0.35, retry_count: 1, days_overdue: 9, customer_tenure: 480, days_since_last_payment: 24, payment_method: 'upi', failure_reason: 'bank_declined', preferred_channel: 'whatsapp', segment: 'consumer', hour: 14 }

export default function Experience() {
  const [radar, setRadar] = useState<RadarLite | null>(null)
  const [recovered, setRecovered] = useState<{ total_recovered: number; verified_outcomes: number } | null>(null)
  const [twin, setTwin] = useState<Twin | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [customers, setCustomers] = useState<ScoredCustomer[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Score | null>(null)
  const [scenario, setScenario] = useState<Scenario>(DEFAULT)
  const [score, setScore] = useState<Score | null>(null)
  const [offline, setOffline] = useState(false)
  const [active, setActive] = useState(0)

  useEffect(() => bindScroll(), [])
  useEffect(() => {
    get<RadarLite>('/api/v1/revenue-at-risk').then(setRadar).catch(() => setOffline(true))
    get<{ total_recovered: number; verified_outcomes: number }>('/api/v1/revenue-recovered').then(setRecovered).catch(() => null)
    post<Twin>('/api/v1/recovery-twin/simulate', {}).then(setTwin).catch(() => null)
    get<Summary>('/api/v1/ml/summary').then(setSummary).catch(() => null)
    get<{ items: ScoredCustomer[] }>('/api/v1/ml/customers?limit=220').then((r) => { setCustomers(r.items); if (r.items[0]) setSelected(r.items[0].customer_id) }).catch(() => null)
  }, [])
  useEffect(() => { if (selected) get<Score>(`/api/v1/ml/customers/${selected}`).then(setDetail).catch(() => null) }, [selected])
  useEffect(() => { const t = setTimeout(() => post<Score>('/api/v1/ml/score', scenario).then(setScore).catch(() => null), 180); return () => clearTimeout(t) }, [scenario])
  useEffect(() => {
    const ids = ['hero', 'pulse', 'loop', 'galaxy', 'lab', 'twin', 'models']
    const io = new IntersectionObserver((entries) => entries.forEach((e) => { if (e.isIntersecting) setActive(ids.indexOf(e.target.id)) }), { threshold: 0.45 })
    ids.forEach((id) => { const el = document.getElementById(id); if (el) io.observe(el) }); return () => io.disconnect()
  }, [])

  const set = <K extends keyof Scenario>(k: K, v: Scenario[K]) => setScenario((s) => ({ ...s, [k]: v }))
  const reasons = radar ? Object.entries(radar.risk_by_reason).slice(0, 6) : []
  const maxReason = Math.max(1, ...reasons.map(([, v]) => v))
  const nav = ['Shield', 'Pulse', 'Loop', 'Galaxy', 'Lab', 'Twin', 'Models']

  return (
    <div className="xp">
      <Suspense fallback={<div className="bg-canvas" />}><BackgroundScene /></Suspense>
      <div className="grain" />
      <header className="xp-top">
        <a href="/" className="xp-brand"><span className="glyph">₹</span>DhanRakshak</a>
        <nav className="xp-dots">{nav.map((n, i) => <a key={n} href={`#${['hero', 'pulse', 'loop', 'galaxy', 'lab', 'twin', 'models'][i]}`} className={active === i ? 'on' : ''}><i />{n}</a>)}</nav>
        <a className="xp-cta" href="/console">Command Center →</a>
      </header>
      <div className="progress" />

      <section id="hero" className="xp-hero">
        <div className="hero-copy">
          <p className="kicker">Revenue Recovery Control Plane · Live models</p>
          <h1>Every rupee<br />deserves a <em>second chance.</em></h1>
          <p className="lede">DhanRakshak finds revenue that is slipping away, works out why, picks the intervention with the highest <b>incremental</b> value, and only acts inside deterministic guardrails.</p>
          <div className="hero-actions"><a href="#galaxy" className="btn gold">Explore the risk galaxy</a><a href="#lab" className="btn ghost">Run the models yourself</a></div>
          {offline && <p className="offline">API is waking up (free tier). Refresh in ~30 s.</p>}
        </div>
        <div className="scroll-hint"><span />scroll</div>
      </section>

      <section id="pulse" className="xp-section">
        <Reveal><p className="kicker">01 · Live pulse</p><h2>What's at stake, right now.</h2><p className="sub">Computed live by the Revenue Leakage Radar over 600 sampled customers from the held-out test period (fictional data).</p></Reveal>
        <div className="metric-grid">
          {[
            ['Revenue at risk', radar?.total_revenue_at_risk, 'coral', 'Across all leak signals'],
            ['Verified recovered', recovered?.total_recovered, 'jade', `${recovered?.verified_outcomes ?? '—'} confirmed payments`],
            ['Incremental (not organic)', twin?.incremental_recovery, 'gold', 'Recovery that would not have happened'],
            ['High-risk exposure', radar?.high_risk_revenue, 'coral', 'Risk score ≥ 0.67'],
          ].map(([t, v, tone, d], i) => (
            <Reveal key={String(t)} delay={i * 90}><Tilt className={`metric ${tone}`}><span>{t as string}</span><strong><Counter value={v as number | undefined} format={(x) => inr(x, true)} /></strong><small>{d as string}</small></Tilt></Reveal>
          ))}
        </div>
        <Reveal className="leaks"><h3>Where it leaks</h3>{reasons.map(([k, v]) => <div className="leak" key={k}><span>{label(k)}</span><div className="leak-bar"><i style={{ width: `${(v / maxReason) * 100}%` }} /></div><b>{inr(v, true)}</b></div>)}{!reasons.length && <p className="sub">Waiting for the radar…</p>}</Reveal>
      </section>

      <section id="loop" className="xp-section">
        <Reveal><p className="kicker">02 · The loop</p><h2>AI recommends. Models quantify.<br />Policy decides.</h2></Reveal>
        <div className="loop-track">
          {LOOP.map(([t, d], i) => <Reveal key={t} delay={i * 70}><Tilt className="loop-card"><span className="n">{String(i + 1).padStart(2, '0')}</span><h4>{t}</h4><p>{d}</p></Tilt></Reveal>)}
        </div>
      </section>

      <section id="galaxy" className="xp-section wide">
        <Reveal><p className="kicker">03 · Risk galaxy · interactive 3D</p><h2>Every customer, scored.</h2><p className="sub">{customers.length} highest-exposure customers placed by lifetime value, open amount and model-predicted risk of loss. Drag to orbit, scroll to zoom, click a star.</p></Reveal>
        <div className="galaxy-wrap">
          <div className="galaxy-canvas">{customers.length ? <Suspense fallback={<div className="loading3d">Loading galaxy…</div>}><RiskGalaxy customers={customers} selected={selected} onSelect={setSelected} /></Suspense> : <div className="loading3d">Loading scored customers…</div>}</div>
          <aside className="dossier">
            {detail?.customer ? <>
              <p className="kicker">Customer dossier</p>
              <h3>{detail.customer.name}</h3>
              <p className="meta">{String(detail.customer.city)} · {detail.customer.segment} · {String(detail.customer.language)}</p>
              <div className="gauge" style={{ ['--v' as string]: detail.risk.probability_unrecovered, ['--c' as string]: riskColor(detail.risk.probability_unrecovered) }}><div><b>{pct(detail.risk.probability_unrecovered, 0)}</b><span>risk of loss</span></div></div>
              <dl><div><dt>Open amount</dt><dd>{inr(detail.customer.open_amount)}</dd></div><div><dt>Organic recovery</dt><dd>{pct(detail.organic_recovery_probability, 0)}</dd></div><div><dt>Best action</dt><dd className="gold-t">{label(detail.recommended_action)}</dd></div><div><dt>Policy</dt><dd className={`pol ${detail.policy_decision}`}>{detail.policy_decision}</dd></div></dl>
              <div className="mini-actions">{detail.actions.slice(0, 5).map((a) => <div key={a.action}><span>{label(a.action)}</span><i style={{ width: `${a.recovery_probability * 100}%` }} /><b>{inr(a.expected_incremental_value)}</b></div>)}</div>
              <p className="why">{detail.explanation}</p>
            </> : <p className="sub">Select a star to see its live model score.</p>}
          </aside>
        </div>
      </section>

      <section id="lab" className="xp-section wide">
        <Reveal><p className="kicker">04 · Model lab · live inference</p><h2>Move a slider. Watch the decision change.</h2><p className="sub">Each change calls the trained XGBoost models on the server. Bars are recovery probability per intervention; the red plane is the model's do-nothing baseline. Incremental value = lift over that baseline × amount, minus cost and friction.</p></Reveal>
        <div className="lab">
          <div className="controls">
            <Slider label="Amount at risk" value={scenario.amount} min={500} max={250000} step={500} fmt={(v) => inr(v)} onChange={(v) => set('amount', v)} />
            <Slider label="Lifetime value" value={scenario.customer_lifetime_value} min={1000} max={400000} step={1000} fmt={(v) => inr(v)} onChange={(v) => set('customer_lifetime_value', v)} />
            <Slider label="Payment success history" value={scenario.historical_payment_success_rate} min={0.2} max={1} step={0.01} fmt={(v) => pct(v, 0)} onChange={(v) => set('historical_payment_success_rate', v)} />
            <Slider label="Past recovery rate" value={scenario.historical_recovery_rate} min={0} max={0.9} step={0.01} fmt={(v) => pct(v, 0)} onChange={(v) => set('historical_recovery_rate', v)} />
            <Slider label="Days overdue" value={scenario.days_overdue} min={0} max={60} step={1} fmt={(v) => `${v} d`} onChange={(v) => set('days_overdue', v)} />
            <Slider label="Retries already" value={scenario.retry_count} min={0} max={3} step={1} fmt={(v) => String(v)} onChange={(v) => set('retry_count', v)} />
            <div className="chips"><Chips label="Method" value={scenario.payment_method} options={['upi', 'credit_card', 'debit_card', 'netbanking', 'wallet', 'emi']} onChange={(v) => set('payment_method', v)} />
              <Chips label="Segment" value={scenario.segment} options={['consumer', 'SMB', 'enterprise', 'high_value']} onChange={(v) => set('segment', v)} />
              <Chips label="Failure" value={scenario.failure_reason} options={['bank_declined', 'customer_abandoned']} onChange={(v) => set('failure_reason', v)} />
              <Chips label="Channel" value={scenario.preferred_channel} options={['whatsapp', 'sms', 'email']} onChange={(v) => set('preferred_channel', v)} /></div>
          </div>
          <div className="lab-out">
            <div className="bars3d">{score ? <Suspense fallback={<div className="loading3d">…</div>}><ActionBars3D actions={score.actions} organic={score.do_nothing_probability} /></Suspense> : <div className="loading3d">Scoring…</div>}</div>
            {score && <div className="verdict">
              <div><span>Risk of loss</span><b style={{ color: riskColor(score.risk.probability_unrecovered) }}>{pct(score.risk.probability_unrecovered, 0)}</b></div>
              <div><span>Recommended</span><b className="gold-t">{label(score.recommended_action)}</b></div>
              <div><span>Incremental value</span><b>{inr(score.actions[0].expected_incremental_value)}</b></div>
              <div><span>Policy Guard</span><b className={`pol ${score.policy_decision}`}>{score.policy_decision}</b></div>
            </div>}
          </div>
        </div>
      </section>

      <section id="twin" className="xp-section">
        <Reveal><p className="kicker">05 · Recovery twin</p><h2>With and without DhanRakshak.</h2><p className="sub">Control-group customers received no intervention. The gap is the revenue DhanRakshak actually earned.</p></Reveal>
        <div className="twin">
          <Reveal><Tilt className="twin-card"><span>Without · control group</span><strong><Counter value={twin ? twin.recovery_rate_without_dhanrakshak * 100 : null} format={(v) => `${v.toFixed(1)}%`} /></strong><div className="twin-bar"><i style={{ height: `${(twin?.recovery_rate_without_dhanrakshak ?? 0) * 100}%` }} /></div><small>organic recovery rate</small></Tilt></Reveal>
          <Reveal delay={120}><div className="twin-gap"><b>+<Counter value={twin ? (twin.recovery_rate_with_dhanrakshak - twin.recovery_rate_without_dhanrakshak) * 100 : null} format={(v) => v.toFixed(1)} /> pts</b><span>uplift</span><em><Counter value={twin?.incremental_recovery} format={(v) => inr(v, true)} /> incremental</em></div></Reveal>
          <Reveal delay={240}><Tilt className="twin-card with"><span>With DhanRakshak</span><strong><Counter value={twin ? twin.recovery_rate_with_dhanrakshak * 100 : null} format={(v) => `${v.toFixed(1)}%`} /></strong><div className="twin-bar"><i style={{ height: `${(twin?.recovery_rate_with_dhanrakshak ?? 0) * 100}%` }} /></div><small>assisted recovery rate · n={twin?.sample_size ?? '—'}</small></Tilt></Reveal>
        </div>
      </section>

      <section id="models" className="xp-section">
        <Reveal><p className="kicker">06 · Trained models</p><h2>Real artifacts, honest metrics.</h2><p className="sub">Trained on chronological splits of the {summary?.dataset_version ?? 'synthetic benchmark'} dataset. Metrics come straight from the saved model files.</p></Reveal>
        <div className="model-grid3">
          <Reveal><Tilt className="model-card"><p className="kicker">Revenue risk · {summary?.revenue_risk.version}</p><h4>Will this revenue be lost?</h4><dl>
            <div><dt>Test ROC-AUC</dt><dd>{summary?.revenue_risk.test.roc_auc?.toFixed(3) ?? '—'}</dd></div>
            <div><dt>Precision @ top 10%</dt><dd>{pct(summary?.revenue_risk.test.precision_at_top_10_pct)}</dd></div>
            <div><dt>Brier score</dt><dd>{summary?.revenue_risk.test.brier_score?.toFixed(3) ?? '—'}</dd></div>
            <div><dt>Train / test rows</dt><dd>{summary ? `${summary.revenue_risk.training_rows.toLocaleString('en-IN')} / ${summary.revenue_risk.test_rows.toLocaleString('en-IN')}` : '—'}</dd></div></dl></Tilt></Reveal>
          <Reveal delay={100}><Tilt className="model-card"><p className="kicker">Action recovery · {summary?.action_recovery.version}</p><h4>Which intervention works?</h4><div className="auc-list">{summary && Object.entries(summary.action_recovery.per_action_auc).map(([k, v]) => <div key={k}><span>{label(k)}</span><i style={{ width: `${(v - 0.5) * 400}%` }} /><b>{v.toFixed(3)}</b></div>)}</div></Tilt></Reveal>
          <Reveal delay={200}><Tilt className="model-card"><p className="kicker">Incrementality · {summary?.incrementality.version}</p><h4>Would it recover anyway?</h4><dl>
            <div><dt>Control recovery</dt><dd>{pct(summary?.incrementality.control_recovery_rate)}</dd></div>
            <div><dt>Treatment recovery</dt><dd>{pct(summary?.incrementality.treatment_recovery_rate)}</dd></div>
            <div><dt>Uplift</dt><dd className="gold-t">+{pct(summary?.incrementality.uplift)}</dd></div>
            <div><dt>Incremental revenue (test)</dt><dd>{inr(summary?.incrementality.incremental_recovered_revenue, true)}</dd></div></dl></Tilt></Reveal>
        </div>
        <Reveal className="closing"><h2>Ready to operate?</h2><p className="sub">The Command Center runs the full workflow: radar, autopilot, promises, audit trail.</p><a className="btn gold" href="/console">Open the Command Center →</a></Reveal>
        <footer className="xp-foot">DhanRakshak · synthetic benchmark data, fictional customers · models: XGBoost on scikit-learn pipelines</footer>
      </section>
    </div>
  )
}

function Slider({ label: l, value, min, max, step, fmt, onChange }: { label: string; value: number; min: number; max: number; step: number; fmt: (v: number) => string; onChange: (v: number) => void }) {
  return <label className="slider"><span>{l}<b>{fmt(value)}</b></span><input type="range" min={min} max={max} step={step} value={value} style={{ ['--f' as string]: `${((value - min) / (max - min)) * 100}%` }} onChange={(e) => onChange(Number(e.target.value))} /></label>
}
function Chips({ label: l, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return <div className="chip-row"><span>{l}</span><div>{options.map((o) => <button key={o} className={o === value ? 'on' : ''} onClick={() => onChange(o)}>{label(o)}</button>)}</div></div>
}
