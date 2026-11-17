import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { download, fmt } from '../api'
import { request } from '../http'
import { useLocale } from '../i18n'
import { strategyDemoCopy, type StrategyDemoCopy as Copy } from '../i18n/strategyDemo'
import './strategy-demo.css'

type Windows = { fast_period: number; slow_period: number }
type Point = { date: string; equity: number; benchmark: number }
type Fill = {
  date: string
  signal_date: string
  action: 'buy' | 'sell'
  price: number
  shares: number
  fee: number
  evidence: { execution_open: number }
}
type DemoRun = {
  synthetic: true
  snapshot: { sha256: string; start_date: string; end_date: string; rows: number; version: string; suspension_dates: string[] }
  parameters: Windows
  period: { start_date: string; end_date: string; observations: number; warmup_rows: number }
  account: { initial_cash: number; commission_rate: number; tax_rate: number; min_commission: number; slippage_bps: number; position_size: number }
  metrics: { total_return: number; benchmark_return: number; max_drawdown: number; trade_count: number; total_fees: number }
  series: Point[]
  trades: Fill[]
  result_sha256: string
  evidence: string
}
type Replay = {
  synthetic: true
  matched: boolean
  snapshot_sha256: string
  result_sha256: string
  compared_fields: string[]
  different_fields: string[]
}
type Target = 'baseline' | 'comparison'
type Operation = Target | 'replay'
type RunNotice = 'invalidWindows' | 'sameWindows' | 'snapshotChanged' | 'runFailed'

const runPath = '/demo/strategy/run'
const replayPath = '/demo/strategy/replay'
const percent = (value: number, precision = 2) => `${fmt(value, precision)}%`
const windowPair = ({ fast_period, slow_period }: Windows) => `${fast_period} / ${slow_period}`
const dates = ({ start_date, end_date }: DemoRun['period'] | DemoRun['snapshot']) => `${start_date} – ${end_date}`

