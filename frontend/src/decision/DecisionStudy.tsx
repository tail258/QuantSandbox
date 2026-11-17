import { useEffect, useRef, useState } from 'react'
import { request } from '../http'
import { t, useLocale } from '../i18n'
import './decision-study.css'

type Statistics = {
  count: number
  mean_return: number | null
  stressed_count: number
  stressed_mean_return: number | null
}

type Scenario = {
  kind: 'breakout' | 'retest' | 'support_failure'
  triggered: number
  untriggered: number
  events: Statistics
  comparison: Statistics
  excluded: Record<string, number>
}

type StudyResult = {
  start: string
  end: string
  holding_sessions: number
  assumptions: {
    price_tick: number
    slippage_bps: number
    round_trip_cost_bps: number
  }
  counts: {
    scheduled_observations: number
    evaluated_observations: number
    excluded_observations: number
  }
  exclusions: Record<string, number>
  scenarios: Scenario[]
}

const copies = {
  en: {
    title: 'Historical event study', run: 'Run study', retry: 'Retry study', busy: 'Evaluating historical sessions…',
    failure: 'The study could not run.',
    intro: 'Compare what happened after the same rule triggered or did not trigger on this instrument.',
    window: 'Study window', observation: 'Scheduled observations', evaluated: 'Rule evaluated', excluded: 'Observation excluded',
    triggered: 'Triggered', comparison: 'Eligible, not triggered',
    scored: (scored: string, total: string) => `${scored} of ${total} scored`,
    stressedScored: (sample: string) => `${sample} scored`,
    mean: 'Mean price change', stressed: 'After assumed costs',
    unavailable: 'No scorable observations.', detail: 'Exclusions by reason',
    reference: (sessions: string) => `The first reference is the opening price on the next exchange session after the observation. The second is the opening price ${sessions} exchange session(s) later. Access to the auction, fills and historical limit prices are unverified.`,
    cost: (tick: string, slippage: string, fees: string) => `Cost sensitivity uses a CNY ${tick} price tick, ${slippage} bp of adverse slippage per side and ${fees} bp of round-trip costs. For entries, both the observed opening price and the adverse-rounded price must fit the plan.`,
    limits: 'This single-snapshot comparison uses unadjusted prices. Historical data may have been revised, and overlapping windows share observations.',
    support: 'Negative values indicate a subsequent fall in the instrument price.',
    observationPhase: { prior: 'Prior session', observation: 'Observation session', outcome: 'Reference window' },
    reasons: {
      missing_bar: 'Missing daily bar', suspended: 'Suspended', trading_status_unverified: 'Trading status unverified',
      invalid_ohlcv: 'Invalid daily prices or volume', reference_unverified: 'Previous-close reference unavailable',
      reference_discontinuity: 'Previous-close reference discontinuity', after_cutoff: 'Outcome beyond the study cutoff',
      open_unavailable: 'Opening price unavailable', open_off_tick: 'Opening price off the tick grid',
      entry_open_outside_plan: 'Opening price outside the plan after the entry check',
      prior_session_unavailable: 'Prior exchange session unavailable', recent_session_gap: 'Recent missing or invalid session',
      recent_reference_discontinuity: 'Recent previous-close reference discontinuity',
      volume_history_short: 'Insufficient volume history', no_eligible_rule: 'No eligible rule',
    },
    kinds: { breakout: 'Breakout', retest: 'Retest', support_failure: 'Support failure' },
    otherReason: 'Other data restriction',
  },
  zh: {
    title: '历史事件研究', run: '运行研究', retry: '重试研究', busy: '正在评估历史交易日…',
    failure: '无法运行这项研究。',
    intro: '比较同一标的在规则触发和符合观察条件但未触发后的价格变化。',
    window: '研究区间', observation: '计划观察日', evaluated: '已评估规则', excluded: '已排除观察日',
    triggered: '已触发', comparison: '符合条件但未触发',
    scored: (scored: string, total: string) => `${scored} / ${total} 份可计分`,
    stressedScored: (sample: string) => `${sample} 份可计分`,
    mean: '平均价格变化', stressed: '计入假设成本后',
    unavailable: '该组没有可计分样本。', detail: '查看排除原因',
    reference: (sessions: string) => `第一个参考价取观察日后下一交易日开盘价，第二个取再过 ${sessions} 个交易日的开盘价。开盘竞价能否参与、具体成交及历史涨跌停价均未核验。`,
    cost: (tick: string, slippage: string, fees: string) => `成本敏感性按 ${tick} 元最小报价单位、每边 ${slippage} 基点不利滑点和 ${fees} 基点往返费用估算。入场观察要求实际开盘价与按不利滑点取整后的参考价均在计划区间内。`,
    limits: '结果来自同一份未复权快照。历史行情可能经过修订，重叠区间之间共用部分观察值。',
    support: '负值表示该标的价格之后下跌。',
    observationPhase: { prior: '前一交易日', observation: '观察日', outcome: '参考区间' },
    reasons: {
      missing_bar: '日线缺失', suspended: '停牌', trading_status_unverified: '交易状态未核验',
      invalid_ohlcv: '日线价格或成交量无效', reference_unverified: '缺少前收参考价',
      reference_discontinuity: '前收参考价不连续', after_cutoff: '结果超出研究截止日',
      open_unavailable: '开盘价缺失', open_off_tick: '开盘价不符合最小变动单位',
      entry_open_outside_plan: '开盘价未通过计划价格区间检查',
      prior_session_unavailable: '缺少前一交易日', recent_session_gap: '近期交易日缺失或无效',
      recent_reference_discontinuity: '近期前收参考价不连续',
      volume_history_short: '成交量历史不足', no_eligible_rule: '无适用规则',
    },
    kinds: { breakout: '放量突破', retest: '回踩确认', support_failure: '支撑失效' },
    otherReason: '其他数据限制',
  },
}

