import { useEffect, useState } from 'react'
import { Download, SlidersHorizontal, Footprints } from 'lucide-react'
import { useProject } from '../workspace/ProjectContext'
import type { PageProps } from '../App'
import { api, fmt, today, type Row } from '../api'
import { Panel, Metric, Note, Empty, LoadingButton, Source } from '../components'
import NationalChart from '../NationalChart'
import NationalTimeline from '../NationalTimeline'
import EtfEvidence from '../EtfEvidence'
const money = (v: any) => (v == null ? '—' : (v > 0 ? '+' : '') + fmt(v / 1e8) + ' 亿元')
const rank = (v: any) => (v == null ? '—' : fmt(v, 1) + '%')

export default function NationalTeam({ reload }: PageProps) {
  const { activeProject, linkRecord } = useProject()
  const [code, setCode] = useState('510300'),
    [universe, setUniverse] = useState<Row>({ '510300': '沪深300' }),
    [data, setData] = useState<Row | null>(null),
    [job, setJob] = useState<Row | null>(null),
    [windowSize, setWindowSize] = useState(252),
    [asof, setAsof] = useState(today),
    [start, setStart] = useState(new Date(Date.now() - 450 * 86400000).toLocaleDateString('sv-SE')),
    [end, setEnd] = useState(today),
    [components, setComponents] = useState(true),
    [settings, setSettings] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [selectedDay, setSelectedDay] = useState<string | null>(null)
  const load = async (params: Row = {}) => {
    const next = await api('/national/dashboard', { code, window: windowSize, asof, ...params })
    setData(next)
    setUniverse(next.universe)
    if (next.run) {
      setStart(next.run.params.start)
      setEnd(next.run.params.end)
    }
    return next
  }
  useEffect(() => {
    let alive = true
    setData(null)
    setMessage('')
    api('/national/dashboard', { code })
      .then((next) => {
        if (!alive) return
        setData(next)
        setUniverse(next.universe)
        if (next.run) {
          setStart(next.run.params.start)
          setEnd(next.run.params.end)
          setAsof(next.run.params.asof)
          setWindowSize(next.run.params.window)
          setComponents(next.run.params.include_components)
        }
      })
      .catch((e) => {
        if (alive) setMessage(e.message)
      })
    return () => {
      alive = false
    }
  }, [code])
  useEffect(() => {
    if (job?.status !== 'running') return
    let alive = true
    const timer = setTimeout(async () => {
      try {
        const next = await api('/national/jobs/' + job.id)
        if (!alive) return
        setJob(next)
        if (next.status === 'completed') {
          await load({ code: job.params.code })
          await reload()
          setMessage('更新完成，原始快照与计算记录已保存。')
        } else if (next.status !== 'running')
          setMessage(next.error || '任务已中断，可重新发起复用缓存')
      } catch (e: any) {
        if (alive) setMessage(e.message)
      }
    }, 1500)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [job])
  const refresh = async () => {
    setBusy(true)
    setMessage('')
    try {
      setJob(
        await api('/national/refresh', {
          code,
          start,
          end,
          asof: end,
          window: windowSize,
          include_components: components,
        }),
      )
      setAsof(end)
    } catch (e: any) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }
  const recalculate = async () => {
    setBusy(true)
    setMessage('')
    try {
      const projectId = activeProject?.id || null
      const next = await load({ include_components: components })
      if (next.run) await linkRecord('research', next.run.id, projectId)
      setSelectedDay(null)
    } catch (e: any) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }
  const run = data?.run,
    result = run?.result,
    latest = result?.latest,
    proof = result?.disclosures,
    period = proof?.latest,
    running = job?.status === 'running'
  const detail = selectedDay ? result?.daily.find((r: Row) => r.date === selectedDay) : null
  return (
    <>
      <div className="page-title">
        <div>
          <h1>国家队足迹</h1>
          <p>原文持仓、ETF资金与融资行为，沿着证据观察市场。</p>
        </div>
        <div className="actions">
          <button className="secondary" onClick={() => setSettings(!settings)}>
            <SlidersHorizontal size={16} /> 研究参数
          </button>
          <LoadingButton busy={busy || running || !data} onClick={refresh}>
            更新观察数据
          </LoadingButton>
        </div>
      </div>
      <div className="controls wrap national-controls">
        <label className="grow">
          观察ETF
          <select
            aria-label="国家队观察ETF"
            value={code}
            disabled={running}
            onChange={(e) => {
              setCode(e.target.value)
              setSelectedDay(null)
            }}
          >
            {Object.entries(universe).map(([c, f]) => (
              <option key={c} value={c}>
                {c} · {String(f)}
              </option>
            ))}
          </select>
        </label>
        <label>
          分位参考窗口
          <select
            aria-label="分位参考窗口"
            value={windowSize}
            onChange={(e) => setWindowSize(Number(e.target.value))}
          >
            {[60, 120, 252, 504].map((n) => (
              <option value={n} key={n}>
                {n}个此前交易日
              </option>
            ))}
          </select>
        </label>
        <label>
          研究截至
          <input
            aria-label="国家队研究截至"
            type="date"
            value={asof}
            onInput={(e) => setAsof(e.currentTarget.value)}
            onChange={(e) => setAsof(e.target.value)}
          />
        </label>
        <LoadingButton busy={busy || running} disabled={!result} onClick={recalculate}>
          按缓存重算
        </LoadingButton>
      </div>
      {result && (windowSize !== result.percentile.window || asof !== result.research_asof) && (
        <Note>参数已调整，点击“按缓存重算”应用到下方结果。</Note>
      )}
      {settings && (
        <Panel title="取数参数">
          <div className="controls wrap">
            <label>
              取数开始
              <input
                aria-label="足迹取数开始"
                type="date"
                value={start}
                onInput={(e) => setStart(e.currentTarget.value)}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label>
              取数结束
              <input
                aria-label="足迹取数结束"
                type="date"
                value={end}
                onInput={(e) => setEnd(e.currentTarget.value)}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={components}
                onChange={(e) => setComponents(e.target.checked)}
              />{' '}
              对照固定指数成分融资
            </label>
          </div>
          <p className="muted">
            默认补约450个自然日的份额与行情；融资取最近75个自然日。单次最多800天，自动分段并复用缓存。分位不足参考窗口时显示实际样本数；研究截至日期约束披露可用日。
          </p>
        </Panel>
      )}
      {running && (
        <Note>
          {job.stage} · {job.done}/{job.total} · 缺口或错误 {job.errors || 0}
          。首次补历史需要数分钟，已成功数据逐项缓存。
        </Note>
      )}
      {message && <Note>{message}</Note>}
      {!result ? (
        <Panel title="建立观察档案">
          <Empty>
            <Footprints size={28} />
            点击“更新观察数据”，补齐所选ETF的历史份额、融资与报告目录。
          </Empty>
        </Panel>
      ) : (
        <>
          <div className="etf-status">
            <span className="tag good">份额截至 {result.asof}</span>
            <span>
              研究截至 {result.research_asof} · {result.family} · {result.daily.length}个交易日
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
                加入当前项目
              </button>
            )}
            <a className="button secondary" href={'/api/research/export/' + run.id}>
              <Download size={14} /> 导出足迹分析
            </a>
          </div>
          {result.asof < result.research_asof && (
            <Note tone="warn">
              研究截至日与份额最新日不同；未发布日期保持缺失。已登记持仓仅代表对应报告期。
            </Note>
          )}
          <div className="metrics etf-metrics">
            <Metric
              label="原文最新持仓期末"
              value={period?.report_date || '尚未登记'}
              sub={
                period
                  ? '已登记最晚公告 ' + period.publication_date
                  : '报告目录与持有人线索可供核查'
              }
            />
            <Metric
              label="核心主体已识别持仓"
              value={period?.shares == null ? '—' : fmt(period.shares / 1e8) + ' 亿份'}
              sub={
                period
                  ? `${period.core_count}家 · ${period.report_date}期末记录合计`
                  : '按已登记原文计算，未知不填零'
              }
            />
            <Metric
              label="当日估算净申赎"
              value={
                <span className={latest.flow > 0 ? 'up' : latest.flow < 0 ? 'down' : ''}>
                  {money(latest.flow)}
                </span>
              }
              sub="日份额差 × 同日单位净值"
            />
            <Metric
              label="申赎绝对值历史分位"
              value={rank(latest.flow_pct)}
              sub={`此前有效 ${latest.flow_n}/${result.percentile.window} · 不含当天`}
            />
            <Metric
              label="ETF融资净新增"
              value={
                <span
                  className={latest.margin_net > 0 ? 'up' : latest.margin_net < 0 ? 'down' : ''}
                >
                  {money(latest.margin_net)}
                </span>
              }
              sub={latest.margin_basis || '尚无融资记录'}
            />
            <Metric
              label="ETF融资余额"
              value={
                latest.margin_balance == null ? '—' : fmt(latest.margin_balance / 1e8) + ' 亿元'
              }
              sub={`融资异动分位 ${rank(latest.margin_net_pct)} · n=${latest.margin_net_n}`}
            />
          </div>
          <Panel
            title="价格 × 份额 × 披露节点"
            action={<span className="tag">市场数据 + 原文披露</span>}
          >
            <NationalChart rows={result.daily} events={result.events} onSelect={setSelectedDay} />
            {detail && (
              <div className="research">
                <b>{detail.date} · 当日观察</b>
                <p>
                  估算申赎 {money(detail.flow)} · 绝对值分位 {rank(detail.flow_pct)}（n=
                  {detail.flow_n}）；ETF融资净新增 {money(detail.margin_net)}，成交额分位{' '}
                  {rank(detail.turnover_pct)}（n={detail.turnover_n}）。
                </p>
                <button className="text-button" onClick={() => setSelectedDay(null)}>
                  收起当天指标
                </button>
              </div>
            )}
          </Panel>
          <NationalTimeline proof={proof} reports={result.reports} />
          <Panel title="融资资金对照" action={<span className="tag">市场代理</span>}>
            <NationalChart rows={result.daily} mode="margin" />
            {result.components.expected > 0 ? (
              <Note>
                指数 {result.components.index_code}，固定名单日期 {result.components.date}
                ；最新融资记录 {latest.component_coverage}/{latest.component_expected}，净新增有效{' '}
                {latest.component_net_coverage}/{latest.component_expected}
                。缺记录包含非两融标的，均保留缺失。沪市净新增用买入−偿还，深市用相邻余额差代理；合计仅含已覆盖样本。此名单回看不作为历史时点回测。
              </Note>
            ) : (
              <Note>当前未取得或未启用成分目录；仍显示ETF自身融资。部分指数暂无自动成分入口。</Note>
            )}
            <div className="research">
              <b>{result.inference.direction || '当前缺少申赎或融资数据，暂不比较方向'}</b>
              <p>{result.inference.basis} 以上是市场行为观察，不转换为国家队买卖金额或出手概率。</p>
            </div>
          </Panel>
          <Panel title="近期资金与异动分位">
            <p className="muted">
              各日只与此前滚动窗口比较，最少20个有效样本。缺失不补零；分位越高表示金额或变动幅度越少见。
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>交易日</th>
                    <th>净份额变化</th>
                    <th>估算申赎</th>
                    <th>申赎分位 / n</th>
                    <th>成交额分位 / n</th>
                    <th>ETF融资净新增</th>
                    <th>成分融资覆盖</th>
                  </tr>
                </thead>
                <tbody>
                  {[...result.daily]
                    .reverse()
                    .slice(0, 20)
                    .map((r: Row) => (
                      <tr key={r.date}>
                        <td>
                          <button className="text-button" onClick={() => setSelectedDay(r.date)}>
                            {r.date}
                          </button>
                        </td>
                        <td>
                          {r.delta == null
                            ? '—'
                            : (r.delta > 0 ? '+' : '') + fmt(r.delta / 1e8) + ' 亿份'}
                          {r.suspect && <small>大幅变化待核验</small>}
                        </td>
                        <td className={r.flow > 0 ? 'up' : r.flow < 0 ? 'down' : ''}>
                          {money(r.flow)}
                        </td>
                        <td>
                          {rank(r.flow_pct)}
                          <small>n={r.flow_n}</small>
                        </td>
                        <td>
                          {rank(r.turnover_pct)}
                          <small>n={r.turnover_n}</small>
                        </td>
                        <td>{money(r.margin_net)}</td>
                        <td>
                          {r.component_coverage}/{r.component_expected}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <details className="panel">
            <summary>来源、覆盖与复算依据</summary>
            <p className="muted">{result.method}</p>
            <p className="muted">
              {result.percentile.method} 计算记录 {run.id}，固定输入 {run.inputs.length} 个快照。
            </p>
            {data?.errors?.length > 0 && (
              <div className="research">
                <b>本次取数 {data?.errors.length} 项缺口或错误</b>
                {data?.errors.map((e: Row, i: number) => (
                  <p key={i}>
                    {e.request.kind} {e.request.code || e.request.end}：{e.error}
                  </p>
                ))}
              </div>
            )}
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
      <EtfEvidence
        key={code}
        defaultCode={code}
        cutoff={result?.research_asof || asof}
        onSaved={() => load()}
      />
    </>
  )
}