function Step({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return <section className="panel strategy-demo-step" aria-labelledby={`strategy-demo-step-${number}`}>
    <h2 id={`strategy-demo-step-${number}`}><span aria-hidden="true">{number}</span>{title}</h2>
    {children}
  </section>
}

function Facts({ items }: { items: [string, ReactNode][] }) {
  return <dl className="strategy-demo-facts">
    {items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
  </dl>
}

function ReturnChart({ baseline, comparison, copy }: { baseline: DemoRun; comparison: DemoRun | null; copy: Copy }) {
  const chart = [
    { type: 'benchmark', label: copy.benchmark, values: baseline.series.map((row) => row.benchmark) },
    { type: 'baseline', label: copy.baseline, values: baseline.series.map((row) => row.equity) },
    ...(comparison ? [{ type: 'comparison', label: copy.comparison, values: comparison.series.map((row) => row.equity) }] : []),
  ].map((line) => ({ ...line, returns: [0, ...line.values.map((value) => (value / baseline.account.initial_cash - 1) * 100)] }))
  let low = 0
  let high = 0
  for (const line of chart) {
    for (const value of line.returns) {
      low = Math.min(low, value)
      high = Math.max(high, value)
    }
  }
  const left = 4, right = 596, top = 8, bottom = 143
  const span = high - low || 1
  const y = (value: number) => bottom - (value - low) / span * (bottom - top)
  return <figure className="strategy-demo-chart">
    <figcaption>{copy.chart}</figcaption>
    <div className="strategy-demo-plot">
      <div className="strategy-demo-axis" aria-hidden="true"><span>{percent(high, 1)}</span><span>{percent(low, 1)}</span></div>
      <svg viewBox="0 0 600 151" preserveAspectRatio="none" role="img" aria-label={copy.chart}>
        <line className="strategy-demo-zero" x1={left} x2={right} y1={y(0)} y2={y(0)} vectorEffect="non-scaling-stroke" />
        {chart.map((line) => <polyline key={line.type} className={`strategy-demo-line ${line.type}`} vectorEffect="non-scaling-stroke" points={line.returns.map((value, index) => `${(left + index / (line.returns.length - 1) * (right - left)).toFixed(1)},${y(value).toFixed(1)}`).join(' ')} />)}
      </svg>
    </div>
    <div className="strategy-demo-dates"><span>{baseline.period.start_date}</span><span>{baseline.period.end_date}</span></div>
    <ul className="strategy-demo-key">
      {chart.map((line) => <li key={line.type}><span className={`strategy-demo-swatch ${line.type}`} aria-hidden="true" />{line.label}</li>)}
    </ul>
  </figure>
}

function Results({ baseline, comparison, copy }: { baseline: DemoRun; comparison: DemoRun | null; copy: Copy }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [baseline, comparison])
  function values(run: DemoRun) {
    return [percent(run.metrics.total_return), percent(run.metrics.max_drawdown), fmt(run.metrics.trade_count), fmt(run.metrics.total_fees)]
  }
  const baseValues = values(baseline)
  const comparisonValues = comparison ? values(comparison) : null
  const benchmarkValues = [percent(baseline.metrics.benchmark_return), '—', '—', '—']
  return <section className="panel strategy-demo-results" aria-labelledby="strategy-demo-results">
    <h2 id="strategy-demo-results" tabIndex={-1} ref={heading}>{copy.results}</h2>
    <Facts items={[
      [copy.period, dates(baseline.period)],
      [copy.observations, fmt(baseline.period.observations)],
      [copy.warmup, fmt(baseline.period.warmup_rows)],
      [copy.suspended, baseline.snapshot.suspension_dates.join(', ') || copy.none],
    ]} />
    <div className="strategy-demo-result-table">
      <table aria-label={copy.results}>
        <thead><tr>
          <th scope="col">{copy.metric}</th>
          <th scope="col">{copy.baseline}<small>{windowPair(baseline.parameters)}</small></th>
          {comparison && <th scope="col">{copy.comparison}<small>{windowPair(comparison.parameters)}</small></th>}
          <th scope="col">{copy.benchmark}</th>
        </tr></thead>
        <tbody>{[copy.return, copy.drawdown, copy.trades, copy.fees].map((label, i) => <tr key={label}>
          <th scope="row">{label}</th><td>{baseValues[i]}</td>
          {comparisonValues && <td>{comparisonValues[i]}</td>}
          <td>{benchmarkValues[i]}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <ReturnChart baseline={baseline} comparison={comparison} copy={copy} />
    <p className="strategy-demo-caption">{copy.interpretation}</p>
    <details>
      <summary>{copy.assumptions}</summary>
      <Facts items={[
        [copy.datasetVersion, baseline.snapshot.version], [copy.snapshotPeriod, dates(baseline.snapshot)],
        [copy.snapshotRows, fmt(baseline.snapshot.rows)], [copy.snapshotHash, <code>{baseline.snapshot.sha256}</code>],
        [copy.initialCash, fmt(baseline.account.initial_cash)], [copy.maxPosition, percent(baseline.account.position_size * 100)],
        [copy.commission, percent(baseline.account.commission_rate * 100, 4)], [copy.minimumCommission, fmt(baseline.account.min_commission)],
        [copy.sellTax, percent(baseline.account.tax_rate * 100, 4)], [copy.slippage, fmt(baseline.account.slippage_bps)],
      ]} />
    </details>
  </section>
}

function FirstFill({ run, copy }: { run: DemoRun; copy: Copy }) {
  const fill = run.trades[0]
  return <details>
    <summary>{copy.executionExample}</summary>
    {fill ? <Facts items={[
      [copy.action, copy[fill.action]], [copy.closeDate, fill.signal_date], [copy.fillDate, fill.date],
      [copy.openPrice, fmt(fill.evidence.execution_open, 4)], [copy.fillPrice, fmt(fill.price, 4)],
      [copy.shares, fmt(fill.shares)], [copy.fee, fmt(fill.fee)],
    ]} /> : <p>{copy.noFills}</p>}
  </details>
}

function ReplayResult({ result, original, copy }: { result: Replay; original: DemoRun; copy: Copy }) {
  const hashMismatch = result.snapshot_sha256 !== original.snapshot.sha256 || result.result_sha256 !== original.result_sha256
  const matched = result.matched && !hashMismatch
  const fieldLabel = (field: string) => {
    const fields: Record<string, string> = { metrics: copy.metricsField, series: copy.seriesField, trades: copy.tradesField, decisions: copy.decisionsField }
    return fields[field] ?? field
  }
  return <div className={`strategy-demo-verification${matched ? ' matched' : ''}`} role={matched ? 'status' : 'alert'}>
    <strong>{matched ? copy.replayMatch : copy.replayMismatch}</strong>
    <p>{copy.compared}: {result.compared_fields.map(fieldLabel).join(', ') || copy.none}</p>
    {!matched && <p>{copy.different}: {result.different_fields.map(fieldLabel).join(', ') || copy.none}</p>}
    {hashMismatch && <p>{copy.hashMismatch}</p>}
    <p>{copy.resultHash}: <code>{result.result_sha256}</code></p>
  </div>
}

export default function StrategyDemo() {
  const copy = strategyDemoCopy[useLocale()]
  const [baseline, setBaseline] = useState<DemoRun | null>(null)
  const [comparison, setComparison] = useState<DemoRun | null>(null)
  const [fast, setFast] = useState('')
  const [slow, setSlow] = useState('')
  const [target, setTarget] = useState<Target>('baseline')
  const [replay, setReplay] = useState<Replay | null>(null)
  const [busy, setBusy] = useState<Operation | null>(null)
  const [runNotice, setRunNotice] = useState<RunNotice | null>(null)
  const [replayError, setReplayError] = useState(false)
  const pending = useRef<AbortController | null>(null)
  const selected = target === 'comparison' ? comparison : baseline
  const invalidWindows = runNotice === 'invalidWindows' || runNotice === 'sameWindows'

  useEffect(() => () => pending.current?.abort(), [])

  async function perform<T>(operation: Operation, path: string, payload: unknown, onSuccess: (result: T) => void) {
    if (pending.current) return
    const controller = new AbortController()
    pending.current = controller
    setBusy(operation)
    try {
      const result = await request<T>(path, { method: 'POST', body: JSON.stringify(payload), signal: controller.signal })
      if (!controller.signal.aborted) onSuccess(result)
    } catch {
      if (!controller.signal.aborted) {
        if (operation === 'replay') setReplayError(true)
        else setRunNotice('runFailed')
      }
    } finally {
      pending.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  function runBaseline() {
    setRunNotice(null)
    void perform<DemoRun>('baseline', runPath, {}, (result) => {
      setBaseline(result)
      setFast(String(result.parameters.fast_period))
      setSlow(String(result.parameters.slow_period))
    })
  }

  function runComparison(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!baseline) return
    const fast_period = Number(fast), slow_period = Number(slow)
    if (!Number.isInteger(fast_period) || !Number.isInteger(slow_period) || fast_period < 2 || fast_period >= slow_period || slow_period > 60) {
      setRunNotice('invalidWindows')
      return
    }
    if (fast_period === baseline.parameters.fast_period && slow_period === baseline.parameters.slow_period) {
      setRunNotice('sameWindows')
      return
    }
    setRunNotice(null)
    void perform<DemoRun>('comparison', runPath, { fast_period, slow_period }, (result) => {
      if (result.snapshot.sha256 !== baseline.snapshot.sha256) {
        setRunNotice('snapshotChanged')
        return
      }
      setComparison(result)
      setTarget('comparison')
      setReplay(null)
      setReplayError(false)
    })
  }

  function replayEvidence() {
    if (!selected) return
    setReplay(null)
    setReplayError(false)
    // Treat the bundle as an opaque string; parsing/reformatting would change the original evidence.
    void perform<Replay>('replay', replayPath, { evidence: selected.evidence }, setReplay)
  }

  return <div className="strategy-demo">
    <header className="strategy-demo-header">
      <p className="strategy-demo-badge">{copy.eyebrow}</p>
      <h1>{copy.title}</h1>
      <p>{copy.intro}</p>
      <p className="strategy-demo-caption">{copy.scope}</p>
    </header>
    <Step number="01" title={copy.questionStep}>
      <p className="strategy-demo-question">{copy.question}</p>
      <p>{copy.rule}</p>
      {!baseline && <button type="button" onClick={runBaseline} disabled={busy !== null}>{busy === 'baseline' ? copy.calculating : copy.runBaseline}</button>}
      {!baseline && runNotice && <p className="strategy-demo-alert" role="alert">{copy[runNotice]}</p>}
    </Step>
    {baseline && <Results baseline={baseline} comparison={comparison} copy={copy} />}
    <Step number="02" title={copy.changeStep}>
      {baseline ? <>
        <p>{copy.changeHint}</p>
        <form className="strategy-demo-controls" noValidate onSubmit={runComparison}>
          <label>{copy.fast}<input type="number" min="2" max="59" step="1" value={fast} aria-invalid={invalidWindows || undefined} aria-describedby={invalidWindows ? 'strategy-demo-window-error' : undefined} onChange={(e) => { setFast(e.target.value); setRunNotice(null) }} disabled={busy !== null} /></label>
          <label>{copy.slow}<input type="number" min="3" max="60" step="1" value={slow} aria-invalid={invalidWindows || undefined} aria-describedby={invalidWindows ? 'strategy-demo-window-error' : undefined} onChange={(e) => { setSlow(e.target.value); setRunNotice(null) }} disabled={busy !== null} /></label>
          <button type="submit" disabled={busy !== null}>{busy === 'comparison' ? copy.calculating : copy.runComparison}</button>
        </form>
        {runNotice && <p id="strategy-demo-window-error" className="strategy-demo-alert" role="alert">{copy[runNotice]}</p>}
      </> : <p className="strategy-demo-caption">{copy.needBaseline}</p>}
    </Step>
    <Step number="03" title={copy.replayStep}>
      {selected ? <>
        <p>{copy.replayHint}</p>
        <div className="strategy-demo-controls">
          <label>{copy.replayTarget}<select value={target} onChange={(e) => { setTarget(e.target.value === 'comparison' ? 'comparison' : 'baseline'); setReplay(null); setReplayError(false) }} disabled={busy !== null}>
            {baseline && <option value="baseline">{copy.baseline} · {windowPair(baseline.parameters)}</option>}
            {comparison && <option value="comparison">{copy.comparison} · {windowPair(comparison.parameters)}</option>}
          </select></label>
          <button type="button" onClick={replayEvidence} disabled={busy !== null}>{busy === 'replay' ? copy.replaying : copy.replay}</button>
          <button type="button" className="secondary" onClick={() => download(`quantsandbox-synthetic-${target}-evidence.json`, selected.evidence, 'application/json')} disabled={busy !== null}>{copy.download}</button>
        </div>
        {replayError && <p className="strategy-demo-alert" role="alert">{copy.replayFailed}</p>}
        {replay && <ReplayResult result={replay} original={selected} copy={copy} />}
        <FirstFill run={selected} copy={copy} />
      </> : <p className="strategy-demo-caption">{copy.needBaseline}</p>}
    </Step>
  </div>
}
