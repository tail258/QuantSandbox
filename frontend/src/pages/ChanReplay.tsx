import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ChevronLeft, ChevronRight, Download, FileUp, Pause, Play, SkipBack, SkipForward } from 'lucide-react'
import type { PageProps } from '../App'
import { download, fmt } from '../api'
import ChanChart from '../chan/ChanChart'
import { layers, stateAtFrame, type ChanEvent, type Layer, type Replay, type Snapshot } from '../chan/model'
import { request } from '../http'
import { t, useLocale } from '../i18n'
import { chanCopy, type ChanCopy } from '../i18n/chan'
import { useProject, withProject } from '../workspace/ProjectContext'
import './chan-replay.css'

const replayPath = '/chan/replay'
const chartSizes = [40, 80, 160] as const
const detailsPageSize = 12
const emptyDates: string[] = []

type Task = 'analyze' | 'demo' | 'import' | 'verify'

function readError(error: unknown) {
  return error instanceof Error ? error.message : ''
}

function description(event: ChanEvent, copy: ChanCopy) {
  if (event.layer === 'fractals') return `${copy[event.structure.kind]} · ${fmt(event.structure.price, 4)}`
  if (event.layer === 'centers') {
    const { phase, lower, upper, expansion_candidate, previous_range_relation } = event.structure
    const center = [copy.centers, copy[phase], `${fmt(lower, 4)}–${fmt(upper, 4)}`]
    if (expansion_candidate) center.push(copy.expansion)
    if (previous_range_relation) center.push(copy[previous_range_relation])
    return center.join(' · ')
  }
  if (event.layer === 'strokes' || event.layer === 'segments') {
    const { direction, start_price, end_price } = event.structure
    const rule = event.layer === 'segments' && event.structure.confirmation_rule
    const path = `${copy[event.layer]} · ${copy[direction]} · ${fmt(start_price, 4)} → ${fmt(end_price, 4)}`
    return rule ? `${path} · ${copy[rule]}` : path
  }
  return `${copy.merged_bars} · ${fmt(event.structure.low, 4)}–${fmt(event.structure.high, 4)}`
}

function EventTable({ events, copy, label, showAction = false }: {
  events: ChanEvent[]
  copy: ChanCopy
  label: string
  showAction?: boolean
}) {
  return <div className="chan-table-wrap" tabIndex={0}>
    <table aria-label={label}>
      <thead><tr>
        <th scope="col">{copy.structure}</th><th scope="col">{copy.dateSpan}</th><th scope="col">{copy.firstSeen}</th>
        <th scope="col">{copy.confirmation}</th><th scope="col">{copy.state}</th>
      </tr></thead>
      <tbody>{events.map((event, i) => {
        const row = event.structure
        const status = showAction ? copy[event.action === 'confirmed' ? 'confirmedEvent' : event.action] : copy[row.status]
        const position = event.layer === 'fractals' ? event.structure.date
          : row.start_date === row.end_date ? row.start_date : `${row.start_date} – ${row.end_date}`
        return <tr key={`${event.layer}:${row.id}:${i}`}>
          <th scope="row">{description(event, copy)}</th>
          <td>{position}</td>
          <td>{row.first_seen_date}</td>
          <td>{row.confirmed_date ?? '—'}</td>
          <td><span className={`chan-status ${row.status}`}>{status}</span></td>
        </tr>
      })}</tbody>
    </table>
  </div>
}

