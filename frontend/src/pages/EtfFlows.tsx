import {t,useLocale} from '../i18n';
import { useEffect, useMemo, useState } from 'react'
import { Download, SlidersHorizontal, RotateCcw } from 'lucide-react'
import { useProject } from '../workspace/ProjectContext'
import type { PageProps } from '../App'
import { api, fmt, today, pct, type Row } from '../api'
import { Panel, Note, Metric, Empty, LoadingButton, Source } from '../components'
import EtfFlowChart from '../EtfFlowChart'
import EtfEvidence from '../EtfEvidence'
const amount = (v: any, unit: string) =>
  v == null ? '—' : (v > 0 ? '+' : '') + fmt(v / 1e8) + ' ' + t(unit === 'flow' ? '亿元' : '亿份')
export default function EtfFlows({ reload }: PageProps) {
 useLocale();
  const { activeProject, linkRecord } = useProject()
  const [data, setData] = useState<Row | null>(null),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<Row | null>(null),
    [unit, setUnit] = useState('delta'),
    [threshold, setThreshold] = useState(3),
    [start, setStart] = useState(new Date(Date.now() - 75 * 86400000).toLocaleDateString('sv-SE')),
    [end, setEnd] = useState(today),
    [codes, setCodes] = useState(''),
    [settings, setSettings] = useState(false),
    [force, setForce] = useState(false),
    [selectedDay, setSelectedDay] = useState<string | null>(null),
    [query, setQuery] = useState(''),
    [family, setFamily] = useState('全部'),
    [onlyAbnormal, setOnlyAbnormal] = useState(false),
    [sort, setSort] = useState('delta_30'),
    [descending, setDescending] = useState(true)
  const load = async (p: Row = {}) => {
    const next = await api('/etf/dashboard', p)
    setData(next)
    if (!data) {
      setCodes((next.run?.params.codes || Object.keys(next.universe)).join(','))
      if (next.run) {
        setStart(next.run.params.start)
        setEnd(next.run.params.end)
        setThreshold(next.run.result.threshold * 100)
      }
    }
    return next
  }
  useEffect(() => {
    load().catch((e) => setMessage(e.message))
  }, [])
  useEffect(() => {
    if (!job || job.status !== 'running') return
    let alive = true
    const timer = setTimeout(async () => {
      try {
        const next = await api('/etf/jobs/' + job.id)
        if (!alive) return
        setJob(next)
        if (next.status === 'completed') {
          await load()
          await reload()
          setMessage('更新完成，显示来源已发布的实际日期。')
        } else if (next.status !== 'running') setMessage(next.error || '任务已中断')
      } catch (e: any) {
        if (alive) setMessage(e.message)
      }
    }, 1500)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [job])
  const result = data?.run?.result,
    run = data?.run
  const pool = () => codes.split(/[,，\s]+/).filter(Boolean)
  const isRunning = job?.status === 'running'
  const calculate = async () => {
    setBusy(true)
    setMessage('')
    try {
      const projectId = activeProject?.id || null
      const next = await load({ codes: pool(), threshold: threshold / 100 })
      if (next.run) await linkRecord('research', next.run.id, projectId)
      setSelectedDay(null)
    } catch (e: any) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }
  const refresh = async () => {
    setMessage('')
    try {
      setJob(
        await api('/etf/refresh', { start, end, codes: pool(), threshold: threshold / 100, force }),
      )
    } catch (e: any) {
      setMessage(e.message)
    }
  }
  const tableRows = useMemo(() => {
    let rows: Row[] = result?.rows || []
    if (query)
      rows = rows.filter((r) => (r.code + ' ' + r.name).toLowerCase().includes(query.toLowerCase()))
    if (family !== '全部') rows = rows.filter((r) => r.family === family)
    if (onlyAbnormal) rows = rows.filter((r) => r.abnormal)
    const sortKey = sort.startsWith('delta_')
      ? unit === 'flow'
        ? sort.replace('delta_', 'flow_')
        : sort
      : sort
    return [...rows].sort((a, b) => {
      if (a[sortKey] == null) return b[sortKey] == null ? 0 : 1
      if (b[sortKey] == null) return -1
      return (
        (descending ? -1 : 1) *
        (typeof a[sortKey] === 'string'
          ? a[sortKey].localeCompare(b[sortKey])
          : a[sortKey] - b[sortKey])
      )
    })
  }, [result, query, family, onlyAbnormal, sort, descending, unit])
  const latest = result?.latest
  const best = result?.windows['30']?.rows
    ?.filter((r: Row) => r[unit] != null && r[unit] > 0)
    .sort((a: Row, b: Row) => b[unit] - a[unit])[0]
  const sortedEvents: Row[] = selectedDay
    ? (result?.details[selectedDay] || [])
        .filter((r: Row) => r.delta != null)
        .sort((a: Row, b: Row) => Math.abs(b[unit] || 0) - Math.abs(a[unit] || 0))
    : []
  const toggleSort = (key: string) => {
    if (key === sort) setDescending(!descending)
    else {
      setSort(key)
      setDescending(true)
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>{t("宽基 ETF 资金观察")}</h1>
          <p>{t("指数、份额变化与公开机构持仓，共同核对资金结构。")}</p>
        </div>
        <div className="actions">
          <button className="secondary" onClick={() => setSettings(!settings)}>
            <SlidersHorizontal size={16} /> {t("样本与参数")}</button>
          <LoadingButton busy={!data || !!isRunning} onClick={refresh}>
            {t("更新数据")}</LoadingButton>
        </div>
      </div>
      {settings && (
        <Panel title={t("取数与计算参数")}>
          <div className="controls wrap">
            <label>
              {t("取数开始日期")}<input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label>
              {t("取数结束日期")}<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
            <label>
              {t("单日份额异常阈值（%）")}<input
                aria-label={t("ETF异常阈值")}
                type="number"
                min={0.1}
                max={100}
                step={0.1}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />{' '}
              {t("强制刷新已有缓存")}</label>
            <LoadingButton busy={busy} onClick={calculate}>
              {t("按缓存重算")}</LoadingButton>
          </div>
          <label>
            {t("ETF样本代码（逗号分隔，最多40只）")}<textarea
              aria-label={t("ETF样本代码")}
              value={codes}
              onChange={(e) => setCodes(e.target.value)}
            />
          </label>
          <button
            className="text-button"
            onClick={() => setCodes(Object.keys(data?.universe || {}).join(','))}
          >
            <RotateCcw size={14} /> {t("恢复默认25只")}</button>
          <p className="muted">
            {t("单次最多120个自然日；1/7/30窗口均按交易日计算。新增样本后更新数据可补取其净值。按缓存重算仅调整样本和阈值；图下拖动滑块可缩放观察区间。仅在你或Codex发起时取数。")}</p>
        </Panel>
      )}
      {isRunning && (
        <Note>
          {t(job?.stage)} · {job?.done}/{job?.total} {t("· 过程错误")}{job?.errors || 0}
          {t("。已完成部分写入缓存，可在服务中断后复用。")}</Note>
      )}
      {message && <Note>{t(message)}</Note>}
      {!result ? (
        <Panel title={t("ETF份额追踪")}>
          <Empty>{t("点击更新数据，获取交易所份额、基金净值与指数历史。数据完成前保留空白。")}</Empty>
        </Panel>
      ) : (
        <>
          {run.params.end > result.asof && (
            <Note tone="warn">
              {t("请求截至")}{run.params.end}{t("，最新可用份额日期为")}{result.asof}{t("。尚未发布的日期保留缺失。")}</Note>
          )}
          <div className="etf-status">
            <span className="tag good">{t("份额日期")}{result.asof}</span>
            <span>
              {t("样本")}{result.universe.length} {t("只 · 当日有效份额变化")}{latest.coverage}/
              {latest.expected} {t("· 同日净值")}{latest.nav_coverage}/{latest.expected}
            </span>
            {activeProject && (
              <button
                className="secondary"
                disabled={activeProject.links.some(
                  (link) => link.kind === 'research' && link.run_id === run.id,
                )}
                onClick={() =>
                  linkRecord('research', run.id)
                    .then(() => setMessage('当前分析已关联研究项目。'))
                    .catch((e) => setMessage(e.message))
                }
              >
                {t("加入当前项目")}</button>
            )}
            <div className="segmented" aria-label={t("ETF统计单位")}>
              <button
                className={unit === 'delta' ? 'selected' : ''}
                onClick={() => setUnit('delta')}
              >
                {t("份额变化")}</button>
              <button className={unit === 'flow' ? 'selected' : ''} onClick={() => setUnit('flow')}>
                {t("估算申赎金额")}</button>
            </div>
          </div>
          <Panel
            title={t("沪深300 × 份额脉冲")}
            action={
              <a className="button secondary" href={'/api/research/export/' + run.id}>
                <Download size={15} /> {t("导出本次分析")}</a>
            }
          >
            <EtfFlowChart rows={result.daily} unit={unit} onSelect={setSelectedDay} />
            {selectedDay && (
              <div className="etf-event">
                <div className="panel-head">
                  <h2>{selectedDay} {t("· 逐只贡献")}</h2>
                  <button className="text-button" onClick={() => setSelectedDay(null)}>
                    {t("收起事件明细")}</button>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>ETF</th>
                        <th>{t("指数")}</th>
                        <th>{t("净份额变化")}</th>
                        <th>{t("估算申赎")}</th>
                        <th>{t("状态")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedEvents.map((r) => (
                        <tr key={r.code}>
                          <td>
                            {r.name}
                            <small>{r.code}</small>
                          </td>
                          <td>{t(r.family)}</td>
                          <td className={r.delta > 0 ? 'up' : 'down'}>
                            {amount(r.delta, 'delta')}
                          </td>
                          <td>{amount(r.flow, 'flow')}</td>
                          <td>
                            {r.suspect ? t("大幅变化待核验") : r.abnormal ? t("超过异常阈值") : t("常态")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </Panel>
          <div className="metrics etf-metrics">
            {[1, 7, 30].map((k) => {
              const w = result.windows[String(k)]
              return (
                <Metric
                  key={k}
                  label={t("{v0}交易日{v1}", {v0: k, v1: unit === 'flow' ? t('估算净申赎') : t('净份额变化')})}
                  value={
                    <span className={w[unit] > 0 ? 'up' : w[unit] < 0 ? 'down' : ''}>
                      {amount(w[unit], unit)}
                    </span>
                  }
                  sub={t("有效{v0} {v1}/{v2} · 已覆盖样本合计", {v0: unit === 'flow' ? t('金额') : t('份额'), v1: unit === 'flow' ? w.nav_coverage : w.coverage, v2: w.expected})}
                />
              )
            })}
            <Metric
              label={t("最新日净增广度")}
              value={`${latest.positive} / ${latest.coverage}`}
              sub={t("净增ETF / 有效ETF · 目标样本{v0}只", {v0: latest.expected})}
            />
            <Metric
              label={t("30交易日最大净增")}
              value={best ? amount(best[unit], unit) : '—'}
              sub={best ? best.name + ' · ' + best.code : t("无有效净增样本或历史不足")}
            />
            <Metric
              label={t("最新日份额异常")}
              value={result.rows.filter((r: Row) => r.abnormal).length + ' ' + t('只')}
              sub={t("单日绝对变化率 ≥ {v0}%；≥50%另行待核验", {v0: fmt(result.threshold * 100)})}
            />
          </div>
          <Note>
            {t(result.coverage_note)}{' '}
            {t("估算申赎使用逐日份额差×同日单位净值，不能代表某一主体买卖。最新日大幅变化待核验")}{' '}
            {latest.suspect_count} {t("只。")}</Note>
          <Panel
            title={t("ETF追踪明细")}
            action={<span className="muted">{t("点击表头排序 · 数据截止")}{result.asof}</span>}
          >
            <div className="controls wrap">
              <label className="grow">
                {t("筛选明细")}<input
                  aria-label={t("搜索ETF")}
                  placeholder={t("代码或基金名称")}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <label>
                {t("跟踪指数")}<select value={family} onChange={(e) => setFamily(e.target.value)}>
                  <option value="全部">{t("全部")}</option>
                  {result.groups.map((g: Row) => (
                    <option key={t(g.family)} value={t(g.family)}>{t(g.family)}</option>
                  ))}
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={onlyAbnormal}
                  onChange={(e) => setOnlyAbnormal(e.target.checked)}
                />{' '}
                {t("仅显示异常")}</label>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {[
                      ['code', 'ETF'],
                      ['family', t("指数")],
                      ['shares', t("最新份额")],
                      ['delta_1', t("1日变化")],
                      ['delta_7', t("7日变化")],
                      ['delta_30', t("30日变化")],
                      ['rate', t("单日变化率")],
                    ].map(([key, label]) => (
                      <th key={key}>
                        <button className="table-sort" onClick={() => toggleSort(key)}>
                          {t(label)}
                          {key === sort ? (descending ? ' ↓' : ' ↑') : ''}
                        </button>
                      </th>
                    ))}
                    <th>{t("状态")}</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((r) => (
                    <tr key={r.code}>
                      <td>
                        {r.name}
                        <small>{r.code}</small>
                      </td>
                      <td>{t(r.family)}</td>
                      <td>{r.shares == null ? '—' : fmt(r.shares / 1e8) + t("亿份")}</td>
                      {[1, 7, 30].map((k) => {
                        const v = r[(unit === 'flow' ? 'flow_' : 'delta_') + k]
                        return (
                          <td key={k} className={v > 0 ? 'up' : v < 0 ? 'down' : ''}>
                            {amount(v, unit)}
                          </td>
                        )
                      })}
                      <td>{pct(r.rate)}</td>
                      <td>
                        <span
                          className={'tag ' + (r.suspect ? 'warn' : r.abnormal ? 'active-tag' : '')}
                        >
                          {r.shares == null
                            ? t("未返回")
                            : r.suspect
                              ? t("待核验")
                              : r.abnormal
                                ? t("异常")
                                : t("常态")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">
              {t("当前显示")}{tableRows.length} / {result.rows.length}{' '}
              {t("只。表格筛选仅影响明细；顶部合计仍使用完整选定样本。")}</p>
          </Panel>
          <Panel title={t("按跟踪指数归集")}>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("跟踪指数")}</th>
                    <th>{t("有效 / 样本")}</th>
                    <th>{t("当日净增数量")}</th>
                    <th>{t("当日份额变化")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.groups.map((g: Row) => (
                    <tr key={t(g.family)}>
                      <td>{t(g.family)}</td>
                      <td>
                        {g.coverage} / {g.count}
                      </td>
                      <td>{g.positive}</td>
                      <td>{amount(g.delta, 'delta')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <details className="panel">
            <summary>{t("来源、数据缺口与计算口径")}</summary>
            <p className="muted">{t(result.method)}</p>
            <p className="muted">
              {t("份额日期使用交易所来源标签。沪深统计/交收时点可能不同；份额所属日、净值所属日和获取日分开保留，不作为历史时点可交易信号。")}</p>
            {data.errors?.length > 0 && (
              <div className="research">
                <b>{t("本次取数记录")}{data.errors.length} {t("项缺口或错误")}</b>
                {data.errors.map((e: Row, i: number) => (
                  <p key={i}>
                    <code>
                      {e.request.kind} {e.request.code || e.request.end}
                    </code>
                    ：{e.error}
                  </p>
                ))}
              </div>
            )}
            <p className="muted">
              {t("计算记录")}{run.id} {t("· 固定输入快照")}{run.inputs.length} {t("个")}</p>
            {run.sources
              .filter(
                (s: Row, i: number, a: Row[]) => a.findIndex((x) => x.source === s.source) === i,
              )
              .map((s: Row) => (
                <Source key={s.id} s={s} />
              ))}
          </details>
        </>
      )}
      <EtfEvidence />
    </>
  )
}
