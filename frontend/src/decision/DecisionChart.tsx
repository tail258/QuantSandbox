import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'
import { fmt } from '../api'
import { layers, type Candle, type ChanEvent, type Layer } from '../chan/model'
import { useLocale } from '../i18n'
import { chanCopy } from '../i18n/chan'
import './decision-chart.css'

export type DecisionLevel = {
  role: 'support' | 'resistance' | 'reference_target'
  price: number
  evidence: { layer: Layer; id: string; index: number; geometry_date: string; confirmed_date: string }
}

type Props = {
  bars: Candle[]
  structures: ChanEvent[]
  levels: DecisionLevel[]
  selectedId: string | null
  selectedRole?: DecisionLevel['role'] | null
  onSelect: (id: string, role?: DecisionLevel['role']) => void
  volumeUnit: string
  period?: 'daily' | 'weekly'
  structureLabels?: Readonly<Record<string, string>>
  observations?: readonly ChartObservation[]
}

export type ChartObservation = { id: string; index: number; geometry: string; available: string; title: string }
const emptyObservations: readonly ChartObservation[] = []

const copy = {
  en: {
    title: 'Daily price and volume', empty: 'No daily candles available.', weeklyTitle: 'Weekly price and volume', weeklyEmpty: 'No verified completed weeks available.',
    weeklyLatest: 'Show latest weeks', volume: 'Volume', shares: 'shares', units: 'units',
    support: 'Support', resistance: 'Resistance', reference_target: 'Reference target', priceLevels: 'Price levels',
    window: 'Candles shown', latest: 'Show latest candles', locate: 'Locate selected evidence',
    evidence: 'Chart evidence', geometry: 'Chart date', controls: 'Chart layers', currentLevels: 'Price levels are from the latest close.',
    key: 'Solid or filled marks are confirmed · dashed or hollow marks are provisional',
    observation: 'Center retests on their confirmation dates',
  },
  zh: {
    title: '日线价格与成交量', empty: '暂无日线。', weeklyTitle: '周线价格与成交量', weeklyEmpty: '暂无可核验的完整周线。',
    weeklyLatest: '回到最新周线', volume: '成交量', shares: '股', units: '份',
    support: '支撑', resistance: '压力', reference_target: '观察目标', priceLevels: '关键价位',
    window: '显示根数', latest: '回到最新日线', locate: '定位所选证据',
    evidence: '图上证据', geometry: '图上日期', controls: '图层', currentLevels: '图中价位以快照最后一根日线为准。',
    key: '实线或实心为已确认 · 虚线或空心为待确认',
    observation: '中枢外侧回抽（按确认日标记）',
  },
}

const height = 414
const priceTop = 17
const priceBottom = 286
const volumeTop = 310
const volumeBottom = 384
const chartWindows = [40, 80, 160]
const weekWindows = [12, 26, 52]

type Marker = {
  key: string
  id: string
  index: number
  price: number
  title: string
  status: 'candidate' | 'confirmed'
  geometry: string
  firstSeen?: string
  confirmed: string | null
  role?: DecisionLevel['role']
}

function structureMarker(event: ChanEvent, words: ReturnType<typeof chanCopy>, label?: string): Marker {
  const { structure, layer } = event
  let index = structure.end_index
  let price = (structure.high + structure.low) / 2
  let title: string = words[layer]
  let geometry = structure.end_date
  if (layer === 'fractals') {
    index = event.structure.index
    price = event.structure.price
    title = `${words[event.structure.kind]} · ${fmt(price, 3)}`
    geometry = event.structure.date
  } else if (layer === 'strokes' || layer === 'segments') {
    price = event.structure.end_price
    title = `${title} · ${words[event.structure.direction]} · ${fmt(event.structure.start_price, 3)} → ${fmt(price, 3)}`
    if (layer === 'segments' && event.structure.confirmation_rule) {
      title += ` · ${words[event.structure.confirmation_rule]}`
    }
  } else if (layer === 'centers') {
    const { lower, upper, phase } = event.structure
    price = (upper + lower) / 2
    title = `${title} · ${words[phase]} · ${fmt(lower, 3)}–${fmt(upper, 3)}`
  } else {
    title = `${title} · ${fmt(structure.low, 3)}–${fmt(structure.high, 3)}`
  }
  if (label) title = `${label} · ${title}`
  return { key: `${layer}:${structure.id}`, id: structure.id, index, price, title, status: structure.status,
    geometry, firstSeen: structure.first_seen_date, confirmed: structure.confirmed_date }
}

