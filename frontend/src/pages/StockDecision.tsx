import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type FormEvent } from 'react'
import { ArrowDownRight, ArrowUpRight, Eye, RefreshCw, Search, ScanLine } from 'lucide-react'
import DecisionChart, { type DecisionLevel } from '../decision/DecisionChart'
import DecisionStudy from '../decision/DecisionStudy'
import TrackedFactors, { type FactorKey } from '../decision/TrackedFactors'
import { chartEvents, type DecisionResponse, type Plan, type Scenario } from '../decision/model'
import { request } from '../http'
import { numberLocale, t, useLocale } from '../i18n'
import { useProject } from '../workspace/ProjectContext'

const readHash = () => window.location.hash
function subscribeHash(callback: () => void) {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}
const getParams = () => new URLSearchParams(readHash().split('?')[1])
const destination = (symbol: string, project: string | null, history?: { snapshot: string; asOf: string }) => {
  const query = new URLSearchParams({ symbol })
  if (project) query.set('project', project)
  if (history) { query.set('snapshot', history.snapshot); query.set('as_of', history.asOf) }
  return `#stock?${query}`
}

const roles = { support: '支撑 / 失效位', resistance: '阻力 / 确认位', reference_target: '上方结构参考' } as const
const scenarios = { breakout: '放量突破', retest: '触及后收复', support_failure: '支撑失效', otherwise: '继续观望' } as const
const actions = { review_entry_after_close: '全部满足后，可在收盘后复核是否考虑买入。',
  review_exit_if_holding: '原结构假设失效；若持有，复核是否减仓或离场。', watch: '没有满足条件时，不新增入场假设。' } as const
const reasons: Record<string, string> = {
  unverified_input: '数据条件不足，暂不生成有效交易计划。', no_qualified_anchors: '没有足够近、已经确认的结构锚点。',
  support_already_broken: '收盘已低于结构支撑，等待形成新结构。', await_close_confirmation: '等待观察交易日收盘确认。',
  no_clear_entry_room: '现有结构未提供足够的上方空间。',
}
const issues: Record<string, string> = {
  calendar_outdated: '交易日历需要更新', stale_quotes: '最近应有的收盘行情仍未返回', provider_refresh_failed: '来源更新失败',
  last_session_untradable: '最新观察日无有效成交', recent_session_gap: '近期有未解释的交易日缺口',
  recent_reference_discontinuity: '近期前收参考出现跳变，需核对公司行动', retrospective_snapshot: '历史回看，不作为当前交易计划',
  session_unverified: '下一观察日未获核验', zero_latest_volume: '最近一日成交量为零', volume_history_short: '连续有效的量能基准不足',
  refreshing: '行情正在更新', transport_failure: '无法核实最新行情状态',
  observation_closed: '该观察日已收盘，请刷新后查看新的条件。',
}
const trends: Record<string, string> = { rising: '高低点抬升', falling: '高低点下移', mixed: '高低点方向分化', insufficient: '趋势证据不足' }
const phases: Record<string, string> = { unresolved: '结构未定', below_support: '支撑下方', above_resistance: '阻力上方', inside_range: '关键价位之间' }
const relations: Record<string, string> = { below: '中枢下方', inside: '中枢内', above: '中枢上方' }
const observationStatuses = { intact: '此快照内未重新触及', reentered: '后来重新触及边界', unverifiable: '后续数据不连续，状态未核验' } as const
const fields = { close: '收盘价', low: '当日最低价', volume: '当日总成交量' } as const
const operators = { gt: '>', lt: '<', gte: '≥', lte: '≤' } as const
const n = (value: number, digits = 4) => new Intl.NumberFormat(numberLocale(), { maximumFractionDigits: digits }).format(value)
type FactorSelection = { symbol: string; project_id: string | null; selected: FactorKey[] }

