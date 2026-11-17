import { useId } from 'react'
import { fmt } from '../api'
import type { ChanCopy } from '../i18n/chan'
import type { Candle, ChanEvent, Layer } from './model'

const chartWidth = 900
const chartHeight = 300
const padding = 12

export default function ChanChart({ bars, last, size, structures, visible, exDates, copy }: {
  bars: Candle[]
  last: number
  size: number
  structures: ChanEvent[]
  visible: ReadonlySet<Layer>
  exDates: ReadonlySet<string>
  copy: ChanCopy
}) {
  const clip = useId()
  const start = Math.max(0, last - size + 1)
  const candles = bars.slice(start, last + 1)
  const first = candles[0]
  const current = candles.at(-1)
  if (!first || !current) return null

  const min = Math.min(...candles.map(bar => bar.low))
  const max = Math.max(...candles.map(bar => bar.high))
  const spread = max - min || (Math.abs(max) * 0.02 || 1)
  const bottom = min - spread * 0.05
  const top = max + spread * 0.05
  const step = (chartWidth - padding * 2) / candles.length
  const width = Math.min(step * .62, 19)
  const x = (i: number) => padding + (i - start + .5) * step
  const y = (price: number) => padding + (top - price) / (top - bottom) * (chartHeight - padding * 2)
  const ticks = Array.from({ length: 5 }, (_, i) => top - (top - bottom) * i / 4)

  function plot(event: ChanEvent) {
    const { layer, structure } = event
    if (!visible.has(layer) || structure.end_index < start || structure.start_index > last) return null
    const classes = `chan-overlay ${layer} ${structure.status}`
    const { start_index, end_index } = structure
    if (layer === 'centers') {
      return <rect key={structure.id} className={classes} x={x(start_index)} y={y(event.structure.upper)}
        width={Math.max(width, x(end_index) - x(start_index))} height={Math.max(1, y(event.structure.lower) - y(event.structure.upper))} />
    }
    if (layer === 'merged_bars') {
      if (start_index === end_index) return null
      return <rect key={structure.id} className={classes} x={x(start_index) - width / 2} y={y(structure.high)}
        width={x(end_index) - x(start_index) + width} height={Math.max(1, y(structure.low) - y(structure.high))} />
    }
    if (layer === 'fractals') {
      const fractal = event.structure
      if (fractal.index < start || fractal.index > last) return null
      return <circle key={structure.id} className={classes} cx={x(fractal.index)} cy={y(fractal.price)} r="5" />
    }
    return <line key={structure.id} className={classes} x1={x(start_index)} y1={y(event.structure.start_price)}
      x2={x(end_index)} y2={y(event.structure.end_price)} />
  }

  return <figure className="chan-chart">
    <div className="chan-chart-prices">
      <figcaption>{copy.chart}</figcaption>
      <span>{copy.open} <strong>{fmt(current.open, 4)}</strong></span>
      <span>{copy.high} <strong>{fmt(current.high, 4)}</strong></span>
      <span>{copy.low} <strong>{fmt(current.low, 4)}</strong></span>
      <span>{copy.close} <strong>{fmt(current.close, 4)}</strong></span>
      {exDates.has(current.date) && <span className="chan-ex-date-text">{copy.exDate}</span>}
    </div>
    <div className="chan-chart-viewport">
      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none" role="img" aria-label={copy.chart}>
        <defs><clipPath id={clip}><rect width={chartWidth} height={chartHeight} /></clipPath></defs>
        {ticks.map(price => <line key={price} className="chan-gridline" x1="0" x2={chartWidth} y1={y(price)} y2={y(price)} />)}
        <g clipPath={`url(#${clip})`}>
          {structures.filter(event => event.layer === 'centers' || event.layer === 'merged_bars').map(plot)}
          {candles.map((bar, offset) => {
            const point = x(start + offset)
            const title = `${bar.date} · ${copy.open} ${fmt(bar.open, 4)} · ${copy.high} ${fmt(bar.high, 4)} · ${copy.low} ${fmt(bar.low, 4)} · ${copy.close} ${fmt(bar.close, 4)}`
            const exDate = exDates.has(bar.date)
            return <g key={bar.date} className={`chan-candle ${bar.close >= bar.open ? 'rising' : 'falling'}`} data-date={bar.date}>
              <title>{exDate ? `${title} · ${copy.exDate}` : title}</title>
              {exDate && <line className="chan-ex-date" x1={point} x2={point} y1="0" y2={chartHeight} />}
              <line x1={point} x2={point} y1={y(bar.high)} y2={y(bar.low)} />
              <rect x={point - width / 2} y={y(Math.max(bar.open, bar.close))} width={width}
                height={Math.max(1.3, Math.abs(y(bar.open) - y(bar.close)))} />
            </g>
          })}
          {structures.filter(event => event.layer !== 'centers' && event.layer !== 'merged_bars').map(plot)}
          <line className="chan-cursor-line" x1={x(last)} x2={x(last)} y1="0" y2={chartHeight} />
        </g>
      </svg>
      <div className="chan-chart-axis" aria-hidden="true">
        {ticks.map(price => <span key={price} style={{ top: `${y(price) / chartHeight * 100}%` }}>{fmt(price)}</span>)}
      </div>
    </div>
    <div className="chan-chart-dates"><span>{first.date}</span>{current.date !== first.date && <span>{current.date}</span>}</div>
  </figure>
}