function displayLabel(marker: Marker, words: ReturnType<typeof chanCopy>) {
  return `${marker.title} · ${marker.geometry} · ${words[marker.status]}${marker.confirmed ? ` · ${words.confirmation} ${marker.confirmed}` : ''}`
}

export default function DecisionChart({ bars, structures, levels, selectedId, selectedRole, onSelect, volumeUnit, structureLabels,
  period = 'daily', observations = emptyObservations }: Props) {
  const locale = useLocale()
  const words = chanCopy(locale)
  const ui = copy[locale]
  const titleId = useId()
  const plotId = useId()
  const chart = useRef<HTMLDivElement>(null)
  const focusNodes = useRef(new Map<string, SVGGElement>())
  const [width, setWidth] = useState(900)
  const weekly = period === 'weekly'
  const [range, setRange] = useState(weekly ? 26 : 80)
  const [visible, setVisible] = useState(() => new Set<Layer>(layers.filter(layer => layer !== 'merged_bars')))
  const [showLevels, setShowLevels] = useState(true)
  const [showObservations, setShowObservations] = useState(true)
  const [ignoredSelection, setIgnoredSelection] = useState<string | null>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [hoverKey, setHoverKey] = useState<string | null>(null)
  const [focusedKey, setFocusedKey] = useState<string | null>(null)
  const [focusInChart, setFocusInChart] = useState(false)
  const compact = useMemo(() => new Intl.NumberFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    notation: 'compact', maximumFractionDigits: 1,
  }), [locale])

  const hasBars = bars.length > 0
  useEffect(() => {
    const node = chart.current
    if (!node) return
    function measure() {
      if (node && node.clientWidth > 0) setWidth(node.clientWidth)
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasBars])

  const markedStructures = useMemo(() => structures.filter(event => event.action !== 'removed').map(event => ({
    event, marker: structureMarker(event, words, structureLabels?.[event.structure.id]),
  })), [structures, words, structureLabels, locale])
  if (!hasBars) return <p className="decision-chart-empty">{weekly ? ui.weeklyEmpty : ui.empty}</p>

  const levelMarkers = levels.map(level => ({
    level,
    marker: {
      key: `level:${level.role}:${level.evidence.id}`, id: level.evidence.id,
      index: level.evidence.index, price: level.price, title: `${ui[level.role]} ${fmt(level.price, 3)}`,
      status: 'confirmed', geometry: level.evidence.geometry_date, confirmed: level.evidence.confirmed_date,
      firstSeen: markedStructures.find(item => item.marker.id === level.evidence.id)?.marker.firstSeen, role: level.role,
    } satisfies Marker,
  }))
  const observationMarkers: Marker[] = observations.filter(item => item.index >= 0 && item.index < bars.length).map(item => ({
    key: `observation:${item.id}`, id: item.id, index: item.index, price: bars[item.index].close, title: item.title,
    status: 'confirmed', geometry: item.geometry, confirmed: item.available,
  }))
  const storedMarker = markedStructures.find(item => item.marker.id === selectedId)?.marker
    ?? observationMarkers.find(marker => marker.id === selectedId)
  const matchingLevels = levelMarkers.filter(item => item.marker.id === selectedId)
  const selectedLevel = matchingLevels.find(item => item.level.role === selectedRole)?.marker
  const selected = selectedLevel ?? storedMarker ?? matchingLevels[0]?.marker
  const last = bars.length - 1
  const latestStart = Math.max(0, last - range + 1)
  const anchorEarlier = selected && selected.index >= 0 && selected.index < latestStart
  const showLatest = ignoredSelection === selected?.key
  const end = anchorEarlier && !showLatest ? Math.min(last, selected.index + Math.floor(range / 2)) : last
  const start = Math.max(0, end - range + 1)
  const candles = bars.slice(start, end + 1)
  const selectedInView = selected && selected.index >= start && selected.index <= end
  const showing = markedStructures.filter(({ event, marker }) => visible.has(event.layer) && (
    event.layer === 'fractals' ? marker.index >= start && marker.index <= end
      : event.structure.end_index >= start && event.structure.start_index <= end
  ) && (event.layer !== 'merged_bars' || event.structure.end_index > event.structure.start_index))
  const shownLevels = showLevels ? levelMarkers : []
  const shownObservations = showObservations ? observationMarkers.filter(marker => marker.index >= start && marker.index <= end) : []
  const interactiveMarkers = [...showing.map(item => item.marker), ...shownLevels.map(item => item.marker), ...shownObservations]
    .sort((left, right) => left.index - right.index)
  const activeMarker = interactiveMarkers.find(marker => marker.key === focusedKey)
    ?? interactiveMarkers.find(marker => marker.key === selected?.key) ?? interactiveMarkers.at(-1)
  const detail = interactiveMarkers.find(marker => marker.key === hoverKey) ?? (focusInChart ? activeMarker : undefined) ?? selected

  const values = shownLevels.map(({ level }) => level.price)
  if (selectedInView) values.push(selected.price)
  const low = Math.min(...candles.map(bar => bar.low), ...values)
  const high = Math.max(...candles.map(bar => bar.high), ...values)
  const span = high - low || Math.abs(high) * 0.02 || 1
  const minimum = low - span * 0.07
  const maximum = high + span * 0.07
  const maxVolume = Math.max(1, ...candles.map(bar => bar.volume))
  const plotLeft = 6
  const plotRight = Math.max(plotLeft + 1, width - 57)
  const step = (plotRight - plotLeft) / candles.length
  const candleWidth = Math.min(14, Math.max(step * 0.65, 0.7))
  const x = (index: number) => plotLeft + (index - start + 0.5) * step
  const y = (price: number) => priceTop + (maximum - price) / (maximum - minimum) * (priceBottom - priceTop)
  const volumeY = (value: number) => volumeBottom - (value / maxVolume) * (volumeBottom - volumeTop)
  const comparison = hoverIndex !== null && hoverIndex >= start && hoverIndex <= end ? hoverIndex : end
  const inspected = bars[comparison]
  const unit = volumeUnit === 'shares' || volumeUnit === 'units' ? ui[volumeUnit] : volumeUnit
  const dateTickCount = width < 475 ? 4 : 7
  const dates = [...new Set(Array.from({ length: dateTickCount }, (_, index) => start + Math.round(index * (end - start) / (dateTickCount - 1))))]
  const prices = Array.from({ length: 6 }, (_, index) => maximum - index * (maximum - minimum) / 5)
  const priceLabels = [...shownLevels.map(({ marker }) => ({ key: marker.key, at: y(marker.price) })),
    { key: 'close', at: y(candles[candles.length - 1].close) }].sort((left, right) => left.at - right.at)
  for (let i = 0; i < priceLabels.length; i++) {
    const floor = i ? priceLabels[i - 1].at + 17 : priceTop
    priceLabels[i].at = Math.max(priceLabels[i].at, floor)
  }
  for (let i = priceLabels.length - 1; i >= 0; i--) {
    const ceiling = i === priceLabels.length - 1 ? priceBottom : priceLabels[i + 1].at - 17
    priceLabels[i].at = Math.min(priceLabels[i].at, ceiling)
  }

  function select(marker: Marker) {
    setIgnoredSelection(null)
    onSelect(marker.id, marker.role)
  }

  function navigate(event: KeyboardEvent<SVGGElement>, marker: Marker) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      select(marker)
      return
    }
    const offset = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
    if (!offset && event.key !== 'Home' && event.key !== 'End') return
    event.preventDefault()
    const index = interactiveMarkers.findIndex(item => item.key === marker.key)
    const next = event.key === 'Home' ? interactiveMarkers[0] : event.key === 'End' ? interactiveMarkers.at(-1) : interactiveMarkers[index + offset]
    if (next) focusNodes.current.get(next.key)?.focus()
  }

  function inspectCandle(event: PointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect()
    if (!bounds.width) return
    const point = (event.clientX - bounds.left) * width / bounds.width
    const index = start + Math.floor((point - plotLeft) / step)
    setHoverIndex(index >= start && index <= end ? index : null)
  }

  function plotMarker(marker: Marker, classes: string, shape: ReactNode) {
    return <g key={marker.key} ref={node => {
      if (node) focusNodes.current.set(marker.key, node)
      else focusNodes.current.delete(marker.key)
    }} role="button" tabIndex={marker.key === activeMarker?.key ? 0 : -1}
      aria-label={displayLabel(marker, words)} aria-pressed={selected?.key === marker.key}
      aria-keyshortcuts="ArrowLeft ArrowRight Home End"
      data-evidence-id={marker.id} className={`decision-marker ${classes} ${marker.status}`}
      onClick={() => select(marker)} onKeyDown={event => navigate(event, marker)}
      onPointerEnter={() => setHoverKey(marker.key)} onPointerLeave={() => setHoverKey(null)}
      onFocus={() => { setFocusedKey(marker.key); setFocusInChart(true) }} onBlur={() => setFocusInChart(false)}>
      <title>{displayLabel(marker, words)}</title>
      {shape}
    </g>
  }

  function structuresIn(behind: boolean) {
    return showing.filter(({ event }) => (event.layer === 'centers' || event.layer === 'merged_bars') === behind).map(({ event, marker }) => {
      const { layer, structure } = event
      const left = x(structure.start_index) - candleWidth / 2
      const right = x(structure.end_index) + candleWidth / 2
      if (layer === 'merged_bars' || layer === 'centers') {
        const top = y(layer === 'centers' ? event.structure.upper : structure.high)
        const bottom = y(layer === 'centers' ? event.structure.lower : structure.low)
        return plotMarker(marker, `decision-structure ${layer}`, <rect className="decision-shape decision-block"
          x={left} y={top} width={right - left} height={Math.max(1, bottom - top)} />)
      }
      if (layer === 'fractals') {
        const cx = x(marker.index)
        const isTop = event.structure.kind === 'top'
        const cy = y(marker.price) + (isTop ? -8 : 8)
        const direction = isTop ? -1 : 1
        const label = structureLabels?.[marker.id]
        return plotMarker(marker, `decision-structure ${layer}`, <>
          <circle className="decision-marker-hit" cx={cx} cy={cy} r="11" />
          <path className="decision-shape decision-fractal" d={`M ${cx} ${cy + direction * 5} l 5 ${-direction * 8} h -10 Z`} />
          {label && <text className="decision-marker-text" x={cx} y={cy + (isTop ? -10 : 16)} textAnchor="middle">{label}</text>}
        </>)
      }
      const { start_price, end_price } = event.structure
      const line = { x1: x(structure.start_index), x2: x(structure.end_index), y1: y(start_price), y2: y(end_price) }
      return plotMarker(marker, `decision-structure ${layer}`, <>
        <line className="decision-marker-hit" {...line} /><line className="decision-shape" {...line} />
      </>)
    })
  }

  function labelAt(key: string, price: number) {
    const trueY = y(price)
    const labelY = priceLabels.find(item => item.key === key)?.at ?? trueY
    return <>
      <line className="decision-price-connector" x1={plotRight} x2={plotRight + 4} y1={trueY} y2={labelY} />
      <rect className="decision-price-label" x={plotRight + 4} y={labelY - 8} rx="3" width="51" height="16" />
      <text className="decision-price-label-text" x={plotRight + 29.5} y={labelY} dominantBaseline="central" textAnchor="middle">{fmt(price, 3)}</text>
    </>
  }

  return <figure className="decision-chart" aria-labelledby={titleId}>
    <figcaption className="decision-chart-toolbar">
      <strong id={titleId}>{weekly ? ui.weeklyTitle : ui.title}</strong>
      <div className="decision-chart-window">
        {anchorEarlier && <button type="button" className="text-button" onClick={() => setIgnoredSelection(showLatest ? null : selected.key)}>
          {showLatest ? ui.locate : weekly ? ui.weeklyLatest : ui.latest}
        </button>}
        <label>{ui.window}<select value={range} onChange={event => { setRange(Number(event.target.value)); setHoverIndex(null) }}>
          {(weekly ? weekWindows : chartWindows).map(size => <option key={size} value={size}>{size}</option>)}
        </select></label>
      </div>
    </figcaption>
    <fieldset className="decision-chart-layers" aria-label={ui.controls}>
      {layers.map(layer => <label key={layer}>
        <input type="checkbox" checked={visible.has(layer)} onChange={() => setVisible(previous => {
          const next = new Set(previous)
          if (next.has(layer)) next.delete(layer)
          else next.add(layer)
          return next
        })} />
        <span className={`decision-layer-swatch ${layer}`} aria-hidden="true" />{words[layer]}
      </label>)}
      {levels.length > 0 && <label><input type="checkbox" checked={showLevels} onChange={() => setShowLevels(value => !value)} />{ui.priceLevels}</label>}
      {observations.length > 0 && <label><input type="checkbox" checked={showObservations} onChange={() => setShowObservations(value => !value)} />{ui.observation}</label>}
    </fieldset>
    <div className="decision-ohlcv">
      <time dateTime={inspected.date}>{inspected.date}</time>
      <span>{words.open} <b>{fmt(inspected.open, 3)}</b></span><span>{words.high} <b>{fmt(inspected.high, 3)}</b></span>
      <span>{words.low} <b>{fmt(inspected.low, 3)}</b></span><span>{words.close} <b>{fmt(inspected.close, 3)}</b></span>
      <span>{ui.volume} <b>{fmt(inspected.volume, 2)}</b>{unit && ` ${unit}`}</span>
    </div>
    <div ref={chart} className="decision-chart-canvas">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="group" aria-label={weekly ? ui.weeklyTitle : ui.title}
        onPointerMove={inspectCandle} onPointerLeave={() => { setHoverIndex(null); setHoverKey(null) }}>
        <defs><clipPath id={plotId}><rect x={plotLeft} y="0" width={plotRight - plotLeft} height={priceBottom + 8} /></clipPath></defs>
        {dates.map(index => <g key={index} className="decision-chart-grid" aria-hidden="true">
          <line x1={x(index)} x2={x(index)} y1={priceTop} y2={volumeBottom} />
          <text x={index === start ? plotLeft : index === end ? plotRight : x(index)} y={406}
            textAnchor={index === start ? 'start' : index === end ? 'end' : 'middle'}>{bars[index].date.slice(5)}</text>
        </g>)}
        {prices.map(price => <g key={price} className="decision-chart-grid" aria-hidden="true">
          <line x1={plotLeft} x2={plotRight} y1={y(price)} y2={y(price)} />
          <text x={plotRight + 6} y={y(price)} dominantBaseline="central">{fmt(price, 3)}</text>
        </g>)}
        <g className="decision-chart-grid" aria-hidden="true">
          <line className="decision-axis" x1={plotRight} x2={plotRight} y1={priceTop} y2={volumeBottom} />
          <line className="decision-axis" x1={plotLeft} x2={plotRight} y1={volumeBottom} y2={volumeBottom} />
          <text x={plotLeft} y={303}>{ui.volume}</text>
          {[maxVolume, maxVolume / 2, 0].map(volume => <g key={volume}>
            <line x1={plotLeft} x2={plotRight} y1={volumeY(volume)} y2={volumeY(volume)} />
            <text x={plotRight + 6} y={volumeY(volume)} dominantBaseline="central">{compact.format(volume)}</text>
          </g>)}
        </g>
        <g clipPath={`url(#${plotId})`}>{structuresIn(true)}</g>
        {candles.map((bar, offset) => {
          const point = x(start + offset)
          const body = y(Math.max(bar.open, bar.close))
          return <g key={bar.date} className={`decision-candle ${bar.close >= bar.open ? 'rising' : 'falling'}`} data-date={bar.date} aria-hidden="true">
            <line x1={point} x2={point} y1={y(bar.high)} y2={y(bar.low)} />
            <rect x={point - candleWidth / 2} y={body} width={candleWidth} height={Math.max(1.2, y(Math.min(bar.open, bar.close)) - body)} />
            <rect className="decision-volume-bar" x={point - candleWidth / 2} y={volumeY(bar.volume)} width={candleWidth} height={volumeBottom - volumeY(bar.volume)} />
          </g>
        })}
        {shownLevels.map(({ level, marker }) => {
          const h = { x1: plotLeft, x2: plotRight, y1: y(level.price), y2: y(level.price) }
          return plotMarker(marker, `decision-level ${level.role}`, <>
            <line className="decision-marker-hit" {...h} /><line className="decision-shape" {...h} />
            {labelAt(marker.key, level.price)}
          </>)
        })}
        <g className="decision-last-price" aria-hidden="true">
          <line x1={plotLeft} x2={plotRight} y1={y(candles[candles.length - 1].close)} y2={y(candles[candles.length - 1].close)} />
          {labelAt('close', candles[candles.length - 1].close)}
        </g>
        <g clipPath={`url(#${plotId})`}>{structuresIn(false)}</g>
        {shownObservations.map(marker => {
          const cx = x(marker.index), cy = y(marker.price)
          return plotMarker(marker, 'decision-observation', <>
            <circle className="decision-marker-hit" cx={cx} cy={cy} r="12" />
            <rect className="decision-shape" x={cx - 4.5} y={cy - 4.5} width="9" height="9" transform={`rotate(45 ${cx} ${cy})`} />
          </>)
        })}
        {hoverIndex !== null && hoverIndex >= start && hoverIndex <= end && <line aria-hidden="true" className="decision-crosshair" x1={x(hoverIndex)} x2={x(hoverIndex)} y1={priceTop} y2={volumeBottom} />}
        {selectedInView && <g className="decision-anchor" data-evidence-id={selected.id} aria-hidden="true">
          <line x1={x(selected.index)} x2={x(selected.index)} y1={priceTop} y2={volumeBottom} />
          <circle cx={x(selected.index)} cy={y(selected.price)} r="7" />
        </g>}
      </svg>
    </div>
    <div className="decision-chart-key">
      <span>{ui.key}</span>
      {shownLevels.map(({ level, marker }) => <span key={marker.key} className={`decision-level-key ${level.role}`}><i aria-hidden="true" />{ui[level.role]}</span>)}
      {end < last && shownLevels.length > 0 && <span>{ui.currentLevels}</span>}
    </div>
    {detail && <div className="decision-chart-detail" role="region" aria-label={ui.evidence}>
      <strong>{detail.title}</strong><span className={`decision-evidence-status ${detail.status}`}>{words[detail.status]}</span>
      <span>{ui.geometry} <time dateTime={detail.geometry}>{detail.geometry}</time></span>
      {detail.firstSeen && <span>{words.firstSeen} <time dateTime={detail.firstSeen}>{detail.firstSeen}</time></span>}
      <span>{words.confirmation} {detail.confirmed ? <time dateTime={detail.confirmed}>{detail.confirmed}</time> : '—'}</span>
    </div>}
  </figure>
}