function FactorPanel({ symbol, project, data, unit }: { symbol: string; project: string | null; data: DecisionResponse; unit: string }) {
  const [preference, setPreference] = useState<FactorSelection | null>(null)
  const [error, setError] = useState('')
  const path = `/decision/${symbol}/factors${project ? '?' + new URLSearchParams({ project_id: project }) : ''}`
  const pendingSave = useRef<AbortController | null>(null)
  const accept = useCallback((response: FactorSelection) => {
    if (response.symbol !== symbol || response.project_id !== project) throw new Error(t('行情回执和当前证券或历史截点不一致。'))
    setPreference(response)
  }, [symbol, project])
  useEffect(() => {
    const controller = new AbortController()
    const signal = controller.signal
    void request<FactorSelection>(path, { signal }).then(result => { if (!signal.aborted) accept(result) })
      .catch((e: Error) => { if (!signal.aborted) setError(e.message) })
    return () => { controller.abort(); pendingSave.current?.abort() }
  }, [path, accept])

  async function save(selected: FactorKey[]) {
    const controller = new AbortController()
    pendingSave.current = controller
    try {
      const response = await request<FactorSelection>(path, { method: 'PUT', body: JSON.stringify({ selected }), signal: controller.signal })
      if (!controller.signal.aborted) accept(response)
    } finally {
      if (pendingSave.current === controller) pendingSave.current = null
    }
  }
  return <TrackedFactors factors={data.factors} savedKeys={preference?.selected ?? []} onSave={save}
    historical={data.input?.historical} volumeUnit={unit} pending={!preference && !error} preferenceError={error || undefined}/>
}

function Playbook({ plan, unit, select }: { plan: Plan; unit: string; select: (level: DecisionLevel) => void }) {
  return <section className="stock-playbook" role="complementary" aria-label={t('当前判断与观察条件')}>
    <section className="stock-current">
      <h2>{t('当前判断')}</h2>
      <div className="stock-stance"><Eye size={18} aria-hidden="true"/><strong>{t('观望')}</strong><span>{t(reasons[plan.watch_reason] ?? '暂无条件')}</span></div>
      <dl className="stock-structure-facts">
        <div><dt>{t('近期分型趋势')}</dt><dd>{t(trends[plan.trend] ?? '趋势证据不足')}</dd></div>
        <div><dt>{t('结构阶段')}</dt><dd>{t(phases[plan.phase] ?? '结构未定')}</dd></div>
        {plan.volume.observed_ratio !== null && <div><dt>{t('最近一日成交量 / 前期均量')}</dt><dd>{n(plan.volume.observed_ratio, 2)}×</dd></div>}
      </dl>
      {!!plan.data_issues.length && <ul className="stock-issues">{plan.data_issues.map(issue => <li key={issue}>{t(issues[issue] ?? issue)}</li>)}</ul>}
      <p className="stock-method">{t(plan.data_quality === 'checked' ? '行情与交易日已核对' : '行情或交易日有待核对')} · {t('规则收益未经样本外验证')}</p>
    </section>
    <section className="stock-next">
      <div className="stock-next-heading"><h2>{t(plan.data_quality === 'limited' ? '原快照观察日' : '观察交易日')}</h2><span>{plan.observation_session ?? t('未核验')}</span></div>
      {plan.scenarios.map(scenario => <ScenarioCard key={scenario.kind} scenario={scenario} plan={plan} unit={unit} select={select}/>) }
      <p className="stock-method">{t('这些条件用完整日线确认。满足条件后，最早也只能在后续可交易日评估执行；跳空、费用、滑点和涨跌停都会影响结果。')}</p>
    </section>
  </section>
}

