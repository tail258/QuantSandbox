import { t, useLocale } from './i18n'
import { useTheme } from './theme'
import { serializeChart } from './chart-export'
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
  useLocale()
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
  useLocale()
  return (
    <div className={'note ' + tone}>
      <Info size={16} />
      <div>{children}</div>
    </div>
  )
}
export function Empty({ children }: { children?: ReactNode }) {
  useLocale()
  return (
    <div className="empty">
      <Search size={25} />
      <p>{children ?? t('暂时没有数据，请先获取或导入。')}</p>
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
  useLocale()
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
  useLocale()
  const theme = useTheme()
  const colors = theme === 'terminal' ? ['#F5C542', '#8CA5BD', '#B79ADE', '#31C48D'] : ['#087d79', '#7892a8', '#b28842', '#bd6d71']
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
        {normalize ? t('各序列首个有效值 = 100') : unit}
        <button
          className="text-button"
          onClick={(e) => {
            const svg = e.currentTarget
              .closest('.chart-wrap')
              ?.querySelector('.recharts-wrapper > svg.recharts-surface')
            if (svg)
              download(
                'quantsandbox-chart.svg',
                serializeChart(svg),
                'image/svg+xml',
              )
          }}
        >
          <Download size={14} /> {t('导出 SVG')}
        </button>
      </div>
      {rows.length ? (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 12, right: 18, bottom: 6, left: 6 }}>
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis
              dataKey="date"
              minTickGap={60}
              tick={{ fontSize: 11, fill: 'var(--chart-text)' }}
              tickFormatter={(v) => String(v).slice(0, 10)}
            />
            <YAxis
              width={64}
              tick={{ fontSize: 11, fill: 'var(--chart-text)' }}
              tickFormatter={(v) => fmt(v, Math.abs(v) < 1 ? 4 : Math.abs(v) < 10 ? 2 : 0)}
              domain={['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{ borderRadius: 8, background: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', color: 'var(--theme-text, #192b37)', fontSize: 12 }}
              formatter={(v: any) => fmt(v, Math.abs(Number(v)) < 1 ? 4 : 2)}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {lines.map((l, i) => (
              <Line
                key={l.key}
                dataKey={l.key}
                name={l.name}
                stroke={theme === 'terminal' ? (l.key === 'benchmark' ? '#6C7884' : colors[i % 4]) : l.color || colors[i % 4]}
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
  useLocale()
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
          {t('加载更多（共 {count} 行）', {count: rows.length})}
        </button>
      )}
    </>
  )
}
export function Source({ s }: { s: Row }) {
  useLocale()
  return (
    <div className="source">
      <div className="source-summary">
        <a href={s.source_url || undefined} target="_blank" rel="noreferrer">
          {s.source || t('来源未注明')}
        </a>
        <span>{t('获取于 {time} UTC', {time: s.fetched_at?.replace('T', ' ').slice(0, 19) || t('未知')})}</span>
      </div>
      <details>
        <summary>{t('来源口径与快照')}</summary>
        <p>{s.method}</p>
        <code>{t('快照 {id}', {id: s.snapshot_id || s.id})}</code>
      </details>
    </div>
  )
}
export function Research({ topic }: { topic: string }) {
  useLocale()
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
        <Search size={15} /> {t('生成 Codex 检索任务')}
      </button>
      {error && <Note tone="warn">{t(error)}</Note>}
      {result && (
        <div className="research">
          <p>{t('将以下任务交给当前 Codex；网页本身不会自动调用模型。')}</p>
          <textarea aria-label={t('Codex 检索任务')} readOnly value={result.prompt} />
          <button
            className="text-button"
            onClick={() => download('research-request.md', result.prompt)}
          >
            {t('下载检索任务')}
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
  useLocale()
  return (
    <button {...rest} disabled={busy || disabled}>
      {busy && <RefreshCw size={15} className="spin" />}
      {busy ? t('处理中…') : children}
    </button>
  )
}
