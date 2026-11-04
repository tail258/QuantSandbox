import { t, useLocale } from '../i18n'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Save, Settings2, RefreshCw } from 'lucide-react'
import type { PageProps } from '../App'
import { api, fmt, pct, type Row } from '../api'
import { post } from '../http'
import { Panel, Note, Chart, Source, LoadingButton, Empty, Research } from '../components'
import { useProject } from '../workspace/ProjectContext'
import Dialog from '../workspace/Dialog'
const ratioMetrics = ['gross_margin', 'net_margin', 'leverage', 'cash_ratio']
export default function Finance({ status, reload }: PageProps) {
  useLocale()
  const { activeProject, reloadProjects } = useProject()
  const [symbol, setSymbol] = useState(activeProject?.symbols[0] || '600519')
  const [profile, setProfile] = useState<Row>({
    template: 'general',
    name: '',
    peers: [],
    metrics: ['revenue', 'profit', 'cashflow'],
    focus: '',
  })
  const [peerText, setPeerText] = useState('')
  const [data, setData] = useState<Row[]>([])
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')
  const [settings, setSettings] = useState(false)
  const [metric, setMetric] = useState('profit')
  const [mode, setMode] = useState('quarter')
  const [period, setPeriod] = useState('common')
  const projectSymbols = activeProject?.symbols.join(',') || ''
  useEffect(() => {
    const first = activeProject?.symbols[0]
    if (first) setSymbol(first)
  }, [activeProject?.id, projectSymbols])
  useEffect(() => {
    if (!/^\d{6}$/.test(symbol)) return
    let alive = true
    api('/profile/' + symbol)
      .then((p) => {
        if (!alive) return
        setProfile(p)
        setPeerText(
          [...new Set([...(activeProject?.symbols || []).filter((s) => s !== symbol), ...p.peers])]
            .slice(0, 5)
            .join(','),
        )
        setMetric(p.metrics.includes('profit') ? 'profit' : p.metrics[0] || 'profit')
        setMsg('')
      })
      .catch((e) => {
        if (alive) setMsg(e.message)
      })
    return () => {
      alive = false
    }
  }, [symbol, activeProject?.id, projectSymbols])
  const symbols = useMemo(
    () =>
      [symbol, ...peerText.split(/[,，\s]+/).filter(Boolean)]
        .filter((v, i, a) => a.indexOf(v) === i)
        .slice(0, 6),
    [symbol, peerText],
  )
  const operationContext = [activeProject?.id || '', ...symbols].join('|')
  const operationOwner = useRef(operationContext)
  const operationGeneration = useRef(0)
  useLayoutEffect(() => {
    operationOwner.current = operationContext
    operationGeneration.current++
    setBusy(false)
    setMsg('')
    return () => {
      operationGeneration.current++
    }
  }, [operationContext])
  useEffect(() => {
    if (symbols.some((s) => !/^\d{6}$/.test(s))) return
    let alive = true
    setLoading(true)
    setData([])
    api('/finance?symbols=' + symbols.join(','))
      .then((d) => {
        if (alive) setData(d)
      })
      .catch((e) => {
        if (alive) setMsg(e.message)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [symbols.join(',')])
  const currentProfile = () => ({ ...profile, peers: symbols.filter((s) => s !== symbol) })
  async function saveProfile() {
    await api('/profile/' + symbol, currentProfile())
    setMsg('公司配置已保存。')
  }
  async function refresh() {
    const owner = operationContext
    const generation = ++operationGeneration.current
    const isCurrent = () =>
      operationOwner.current === owner && operationGeneration.current === generation
    setBusy(true)
    setMsg('')
    try {
      // The request may continue populating its original cache after a project switch.
      await api('/profile/' + symbol, currentProfile())
      const responses = await Promise.all(
        symbols.map((s) => api('/fetch', { kind: 'finance', symbol: s })),
      )
      const next = await api('/finance?symbols=' + symbols.join(','))
      await reload()
      if (!isCurrent()) return
      setData(next)
      setMsg(
        responses.some((r) => r.warning)
          ? '部分来源更新失败，显示已保留的缓存；请查看来源与缺口。'
          : '已按报表口径更新单季度比较。',
      )
    } catch (e: any) {
      if (isCurrent()) setMsg(e.message)
    } finally {
      if (isCurrent()) setBusy(false)
    }
  }
  const rowsByCompany: Row[] = data.map((d) => ({
    ...d,
    selected: mode === 'quarter' ? d.rows : d.raw_rows,
  }))
  const dates = [
    ...new Set<string>(rowsByCompany.flatMap((d) => d.selected.map((r: Row) => r.date))),
  ]
    .sort()
    .slice(-16)
  const commonDates = dates.filter((date) =>
    rowsByCompany.every((d) => d.selected.some((r: Row) => r.date === date)),
  )
  const reportDate = period === 'common' ? commonDates.at(-1) : period
  const chart = dates.map((date) => ({
    date,
    ...Object.fromEntries(
      rowsByCompany.map((d) => {
        const value = d.selected.find((r: Row) => r.date === date)?.[metric]
        return [
          d.symbol,
          value == null ? null : ratioMetrics.includes(metric) ? value * 100 : value / 1e8,
        ]
      }),
    ),
  }))
  const labels: Row = status.metrics || {}
  const financialFormat = (key: string, value: any) =>
    ['gross_margin', 'net_margin', 'leverage'].includes(key)
      ? pct(value)
      : key === 'cash_ratio'
        ? fmt(value) + ' ' + t('倍')
        : value == null
          ? '—'
          : fmt(value / 1e8) + ' ' + t('亿')
  async function saveComparison() {
    const projectId = activeProject?.id
    setBusy(true)
    setMsg('')
    try {
      await saveProfile()
      const record = await api('/save-finance', {
        symbols,
        mode,
        metric,
        period,
        report_date: reportDate,
      })
      if (projectId) {
        await post('/projects/' + projectId + '/links', { kind: 'research', run_id: record.id })
        await reloadProjects()
      }
      setMsg(projectId ? '本次财务比较已保存并关联研究项目。' : '本次财务比较已保存。')
    } catch (e: any) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>{t('公司与财务')}</h1>
          <p>{t('利润、现金流与估值，在同一报告期比较。')}</p>
        </div>
        <LoadingButton busy={busy} onClick={refresh}>
          <RefreshCw size={15} />
          {t('更新并比较')}{' '}
        </LoadingButton>
      </div>
      <div className="research-object-bar">
        <label>
          {t('公司代码')}{' '}
          <input
            aria-label={t('公司代码')}
            value={symbol}
            maxLength={6}
            onChange={(e) => setSymbol(e.target.value)}
          />
        </label>
        <div className="object-identity">
          <strong>{profile.name || symbol}</strong>
          <small>
            {t(status.templates[profile.template]?.name || '公司分析')} ·{' '}
            {t('{count} 家比较', { count: symbols.length })}{' '}
          </small>
        </div>
        <span className="tag">{t('财报截至 {date}', { date: dates.at(-1) || t('暂无缓存') })}</span>
        <button className="secondary" onClick={() => setSettings(true)}>
          <Settings2 size={15} />
          {t('公司与同行配置')}{' '}
        </button>
      </div>
      {msg && <Note>{t(msg)}</Note>}
      <div className="research-method-strip">
        <span>{t('报表版本：当前修订数据')}</span>
        <span>
          {mode === 'quarter'
            ? t('利润与现金流拆单季度；资产负债为时点')
            : t('报表原值，累计流量与时点保留')}
        </span>
        <span>{t('公告日以来源版本显示')}</span>
      </div>
      <Panel
        title={t('历史与同行比较')}
        action={
          <div className="controls compact">
            <label>
              {t('财务指标')}{' '}
              <select
                aria-label={t('财务指标')}
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                {Object.entries(labels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {t(String(label))}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('报表口径')}{' '}
              <select
                aria-label={t('报表口径')}
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="quarter">{t('单季度')}</option>
                <option value="ytd">{t('报表原值')}</option>
              </select>
            </label>
          </div>
        }
      >
        {loading ? (
          <Empty>{t('正在读取公司缓存…')}</Empty>
        ) : data.length ? (
          <>
            <Chart
              rows={chart}
              lines={data.map((d) => ({
                key: d.symbol,
                name: d.symbol === symbol ? profile.name || d.symbol : d.symbol,
              }))}
              unit={ratioMetrics.includes(metric) ? t('%（现金比率 ×100）') : t('亿元')}
            />
            <div className="controls result-table-controls">
              <label>
                {t('比较报告期')}{' '}
                <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                  <option value="common">{t('共同最新报告期')}</option>
                  <option value="latest">{t('各公司最新（可能不同期）')}</option>
                  {dates
                    .slice()
                    .reverse()
                    .map((date) => (
                      <option key={date} value={date}>
                        {date}
                      </option>
                    ))}
                </select>
              </label>
              <button className="secondary" disabled={busy} onClick={saveComparison}>
                <Save size={14} />
                {t('保存本次比较')}{' '}
              </button>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t('公司 / 报告期')}</th>
                    {profile.metrics.map((key: string) => (
                      <th key={key}>{t(labels[key] || key)}</th>
                    ))}
                    <th>{t('来源版本公告日')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rowsByCompany.map((company) => {
                    const row =
                      period === 'latest'
                        ? company.selected.at(-1)
                        : company.selected.find((row: Row) => row.date === reportDate)
                    return (
                      row && (
                        <tr key={company.symbol}>
                          <td>
                            {company.symbol}
                            <small>{row.date}</small>
                          </td>
                          {profile.metrics.map((key: string) => (
                            <td key={key}>{financialFormat(key, row[key])}</td>
                          ))}
                          <td>{row.available_date || t('未知')}</td>
                        </tr>
                      )
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <Empty>{t('该公司暂未缓存财报。点击“更新并比较”手动获取。')}</Empty>
        )}
      </Panel>
      <Panel title={t('观察重点')}>
        <p className="observation-focus">
          {(profile.focus && profile.focus === status.templates[profile.template]?.focus
            ? t(profile.focus)
            : profile.focus) ||
            t(status.templates[profile.template]?.focus || '') ||
            t('在公司配置中选择关注指标与研究重点。')}
        </p>
        {['bank', 'insurance'].includes(profile.template) && (
          <Note>{t('专用经营指标需从公告补充；通用报表字段不是完整行业模型。')}</Note>
        )}
      </Panel>
      <Panel title={t('估值观察')}>
        <div className="link-row">
          {status.series
            .filter(
              (s: Row) =>
                symbols.includes(s.symbol) && (s.id.endsWith('peTTM') || s.id.endsWith('pbMRQ')),
            )
            .map((s: Row) => (
              <Valuation key={s.id} series={s} />
            ))}
        </div>
        <p className="muted">{t('来自已缓存日线。暂无估值时，可在数据中心获取对应公司的行情。')}</p>
      </Panel>
      <details className="workspace-details">
        <summary>{t('计算口径与补充检索')}</summary>
        <p>
          {t(
            '仅流量项目拆季度；Q2/Q3/Q4 为本期累计减同年上一季度累计。缺前期留空，余额不差分，单季比例重新计算。原值模式不展示推导比例。',
          )}{' '}
        </p>
        <Research topic={`${symbol} ${profile.focus || '公司财报及行业专属经营指标'}`} />
      </details>
      {data.map((company) => (
        <Source key={company.symbol} s={company} />
      ))}
      {settings && (
        <Dialog title={t('公司与同行配置')} onClose={() => setSettings(false)}>
          <div className="controls wrap">
            <label className="grow">
              {t('公司显示名')}{' '}
              <input
                value={profile.name || ''}
                onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              />
            </label>
            <label>
              {t('分析模板')}{' '}
              <select
                aria-label={t('分析模板')}
                value={profile.template}
                onChange={(e) => {
                  const template = status.templates[e.target.value]
                  if (!template) return
                  setProfile({
                    ...profile,
                    template: e.target.value,
                    metrics: template.metrics,
                    focus: template.focus,
                  })
                  setMetric(template.metrics[0])
                }}
              >
                {Object.entries(status.templates).map(([key, value]: [string, any]) => (
                  <option key={key} value={key}>
                    {t(value.name || key)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            {t('同行代码（最多 5 家）')}{' '}
            <input
              value={peerText}
              onChange={(e) => setPeerText(e.target.value)}
              placeholder={t('六位代码，逗号分隔')}
            />
          </label>
          <fieldset className="metric-choice-fields">
            <legend>{t('比较指标')}</legend>
            <div className="checks">
              {Object.entries(labels).map(([key, label]) => (
                <label className="checkbox" key={key}>
                  <input
                    type="checkbox"
                    checked={profile.metrics.includes(key)}
                    onChange={(e) =>
                      setProfile({
                        ...profile,
                        metrics: e.target.checked
                          ? [...profile.metrics, key]
                          : profile.metrics.filter((value: string) => value !== key),
                      })
                    }
                  />
                  {t(String(label))}
                </label>
              ))}
            </div>
          </fieldset>
          <label>
            {t('观察重点')}{' '}
            <textarea
              value={profile.focus}
              onChange={(e) => setProfile({ ...profile, focus: e.target.value })}
            />
          </label>
          <p className="muted">{t('公司专属经营指标仍通过带来源的 CSV 补充。')}</p>
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setSettings(false)}>
              {t('关闭')}{' '}
            </button>
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                try {
                  await saveProfile()
                  setSettings(false)
                } catch (e: any) {
                  setMsg(e.message)
                } finally {
                  setBusy(false)
                }
              }}
            >
              <Save size={14} />
              {t('保存公司配置')}{' '}
            </button>
          </div>
        </Dialog>
      )}
    </>
  )
}
function Valuation({ series }: { series: Row }) {
  useLocale()
  const [row, setRow] = useState<Row | null>(null)
  useEffect(() => {
    let live = true
    api('/series/' + series.id)
      .then((value) => {
        if (live) setRow(value.rows.at(-1))
      })
      .catch(() => {})
    return () => {
      live = false
    }
  }, [series.id])
  return (
    <div className="valuation">
      <span>{series.name}</span>
      <strong>
        {fmt(row?.value)} {t('倍')}
      </strong>
      <small>{row?.date || t('加载中')}</small>
    </div>
  )
}