type Copy = typeof copies.en

function reasonText(reason: string, copy: Copy): string {
  const messages: Record<string, string> = copy.reasons
  if (Object.hasOwn(messages, reason)) return messages[reason]
  for (const [phase, label] of Object.entries(copy.observationPhase)) {
    const fragment = reason.slice(phase.length + 1)
    if (reason.startsWith(`${phase}_`) && Object.hasOwn(messages, fragment)) return `${label} · ${messages[fragment]}`
  }
  return copy.otherReason
}

function Exclusions({ exclusions, copy, numbers }: {
  exclusions: Record<string, number>
  copy: Copy
  numbers: Intl.NumberFormat
}) {
  const reasons = Object.entries(exclusions)
  if (!reasons.length) return null

  return <details className="decision-study-exclusions">
    <summary>{copy.detail}</summary>
    <ul>{reasons.map(([reason, count]) => <li key={reason}>
      {reasonText(reason, copy)} <strong>{numbers.format(count)}</strong>
    </li>)}</ul>
  </details>
}

function Cohort({ title, total, statistics, showStress, copy, numbers, percent }: {
  title: string
  total: number
  statistics: Statistics
  showStress: boolean
  copy: Copy
  numbers: Intl.NumberFormat
  percent: Intl.NumberFormat
}) {
  const renderPercent = (value: number | null) => value === null ? '—' : percent.format(value)

  return <div className="decision-study-cohort">
    <dt><strong>{title}</strong> <span>{copy.scored(numbers.format(statistics.count), numbers.format(total))}</span></dt>
    <dd>
      {statistics.mean_return === null ? copy.unavailable : <>
        <span>{copy.mean} <strong>{renderPercent(statistics.mean_return)}</strong></span>
        {showStress && <span>{copy.stressed} <strong>{renderPercent(statistics.stressed_mean_return)}</strong>
          {statistics.stressed_count !== statistics.count && ` · ${copy.stressedScored(numbers.format(statistics.stressed_count))}`}
        </span>}
      </>}
    </dd>
  </div>
}