function FrameDetails({ live, changes, copy }: { live: ChanEvent[]; changes: ChanEvent[]; copy: ChanCopy }) {
  const [layer, setLayer] = useState<Layer>('segments')
  const [page, setPage] = useState(0)
  const rows = useMemo(() => live.filter(event => event.layer === layer).reverse(), [live, layer])
  const maxPage = Math.max(0, Math.ceil(rows.length / detailsPageSize) - 1)
  const currentPage = Math.min(page, maxPage)
  const counts = Object.fromEntries(layers.map(key => [key, 0])) as Record<Layer, number>
  for (const event of live) counts[event.layer]++

  return <>
    <section className="panel chan-section" aria-labelledby="chan-changes">
      <h2 id="chan-changes">{copy.changes}</h2>
      {changes.length
        ? <EventTable events={changes} copy={copy} label={copy.changes} showAction />
        : <p className="muted">{copy.noChanges}</p>}
    </section>
    <section className="panel chan-section" aria-labelledby="chan-inspect">
      <div className="chan-section-title">
        <h2 id="chan-inspect">{copy.detail}</h2>
        <label className="chan-inline-label">{copy.chooseLayer}
          <select value={layer} onChange={event => { setLayer(event.target.value as Layer); setPage(0) }}>
            {layers.map(key => <option key={key} value={key}>{copy[key]} ({counts[key]})</option>)}
          </select>
        </label>
      </div>
      {rows.length
        ? <EventTable events={rows.slice(currentPage * detailsPageSize, (currentPage + 1) * detailsPageSize)} copy={copy} label={copy[layer]} />
        : <p className="muted">{copy.noStructures}</p>}
      {maxPage > 0 && <div className="chan-details-pagination">
        <button type="button" className="secondary" aria-label={copy.priorPage} disabled={!currentPage}
          onClick={() => setPage(currentPage - 1)}><ChevronLeft size={15} aria-hidden="true" /></button>
        <span>{currentPage + 1} / {maxPage + 1}</span>
        <button type="button" className="secondary" aria-label={copy.nextPage} disabled={currentPage === maxPage}
          onClick={() => setPage(currentPage + 1)}><ChevronRight size={15} aria-hidden="true" /></button>
      </div>}
    </section>
  </>
}