function ScenarioCard({ scenario, plan, unit, select }: { scenario: Scenario; plan: Plan; unit: string; select: (level: DecisionLevel) => void }) {
  const Icon = scenario.action === 'review_entry_after_close' ? ArrowUpRight : scenario.action === 'review_exit_if_holding' ? ArrowDownRight : Eye
  return <article className={`stock-scenario stock-scenario-${scenario.action}`}>
    <h3><Icon size={17} aria-hidden="true"/>{t(scenarios[scenario.kind])}</h3>
    {!!scenario.conditions.length && <ul>{scenario.conditions.map((condition, index) => <li key={index}>
      {t(fields[condition.field])} {operators[condition.comparison]} <strong>{n(condition.value, condition.field === 'volume' ? 0 : 4)}</strong> {condition.field === 'volume' ? unit : t('元')}
    </li>)}</ul>}
    <p>{t(actions[scenario.action])}</p>
    {scenario.evidence_roles.map(role => {
      const level = plan.levels.find(candidate => candidate.role === role)
      return level && <button key={role} type="button" className="stock-proof-link" aria-controls="stock-price-chart" onClick={() => select(level)}>
        {t(roles[role])} {n(level.price)}<ArrowUpRight size={13} aria-hidden="true"/>
      </button>
    })}
  </article>
}