function StudyReport({ result, copy, locale }: { result: StudyResult; copy: Copy; locale: string }) {
  const numbers = new Intl.NumberFormat(locale, { maximumFractionDigits: 3 })
  const percent = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2, signDisplay: 'exceptZero' })
  const { counts, assumptions } = result

  return <div className="decision-study-result">
    <p className="decision-study-window">{copy.window} <strong>
      <time dateTime={result.start}>{result.start}</time> – <time dateTime={result.end}>{result.end}</time>
    </strong></p>
    <dl className="decision-study-counts">
      <div><dt>{copy.observation}</dt><dd>{numbers.format(counts.scheduled_observations)}</dd></div>
      <div><dt>{copy.evaluated}</dt><dd>{numbers.format(counts.evaluated_observations)}</dd></div>
      <div><dt>{copy.excluded}</dt><dd>{numbers.format(counts.excluded_observations)}</dd></div>
    </dl>
    <Exclusions exclusions={result.exclusions} copy={copy} numbers={numbers} />
    <div className="decision-study-groups">
      {result.scenarios.map(scenario => <section key={scenario.kind}>
        <h3>{copy.kinds[scenario.kind]}</h3>
        <dl>
          <Cohort title={copy.triggered} total={scenario.triggered} statistics={scenario.events}
            showStress={scenario.kind !== 'support_failure'} copy={copy} numbers={numbers} percent={percent} />
          <Cohort title={copy.comparison} total={scenario.untriggered} statistics={scenario.comparison}
            showStress={scenario.kind !== 'support_failure'} copy={copy} numbers={numbers} percent={percent} />
        </dl>
        {scenario.kind === 'support_failure' && scenario.events.count > 0 && <p>{copy.support}</p>}
        <Exclusions exclusions={scenario.excluded} copy={copy} numbers={numbers} />
      </section>)}
    </div>
    <div className="decision-study-method">
      <p>{copy.reference(numbers.format(result.holding_sessions))}</p>
      <p>{copy.cost(numbers.format(assumptions.price_tick), numbers.format(assumptions.slippage_bps),
        numbers.format(assumptions.round_trip_cost_bps))}</p>
      <p>{copy.limits}</p>
    </div>
  </div>
}

type StudyLoad = { endpoint: string } & (
  { status: 'loading' } | { status: 'ready'; result: StudyResult } | { status: 'failed'; detail: string }
)

export default function DecisionStudy({ endpoint }: { endpoint: string }) {
  const locale = useLocale()
  const copy = copies[locale]
  const [load, setLoad] = useState<StudyLoad | null>(null)
  const controller = useRef<AbortController | null>(null)
  const current = load?.endpoint === endpoint ? load : null

  useEffect(() => () => controller.current?.abort(), [endpoint])

  async function run() {
    if (controller.current && !controller.current.signal.aborted) return
    const task = new AbortController()
    controller.current = task
    setLoad({ endpoint, status: 'loading' })
    try {
      const result = await request<StudyResult>(endpoint, { signal: task.signal, timeoutMs: 60_000 })
      if (!task.signal.aborted) setLoad({ endpoint, status: 'ready', result })
    } catch (error) {
      if (!task.signal.aborted) setLoad({ endpoint, status: 'failed', detail: error instanceof Error ? error.message : '' })
    } finally {
      if (controller.current === task) controller.current = null
    }
  }

  return <details className="decision-study">
    <summary>{copy.title}</summary>
    <p>{copy.intro}</p>
    {current?.status === 'ready' ? <StudyReport result={current.result} copy={copy} locale={locale === 'zh' ? 'zh-CN' : 'en-US'} /> : <>
      {current?.status === 'failed' && <p className="decision-study-error" role="alert">
        {copy.failure} {current.detail ? t(current.detail) : ''}
      </p>}
      <button type="button" className="secondary" onClick={() => void run()} disabled={current?.status === 'loading'}>
        {current?.status === 'failed' ? copy.retry : copy.run}
      </button>
      {current?.status === 'loading' && <p role="status">{copy.busy}</p>}
    </>}
  </details>
}
