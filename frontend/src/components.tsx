import { useState, type ReactNode } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { Download, Search, Info, RefreshCw } from 'lucide-react'
import { api, fmt, download, type Row } from './api'
export function Panel({
  title,
  action,
  children,
  className = '',
}: {
  title: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={'panel ' + className}>
      <div className="panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}
export function Note({ children, tone = 'info' }: { children: ReactNode; tone?: string }) {
  return (
    <div className={'note ' + tone}>
      <Info size={16} />
      <div>{children}</div>
    </div>
  )
}
export function Empty({ children = '暂时没有数据，请先获取或导入。' }: { children?: ReactNode }) {
  return (
    <div className="empty">
      <Search size={25} />
      <p>{children}</p>
    </div>
  )
}
export function Metric({
  label,
  value,
  sub,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  )
}
export function Chart({
  rows,
  lines,
  unit = '',
  normalize = false,
}: {
  rows: Row[]
  lines: { key: string; name: string; color?: string }[]
  unit?: string
  normalize?: boolean
}) {
  const colors = ['#087d79', '#7892a8', '#b28842', '#bd6d71']
  let data = rows
  if (normalize) {
    data = rows.map((r) => ({ ...r }))
    lines.forEach((l) => {
      const first = rows.find((r) => r[l.key] != null && r[l.key] !== 0)?.[l.key]
      data.forEach((r) => (r[l.key] = r[l.key] != null && first ? (r[l.key] / first) * 100 : null))
    })
  }
  return (
    <div className="chart-wrap">
      <div className="chart-caption">
        {normalize ? '各序列首个有效值 = 100' : unit}
        <button
          className="text-button"
          onClick={(e) => {
            const svg = e.currentTarget
              .closest('.chart-wrap')
              ?.querySelector('.recharts-wrapper > svg.recharts-surface')
            if (svg)
              download(
                'quantsandbox-chart.svg',
                new XMLSerializer().serializeToString(svg),
                'image/svg+xml',
              )
          }}
        >
          <Download size={14} /> 导出 SVG
        </button>
      </div>
      {rows.length ? (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 12, right: 18, bottom: 6, left: 6 }}>
            <CartesianGrid stroke="#edf0f2" vertical={false} />
            <XAxis
              dataKey="date"
              minTickGap={60}
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => String(v).slice(0, 10)}
            />
            <YAxis
              width={64}
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => fmt(v, Math.abs(v) < 1 ? 4 : Math.abs(v) < 10 ? 2 : 0)}
              domain={['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: '1px solid #e1e7eb', fontSize: 12 }}
              formatter={(v: any) => fmt(v, Math.abs(Number(v)) < 1 ? 4 : 2)}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {lines.map((l, i) => (
              <Line
                key={l.key}
                dataKey={l.key}
                name={l.name}
                stroke={l.color || colors[i % 4]}
                strokeWidth={1.8}
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <Empty />
      )}
    </div>
  )
}
export function RawTable({ rows }: { rows: Row[] }) {
  const [limit, setLimit] = useState(20)
  if (!rows.length) return <Empty />
  const cols = Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== 'object')
  return (
    <>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {cols.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((r, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c}>{String(r[c] ?? '—')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > limit && (
        <button className="text-button" onClick={() => setLimit(limit + 50)}>
          加载更多（共 {rows.length} 行）
        </button>
      )}
    </>
  )
}
export function Source({ s }: { s: Row }) {
  return (
    <div className="source">
      <div className="source-summary">
        <a href={s.source_url || undefined} target="_blank" rel="noreferrer">
          {s.source || '来源未注明'}
        </a>
        <span>获取于 {s.fetched_at?.replace('T', ' ').slice(0, 19) || '未知'} UTC</span>
      </div>
      <details>
        <summary>来源口径与快照</summary>
        <p>{s.method}</p>
        <code>快照 {s.snapshot_id || s.id}</code>
      </details>
    </div>
  )
}
export function Research({ topic }: { topic: string }) {
  const [result, setResult] = useState<Row | null>(null)
  const [error, setError] = useState('')
  return (
    <div>
      <button
        className="secondary"
        onClick={() =>
          api('/research', { topic })
            .then(setResult)
            .catch((e) => setError(e.message))
        }
      >
        <Search size={15} /> 生成 Codex 检索任务
      </button>
      {error && <Note tone="warn">{error}</Note>}
      {result && (
        <div className="research">
          <p>将以下任务交给当前 Codex；网页本身不会自动调用模型。</p>
          <textarea aria-label="Codex 检索任务" readOnly value={result.prompt} />
          <button
            className="text-button"
            onClick={() => download('research-request.md', result.prompt)}
          >
            下载检索任务
          </button>
          <div className="link-row">
            {result.sources.map((s: Row) => (
              <a key={s.url} href={s.url} target="_blank" rel="noreferrer">
                {s.name}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
export function LoadingButton({
  busy,
  disabled,
  children,
  ...rest
}: {
  busy: boolean
  disabled?: boolean
  children: ReactNode
  onClick?: () => void
  type?: 'submit' | 'button'
  className?: string
}) {
  return (
    <button {...rest} disabled={busy || disabled}>
      {busy && <RefreshCw size={15} className="spin" />}
      {busy ? '处理中…' : children}
    </button>
  )
}