function DecisionDetail({ symbol, project, snapshot, asOf }: { symbol: string; project: string | null; snapshot: string | null; asOf: string | null }) {
  const [data, setData] = useState<DecisionResponse | null>(null)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)
  const [selection, setSelection] = useState<{ id: string; role?: DecisionLevel['role']; snapshot?: string } | null>(null)
  const [history, setHistory] = useState('')
  const [expiredDeadline, setExpiredDeadline] = useState(0)
  const [period, setPeriod] = useState<'daily' | 'weekly'>('daily')
  const chartFrame = useRef<HTMLDivElement>(null)
  const chartSeries = period === 'weekly' ? data?.weekly : data
  const visibleEvents = useMemo(() => chartSeries ? chartEvents(chartSeries) : [], [chartSeries])
  const input = data?.input
  const select = useCallback((id: string, role?: DecisionLevel['role']) => setSelection({ id, role, snapshot: input?.id }), [input?.id])
  const showOnDailyChart = (id: string, role?: DecisionLevel['role']) => {
    setPeriod('daily')
    select(id, role)
    chartFrame.current?.focus()
  }
  const showDailyEvidence = (level: DecisionLevel) => showOnDailyChart(level.evidence.id, level.role)
  const selected = selection?.snapshot === input?.id ? selection : null

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    const query = new URLSearchParams()
    if (project) query.set('project_id', project)
    if (snapshot) query.set('snapshot_id', snapshot)
    if (asOf) query.set('as_of', asOf)
    const get = `/decision/${symbol}?${query}`
    const accept = (result: DecisionResponse) => {
      if (signal.aborted) return
      if (result.symbol !== symbol || result.project_id !== project || (snapshot && (
        result.input?.id !== snapshot || !result.input.historical || (asOf && result.input.expected_session !== asOf)
      ))) {
        setError(t('行情回执和当前证券或历史截点不一致。'))
        return
      }
      setData(result)
    }
    let fresherApplied = false
    setWorking(true); setError('')
    if (refreshKey === 0 || snapshot) {
      void request<DecisionResponse>(get, { signal }).then(result => {
        if (!fresherApplied) accept(result)
      }).catch((e: Error) => { if (!signal.aborted && snapshot) setError(e.message) })
        .finally(() => { if (!signal.aborted && snapshot) setWorking(false) })
    }
    if (!snapshot) {
      void request<DecisionResponse>(`/decision/${symbol}/refresh?${query}`, { method: 'POST', signal, timeoutMs: 120_000 })
        .then(result => { fresherApplied = true; accept(result) })
        .catch((e: Error) => { if (!signal.aborted) setError(e.message) })
        .finally(() => { if (!signal.aborted) setWorking(false) })
    }
    return () => controller.abort()
  }, [symbol, project, snapshot, asOf, refreshKey])

  const originalPlan = data?.plan
  const deadline = !snapshot && originalPlan?.observation_session
    ? Date.parse(`${originalPlan.observation_session}T15:00:00+08:00`) : 0
  useEffect(() => {
    if (!deadline) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const expire = () => {
      clearTimeout(timer)
      const remaining = deadline - Date.now()
      if (remaining <= 0) setExpiredDeadline(deadline)
      else timer = setTimeout(expire, Math.min(remaining, 2_147_483_647))
    }
    expire()
    window.addEventListener('focus', expire)
    document.addEventListener('visibilitychange', expire)
    return () => {
      clearTimeout(timer)
      window.removeEventListener('focus', expire)
      document.removeEventListener('visibilitychange', expire)
    }
  }, [deadline])
  const expired = !!deadline && (expiredDeadline === deadline || Date.now() >= deadline)
  const plan: Plan | null | undefined = originalPlan && (working || error || expired) ? {
    ...originalPlan, watch_reason: 'unverified_input', data_quality: 'limited',
    data_issues: [...(working ? ['refreshing'] : []), ...(error ? ['transport_failure'] : []),
      ...(expired ? ['observation_closed'] : []), ...originalPlan.data_issues],
    scenarios: originalPlan.scenarios.filter(scenario => scenario.kind === 'otherwise'),
  } : originalPlan
  const volumeUnit = t(input?.volume_unit === 'units' ? '份' : '股')
  const selectedEvent = visibleEvents.find(event => event.structure.id === selected?.id)
  const observations = data?.structure_observations ?? []
  const studyQuery = input && new URLSearchParams({ snapshot_id: input.id })
  if (studyQuery && project) studyQuery.set('project_id', project)
  if (studyQuery && asOf) studyQuery.set('as_of', asOf)
  return <section className="stock-detail">
    <div className="stock-detail-header">
      <div><h1>{data?.instrument?.name ?? symbol}</h1><p>{symbol}{data?.instrument && ` · ${data.instrument.exchange} · ${t(data.instrument.kind === 'etf' ? 'ETF' : '股票')}`}</p></div>
      <div className="stock-header-meta">
        <span aria-live="polite">{working ? t('正在核对行情…') : input?.historical
          ? t('历史回看 · 截点 {date}', { date: input.expected_session ?? plan?.as_of ?? '' })
          : plan ? t('完成日线截至 {date}', { date: plan.as_of }) : t('暂无已核验日线')}</span>
        {snapshot ? <a href={destination(symbol, project)}>{t('返回最新行情')}</a> :
          <button type="button" className="secondary" onClick={() => { setWorking(true); setRefreshKey(key => key + 1) }} disabled={working}><RefreshCw size={16} aria-hidden="true"/>{t('刷新行情')}</button>}
      </div>
    </div>
    {(error || data?.warning) && <p className="stock-notice" role="status">{t(input ? '保留上次成功的日线。' : '尚未收到有效日线。')} {error || data?.warning}</p>}
    {working && input && <p className="stock-subtle" role="status">{t('先显示固定快照，更新完成后再校验条件。')}</p>}
    {!input && !error && !data?.warning && <p className="stock-empty" role="status">{t(working ? '正在取得证券身份、交易日历与完成日线…' : '暂无已核验日线')}</p>}
    {input && !plan && <p className="stock-empty" role="status">{t('这个快照没有可分析的成交日线。')}</p>}
    {input && plan && data && <>
      <div className="stock-detail-grid">
        <div className="stock-detail-main">
          <div id="stock-price-chart" className="stock-chart-frame" tabIndex={-1} ref={chartFrame} aria-label={t('价格和结构图')}>
            {data.weekly && <div className="stock-period-strip">
              <div role="group" aria-label={t('切换图表周期')}>
                <button type="button" aria-pressed={period === 'daily'} onClick={() => { setPeriod('daily'); setSelection(null) }}>{t('日线')}</button>
                <button type="button" aria-pressed={period === 'weekly'} onClick={() => { setPeriod('weekly'); setSelection(null) }}>{t('周线')}</button>
              </div>
              <span>{data.weekly.context.completed_through ? t('完整周线截至 {date}', { date: data.weekly.context.completed_through }) : t('暂无可靠的连续周线')}
                {data.weekly.context.status === 'ready' && ` · ${t(trends[data.weekly.context.trend] ?? '趋势证据不足')}`}
              </span>
            </div>}
            <DecisionChart key={input.id + period} period={period} bars={chartSeries?.bars ?? []} structures={visibleEvents}
              levels={period === 'daily' ? plan.levels : []} selectedId={selected?.id ?? null} selectedRole={selected?.role ?? null} onSelect={select} volumeUnit={volumeUnit}
              observations={period === 'daily' ? observations.map(item => ({ id: item.id, index: item.available_index, geometry: item.geometry_date,
                available: item.available_date, title: t(item.side === 'above' ? '上沿外侧回抽' : '下沿外侧回抽') })) : []}/>
            {period === 'weekly' && <p className="stock-period-note">{t('周线只使用完整交易周，作为日线计划的背景。日线触发价不画在周线上。')}</p>}
          </div>
          <section className="stock-evidence" aria-label={t('结构依据')}>
            <div className="stock-evidence-head"><h2>{t('结构依据')}</h2><span>{t(plan.level_basis === 'confirmed_center' ? '已确认中枢' : plan.level_basis ? '已确认分型' : '未形成合格锚点')}</span></div>
            {plan.last_center && <p>{t(relations[plan.last_center.relation] ?? '结构未定')} · {n(plan.last_center.lower)}–{n(plan.last_center.upper)} · {t('确认于 {date}', { date: plan.last_center.confirmed_date })}{!plan.last_center.used_for_levels && ` · ${t('仅作结构背景')}`}</p>}
            {!!plan.levels.length && <ul className="stock-levels">{plan.levels.map(level => <li key={level.role}>
              <button type="button" className="stock-proof-link" aria-pressed={selected?.role === level.role} aria-controls="stock-price-chart" onClick={() => showDailyEvidence(level)}>
                <ScanLine size={15} aria-hidden="true"/>{t(roles[level.role])} <strong>{n(level.price)}</strong>
              </button><span>{t('形态日 {date}', { date: level.evidence.geometry_date })} · {t('确认于 {date}', { date: level.evidence.confirmed_date })}</span>
            </li>)}</ul>}
            {!!observations.length && <details className="stock-observations">
              <summary>{t('日线中枢外侧回抽')}</summary>
              <p>{t('按结构确认日标记。它提供结构背景，不作为缠论买卖点或交易条件。')}</p>
              <ul className="stock-levels">{[...observations].reverse().map(item => <li key={item.id}>
                <button type="button" className="stock-proof-link" aria-pressed={selected?.id === item.id && period === 'daily'}
                  aria-controls="stock-price-chart" onClick={() => showOnDailyChart(item.id)}>
                  <ScanLine size={15} aria-hidden="true"/>{t(item.side === 'above' ? '上沿外侧回抽' : '下沿外侧回抽')} {n(item.edge)}
                </button>
                <span>{t('形态日 {date}', { date: item.geometry_date })} · {t('确认于 {date}', { date: item.available_date })}</span>
                <span>{t(observationStatuses[item.status])} · {item.status_date}</span>
              </li>)}</ul>
            </details>}
            {selectedEvent && period === 'daily' && <p className="stock-selection" aria-live="polite">{t('图上结构')} <code>{selectedEvent.structure.id}</code> · {t('首次可见 {date}', { date: selectedEvent.structure.first_seen_date })} · {selectedEvent.structure.confirmed_date ? t('确认于 {date}', { date: selectedEvent.structure.confirmed_date }) : t('候选，尚未确认')}</p>}
          </section>
        </div>
        <Playbook plan={plan} unit={volumeUnit} select={showDailyEvidence}/>
      </div>
      {!!data.factors?.length && <FactorPanel symbol={symbol} project={project} data={data} unit={volumeUnit}/>}
      {studyQuery && <DecisionStudy key={studyQuery.toString()} endpoint={`/decision/${symbol}/evaluation?${studyQuery}`}/>}
      <details className="stock-source">
        <summary>{t('行情来源、计算口径与回看')}</summary>
        <p><a href={input.source_url} target="_blank" rel="noreferrer">{input.source}</a> · {t('未复权')} · {input.start_date} – {input.end_date} · {input.fetched_at}</p>
        <p><a href={input.calendar_source_url} target="_blank" rel="noreferrer">{input.calendar_source}</a> · {t('快照')} <code>{input.id}</code> · {plan.rule_version} / {plan.structure_version}</p>
        <p>SHA-256 <code>{input.sha256}</code></p>
        <p>{t('图形画在形态发生的位置；是否已经可用，以确认日为准。周线使用同一识别算法，作为更长周期的独立背景。')}</p>
        <p>{t('缺口 {count}', { count: input.missing_sessions.length })} · {t('已知停牌 {count}', { count: input.suspended_sessions.length })} · {t('前收参考跳变 {count}', { count: input.reference_breaks.length })}</p>
        <form onSubmit={event => { event.preventDefault(); if (history) location.hash = destination(symbol, project, { snapshot: input.id, asOf: history }) }}>
          <label>{t('按交易日回看')} <select value={history} onChange={event => setHistory(event.target.value)}>
            <option value="">{t('选择交易日')}</option>
            {data.bars.slice(-80).reverse().map(bar => <option key={bar.date} value={bar.date}>{bar.date}</option>)}
          </select></label>
          <button className="secondary" type="submit" disabled={!history}>{t('打开历史截点')}</button>
        </form>
      </details>
    </>}
  </section>
}