function Timeline({ bars, result, input, copy }: Replay & { copy: ChanCopy }) {
  const last = result.frames.length - 1
  const [cursor, setCursor] = useState(last)
  const [playing, setPlaying] = useState(false)
  const [size, setSize] = useState<number>(80)
  const [visible, setVisible] = useState<Set<Layer>>(() => new Set(layers.filter(layer => layer !== 'merged_bars')))
  const frame = result.frames[cursor]
  const live = useMemo(() => frame ? stateAtFrame(result.events, frame) : [], [result.events, frame])
  const exDates = input.coverage?.cash_dividend_ex_dates ?? emptyDates
  const exDatesSet = useMemo(() => new Set(exDates), [exDates])
  const running = playing && cursor < last
  useEffect(() => {
    if (!running) return
    const timer = window.setTimeout(() => setCursor(cursor + 1), 550)
    return () => window.clearTimeout(timer)
  }, [running, cursor])
  if (!frame) return null

  function seek(index: number) {
    setPlaying(false)
    setCursor(index)
  }
  function togglePlay() {
    if (running) setPlaying(false)
    else {
      if (cursor === last) setCursor(0)
      setPlaying(true)
    }
  }
  function toggleLayer(layer: Layer) {
    setVisible(previous => {
      const next = new Set(previous)
      if (next.has(layer)) next.delete(layer)
      else next.add(layer)
      return next
    })
  }

  return <>
    <section className="panel chan-section chan-timeline" aria-labelledby="chan-observation">
      <div className="chan-section-title">
        <div>
          <div className="chan-observation-heading">
            <h2 id="chan-observation">{copy.date}</h2>
            {input.mode === 'synthetic' && <small>{copy.synthetic}</small>}
          </div>
          <div className="chan-observed-date">
            <time dateTime={frame.date}>{frame.date}</time>
            <span>{cursor + 1} / {last + 1}</span>
          </div>
        </div>
        <label className="chan-inline-label">{copy.range}
          <select value={size} onChange={event => setSize(Number(event.target.value))}>
            {chartSizes.map(count => <option value={count} key={count}>{count} {copy.candles}</option>)}
          </select>
        </label>
      </div>
      <ChanChart bars={bars} last={frame.index} size={size} structures={live} visible={visible} exDates={exDatesSet} copy={copy} />
      <div className="chan-scrub">
        <div className="chan-step-actions">
          <button type="button" className="secondary" aria-label={copy.first} disabled={!cursor} onClick={() => seek(0)}><SkipBack size={16} aria-hidden="true" /></button>
          <button type="button" className="secondary" aria-label={copy.previous} disabled={!cursor} onClick={() => seek(cursor - 1)}><ChevronLeft size={17} aria-hidden="true" /></button>
          <button type="button" className="chan-play" disabled={!last} onClick={togglePlay}>
            {running ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
            {running ? copy.pause : copy.play}
          </button>
          <button type="button" className="secondary" aria-label={copy.next} disabled={cursor === last} onClick={() => seek(cursor + 1)}><ChevronRight size={17} aria-hidden="true" /></button>
          <button type="button" className="secondary" aria-label={copy.latest} disabled={cursor === last} onClick={() => seek(last)}><SkipForward size={16} aria-hidden="true" /></button>
        </div>
        <input type="range" min="0" max={last} value={cursor} disabled={!last}
          aria-label={copy.timeline} aria-valuetext={frame.date} onChange={event => seek(Number(event.target.value))} />
      </div>
      <fieldset className="chan-layers">
        <legend>{copy.layers}</legend>
        {layers.map(layer => <label key={layer}>
          <input type="checkbox" checked={visible.has(layer)} onChange={() => toggleLayer(layer)} />
          <span className={`chan-layer-swatch ${layer}`} aria-hidden="true" />{copy[layer]}
        </label>)}
      </fieldset>
      <p className="chan-chart-key">{copy.statusKey}</p>
    </section>
    <FrameDetails live={live} changes={result.events.slice(frame.event_start, frame.event_end)} copy={copy} />
  </>
}

function SourceDetails({ replay, copy }: { replay: Replay; copy: ChanCopy }) {
  const { input, result } = replay
  const provenance = input.coverage
  function dates(rows: string[] | null) {
    return rows ? rows.join(', ') || copy.none : copy.unknown
  }
  const facts: [string, ReactNode][] = [
    [copy.snapshot, <code>{input.snapshot_id}</code>],
    [copy.priceBasis, input.price_basis === 'synthetic' ? copy.synthetic : copy.unadjusted],
    [copy.algorithm, <code>{result.algorithm}</code>],
    [copy.inputHash, <code>{input.sha256}</code>],
  ]
  if (input.project_id) facts.push([copy.archivedProject, <code>{input.project_id}</code>])
  if (input.source_sha256) facts.push([copy.sourceHash, <code>{input.source_sha256}</code>])
  if (input.fetched_at) facts.push([copy.fetched, input.fetched_at])
  if (input.source_url?.startsWith('https://')) {
    facts.push([copy.source, <a href={input.source_url} target="_blank" rel="noreferrer">{input.source}</a>])
  } else if (input.source) facts.push([copy.source, input.source])
  if (provenance && input.mode === 'project') facts.push(
    [copy.calendar, provenance.calendar_verified ? copy.calendarVerified : copy.calendarUnknown],
    [copy.suspended, dates(provenance.excluded_suspension_dates)],
    [copy.missing, dates(provenance.missing_session_dates)],
    [copy.unknownSuspension, fmt(provenance.unknown_suspension_count)],
    [copy.dividend, dates(provenance.cash_dividend_ex_dates)],
  )
  return <details className="chan-source-details">
    <summary>{copy.evidence}</summary>
    <dl className="chan-facts">{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {input.price_basis === 'raw_unadjusted' && <p className="muted">{copy.priceNote}</p>}
  </details>
}

function ChanWorkspace({ projectId, copy }: { projectId: string; copy: ChanCopy }) {
  const [selection, setSelection] = useState('')
  const [list, setList] = useState<Snapshot[] | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [active, setActive] = useState<{ replay: Replay; task: Task; revision: number } | null>(null)
  const [task, setTask] = useState<Task | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [verified, setVerified] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const filePicker = useRef<HTMLInputElement>(null)
  const resultHeader = useRef<HTMLHeadingElement>(null)
  const projectPath = `/projects/${encodeURIComponent(projectId)}/chan`
  const selected = list?.find(item => item.id === selection)

  useEffect(() => {
    if (!projectId) return
    const load = new AbortController()
    request<{ snapshots: Snapshot[] }>(`${projectPath}/snapshots`, { signal: load.signal })
      .then(response => setList(response.snapshots))
      .catch(reason => { if (!load.signal.aborted) setListError(readError(reason)) })
    return () => load.abort()
  }, [projectId, projectPath, reloadKey])
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => { if (active) resultHeader.current?.focus() }, [active])

  async function run(operation: Task, execute: (signal: AbortSignal) => Promise<Replay>) {
    if (controller.current) return
    const pending = new AbortController()
    controller.current = pending
    setTask(operation)
    setError(null)
    setVerified(false)
    try {
      const replay = await execute(pending.signal)
      if (pending.signal.aborted) return
      if ((operation === 'import' || operation === 'verify') && !replay.verified) {
        setError('evidenceMismatch')
        return
      }
      setVerified(Boolean(replay.verified))
      if (operation !== 'verify') setActive(current => ({ replay, task: operation, revision: (current?.revision ?? 0) + 1 }))
    } catch (reason) {
      if (!pending.signal.aborted) setError(readError(reason))
    } finally {
      if (controller.current === pending) {
        controller.current = null
        if (!pending.signal.aborted) setTask(null)
      }
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    void run('analyze', signal => request<Replay>(`${projectPath}/analyze`, {
      method: 'POST', body: JSON.stringify({ snapshot_id: selected.id }), signal,
    }))
  }

  async function replayEvidence(body: string, signal: AbortSignal) {
    return request<Replay>(replayPath, { method: 'POST', body, signal })
  }

  const replay = active?.replay
  return <div className="chan-workspace">
    <div className="page-title">
      <div><h1>{copy.title}</h1><p>{copy.intro}</p></div>
    </div>
    <section className="panel chan-section" aria-labelledby="chan-input">
      <h2 id="chan-input">{copy.source}</h2>
      {projectId && list === null && listError === null && <p className="muted" role="status">{copy.loading}</p>}
      {listError !== null && <div className="chan-source-actions">
        <p role="alert">{listError ? t(listError) : copy.failed}</p>
        <button type="button" className="secondary" onClick={() => {
          setList(null)
          setListError(null)
          setReloadKey(value => value + 1)
        }}>{copy.retry}</button>
      </div>}
      {!projectId && <p className="muted">{copy.noProject}</p>}
      {list?.length === 0 && <p className="muted">{copy.noSnapshots} <a href={`#${withProject('data', projectId)}`}>{copy.openData}</a></p>}
      {list && list.length > 0 && <form className="chan-source-form" onSubmit={submit}>
        <label>{copy.project}
          <select value={selected?.id ?? ''} onChange={event => setSelection(event.target.value)}>
            <option value="">{copy.pick}</option>
            {list.map(snapshot => <option key={snapshot.id} value={snapshot.id}>
              {snapshot.symbol} · {snapshot.start_date} – {snapshot.end_date} · {snapshot.source} · {snapshot.id.slice(0, 8)}
            </option>)}
          </select>
        </label>
        <button type="submit" disabled={!selected || task !== null}>{copy.load}</button>
      </form>}
      <div className="chan-source-actions">
        <button type="button" className="secondary" disabled={task !== null}
          onClick={() => void run('demo', signal => request<Replay>('/chan/demo', { method: 'POST', signal }))}>
          <Play size={15} aria-hidden="true" />{copy.demo}
        </button>
        <button type="button" className="secondary" disabled={task !== null} onClick={() => filePicker.current?.click()}>
          <FileUp size={15} aria-hidden="true" />{copy.openEvidence}
        </button>
        <input ref={filePicker} type="file" accept=".json,application/json" aria-label={copy.openEvidence} hidden
          onChange={event => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) void run('import', async signal => replayEvidence(await file.text(), signal))
          }} />
        {task !== null && <span className="muted" role="status">{copy.working}</span>}
      </div>
      {error !== null && <p className="chan-error" role="alert">{error === 'evidenceMismatch' ? copy.evidenceMismatch : error ? t(error) : copy.failed}</p>}
    </section>
    {active && replay && <>
      <section className="panel chan-section chan-run" aria-labelledby="chan-result">
        <div className="chan-section-title">
          <div>
            <h2 tabIndex={-1} ref={resultHeader} id="chan-result">
              {replay.input.mode === 'synthetic' ? copy.synthetic : replay.input.symbol}
              {active.task === 'import' && <small className="chan-import-tag">{copy.imported}</small>}
            </h2>
            <p className="muted">{copy.coverage} · {replay.input.start_date} – {replay.input.end_date} · {copy.candleCount} {fmt(replay.bars.length)}</p>
          </div>
          <div className="chan-source-actions">
            <button type="button" className="secondary" disabled={task !== null}
              onClick={() => download(`chan-${replay.input.sha256.slice(0, 12)}.json`, replay.evidence, 'application/json')}>
              <Download size={15} aria-hidden="true" />{copy.download}
            </button>
            <button type="button" className="secondary" disabled={task !== null}
              onClick={() => void run('verify', signal => replayEvidence(replay.evidence, signal))}>{copy.verify}</button>
          </div>
        </div>
        {verified && <p className="chan-verified" role="status">{copy.verified}</p>}
        <SourceDetails replay={replay} copy={copy} />
      </section>
      <Timeline key={active.revision} {...replay} copy={copy} />
    </>}
  </div>
}

export default function ChanPage(_props: PageProps) {
  const copy = chanCopy(useLocale())
  const { activeProject } = useProject()
  const projectId = activeProject?.id ?? ''
  return <ChanWorkspace key={projectId} projectId={projectId} copy={copy} />
}