export default function StockDecision() {
  useLocale()
  const hash = useSyncExternalStore(subscribeHash, readHash, () => '')
  const route = useMemo(getParams, [hash])
  const symbol = route.get('symbol') || ''
  const project = route.get('project')
  const snapshot = route.get('snapshot')
  const asOf = route.get('as_of')
  const { activeProject } = useProject()
  const [lookup, setLookup] = useState('')
  const [reopen, setReopen] = useState(0)
  function open(event: FormEvent) {
    event.preventDefault()
    const chosen = lookup.trim()
    if (!/^[0-9]{6}$/.test(chosen)) return
    const member = activeProject?.symbols.includes(chosen) ? activeProject.id : null
    const next = destination(chosen, member)
    if (location.hash === next) setReopen(value => value + 1)
    else location.hash = next
  }
  return <div className="stock-decision">
    <form className="stock-lookup" onSubmit={open}>
      <div className="stock-lookup-controls">
        <label className="stock-lookup-label"><Search size={17} aria-hidden="true"/><span>{t('股票或 ETF 代码')}</span><input value={lookup} onChange={event => setLookup(event.target.value)}
          inputMode="numeric" pattern="[0-9]{6}" placeholder="600105" required /></label>
        <button type="submit">{t('打开标的分析')}</button>
      </div>
      {activeProject?.symbols.filter(value => /^[0-9]{6}$/.test(value)).map(value => <a key={value} href={destination(value, activeProject.id)}>{value}</a>)}
    </form>
    {/^[0-9]{6}$/.test(symbol) && (!asOf || snapshot) ?
      <DecisionDetail key={[symbol, project, snapshot, asOf, reopen].join(':')} symbol={symbol} project={project} snapshot={snapshot} asOf={asOf}/>
      : <div className="stock-empty"><h1>{t('个股与 ETF')}</h1><p>{t('输入沪深六位代码，打开已完成日线、缠论结构和观察条件。')}</p></div>}
    <details className="stock-source stock-market-context">
      <summary>{t('市场背景')}</summary>
      <p>{t('大盘用作参考。跟踪个股或 ETF 时，观察条件以该标的自己的行情为准。')}</p>
      <div className="stock-market-links">
        <a href={destination('510300', null)}>{t('沪深 300 ETF · 宽基参考')}</a>
        <a href="#etf">{t('ETF 资金')}</a>
        <a href="#evidence">{t('筹码与情绪')}</a>
      </div>
    </details>
  </div>
}
