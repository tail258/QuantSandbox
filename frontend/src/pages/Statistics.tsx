import { useEffect, useRef, useState } from 'react'
import { FlaskConical, Download, SlidersHorizontal } from 'lucide-react'
import type { PageProps } from '../App'
import { api, pct, fmt, today, type Row } from '../api'
import { post } from '../http'
import { Panel, Note, Metric, Chart, Empty, Source, LoadingButton } from '../components'
import { useProject } from '../workspace/ProjectContext'
import Dialog from '../workspace/Dialog'
const defaults = {
  x: '',
  y: '',
  start: '2023-01-01',
  end: today,
  frequency: 'D',
  transform: 'returns',
  lag: 0,
  horizon: 5,
  threshold: 0,
  operator: 'gt',
  nonoverlap: true,
}
export default function Statistics({ status }: PageProps) {
  const { activeProject, reloadProjects } = useProject()
  const available: Row[] = status.series
  const [params, setParams] = useState<Row>(defaults)
  const [result, setResult] = useState<Row | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [settings, setSettings] = useState(false)
  const scope = useRef(0)
  const initialized = useRef<string | null>(null)
  const projectKey = activeProject?.id || 'independent'
  useEffect(() => {
    const changed = initialized.current !== projectKey
    if (!available.length) return
    if (
      !changed &&
      params.x &&
      params.y &&
      available.some((s) => s.id === params.x) &&
      available.some((s) => s.id === params.y)
    )
      return
    initialized.current = projectKey
    const preferred = available.filter((s) => activeProject?.symbols.includes(s.symbol))
    const choices = preferred.length ? preferred : available
    const x = choices.find((s) => s.id.endsWith(':close')) || choices[0]
    const y =
      choices.find((s) => s.symbol !== x.symbol && s.id.endsWith(':close')) ||
      choices.find((s) => s.id !== x.id) ||
      available.find((s) => s.id !== x.id)
    setParams({
      ...defaults,
      x: x.id,
      y: y?.id || '',
      start: [x.start, y?.start].filter(Boolean).sort().at(-1) || defaults.start,
      end: [x.end, y?.end].filter(Boolean).sort()[0] || today,
    })
  }, [projectKey, available.map((s) => s.id).join(',')])
  useEffect(() => {
    const ticket = ++scope.current
    setResult(null)
    setMsg('')
    let live = true
    api<Row[]>('/runs')
      .then((records) => {
        if (!live || scope.current !== ticket) return
        const matches = records.filter(
          (r) =>
            r.kind === 'statistics' &&
            (!activeProject ||
              activeProject.links.some((link) => link.kind === 'research' && link.run_id === r.id)),
        )
        if (matches[0]) {
          setResult(matches[0])
          setParams(matches[0].params)
          initialized.current = projectKey
        }
      })
      .catch((e) => {
        if (live) setMsg(e.message)
      })
    return () => {
      live = false
      scope.current++
    }
  }, [projectKey])
  const change = (key: string, value: unknown) => setParams((old) => ({ ...old, [key]: value }))
  async function run() {
    const ticket = ++scope.current,
      projectId = activeProject?.id
    setBusy(true)
    setMsg('')
    try {
      const next = await api('/analyze', params)
      if (projectId) {
        await post('/projects/' + projectId + '/links', { kind: 'research', run_id: next.id })
        await reloadProjects()
      }
      if (scope.current !== ticket) return
      setResult(next)
      setSettings(false)
      setMsg('计算已保存' + (projectId ? '并关联当前项目。' : '。'))
    } catch (e: any) {
      if (scope.current === ticket) setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }
  const r = result?.result,
    conditional = r?.conditional
  const pending = result && JSON.stringify(params) !== JSON.stringify(result.params)
  const optionSeries = [
    ...available,
    ...(result?.sources || []).filter(
      (source: Row) => source.id && !available.some((item) => item.id === source.id),
    ),
  ]
  const xName = optionSeries.find((s) => s.id === params.x)?.name || '选择 X'
  const yName = optionSeries.find((s) => s.id === params.y)?.name || '选择 Y'
  const parameters = (
    <>
      <div className="controls wrap">
        <label className="wide">
          解释变量 X
          <select
            aria-label="解释变量 X"
            value={params.x}
            onChange={(e) => change('x', e.target.value)}
          >
            <option value="">选择序列</option>
            {optionSeries.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="wide">
          观察变量 Y
          <select
            aria-label="观察变量 Y"
            value={params.y}
            onChange={(e) => change('y', e.target.value)}
          >
            <option value="">选择序列</option>
            {optionSeries.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="controls wrap">
        <label>
          开始日期
          <input
            type="date"
            value={params.start}
            onInput={(e) => change('start', e.currentTarget.value)}
            onChange={(e) => change('start', e.target.value)}
          />
        </label>
        <label>
          结束日期
          <input
            type="date"
            value={params.end}
            onInput={(e) => change('end', e.currentTarget.value)}
            onChange={(e) => change('end', e.target.value)}
          />
        </label>
        <label>
          取样频率
          <select value={params.frequency} onChange={(e) => change('frequency', e.target.value)}>
            <option value="D">日 / 共同观测</option>
            <option value="W">周末值（周五）</option>
            <option value="M">月末值</option>
          </select>
        </label>
        <label>
          相关性变换
          <select value={params.transform} onChange={(e) => change('transform', e.target.value)}>
            <option value="returns">变化率</option>
            <option value="diff">一阶差分</option>
            <option value="level">原始水平</option>
          </select>
        </label>
      </div>
      <div className="controls wrap">
        <label>
          X 领先 Y 的期数
          <input
            type="number"
            min={-120}
            max={120}
            value={params.lag}
            onChange={(e) => change('lag', Number(e.target.value))}
          />
        </label>
        <label>
          条件后观察期数
          <input
            type="number"
            min={1}
            max={120}
            value={params.horizon}
            onChange={(e) => change('horizon', Number(e.target.value))}
          />
        </label>
        <label>
          X 的触发条件
          <select value={params.operator} onChange={(e) => change('operator', e.target.value)}>
            <option value="gt">大于阈值</option>
            <option value="lt">小于阈值</option>
          </select>
        </label>
        <label>
          阈值（变化率 0.01=1%）
          <input
            type="number"
            step="0.01"
            value={params.threshold}
            onChange={(e) => change('threshold', Number(e.target.value))}
          />
        </label>
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={params.nonoverlap}
          onChange={(e) => change('nonoverlap', e.target.checked)}
        />
        排除重叠窗口（固定步长取样）
      </label>
    </>
  )
  return (
    <>
      <div className="page-title">
        <div>
          <h1>统计实验</h1>
          <p>把直觉写成条件，保留样本、基准与区间。</p>
        </div>
        {r && (
          <LoadingButton busy={busy} disabled={!params.x || !params.y} onClick={run}>
            计算并保存
          </LoadingButton>
        )}
      </div>
      <div className="research-object-bar">
        <div className="object-identity">
          <strong>
            {xName} <span className="muted">×</span> {yName}
          </strong>
          <small>
            {params.start} 至 {params.end} ·{' '}
            {({ D: '日 / 共同观测', W: '周频', M: '月频' } as Row)[params.frequency]} · X 领先{' '}
            {params.lag} 期
          </small>
        </div>
        {r && (
          <button className="secondary" onClick={() => setSettings(true)}>
            <SlidersHorizontal size={15} />
            调整实验条件
          </button>
        )}
      </div>
      {msg && <Note>{msg}</Note>}
      {pending && <Note>条件已调整；下方仍显示上次保存结果，点击“计算并保存”应用新条件。</Note>}
      {r ? (
        <>
          <div className="research-method-strip">
            <span>
              结果区间 {result!.params.start} 至 {result!.params.end}
            </span>
            <span>
              变换{' '}
              {
                ({ returns: '变化率', diff: '一阶差分', level: '原始水平' } as Row)[
                  result!.params.transform
                ]
              }
            </span>
            <span>按可用日期对齐 · 缺失不前填</span>
          </div>
          <div className="metrics">
            <Metric
              label="Pearson 相关系数"
              value={fmt(r.correlation, 3)}
              sub={`配对样本 n = ${r.n}`}
            />
            <Metric
              label="条件后上涨概率"
              value={pct(conditional?.probability)}
              sub={`命中 ${conditional?.up ?? '—'} / 条件样本 ${conditional?.n ?? '—'}`}
            />
            <Metric
              label="无条件上涨概率"
              value={pct(conditional?.baseline)}
              sub={`同口径基准 n = ${conditional?.baseline_n ?? '—'}`}
            />
            <Metric
              label="95% 区间"
              value={
                conditional?.interval
                  ? `${pct(conditional.interval[0])} – ${pct(conditional.interval[1])}`
                  : '—'
              }
              sub="Wilson 区间；非因果结论"
            />
          </div>
          {conditional && conditional.n < 30 && (
            <Note tone="warn">
              条件样本不足 30，概率区间较不稳定。反复筛选参数会增加偶然发现，请保留独立区间验证。
            </Note>
          )}
          {result!.params.transform === 'level' && (
            <Note tone="warn">原始水平相关可能来自共同趋势，建议同时比较变化率或差分。</Note>
          )}
          <Panel
            title="对齐后的变量"
            action={
              <a className="button secondary" href={'/api/research/export/' + result!.id}>
                <Download size={14} />
                导出结果
              </a>
            }
          >
            <Chart
              rows={r.points}
              lines={[
                { key: 'x', name: 'X 变换值' },
                { key: 'y', name: 'Y 变换值（已位移）' },
              ]}
              unit="两序列同轴；单位不同请分别解读"
            />
            <p className="muted">{r.method}</p>
          </Panel>
          <details className="workspace-details">
            <summary>本次结果的参数与输入</summary>
            <pre>{JSON.stringify(result!.params, null, 2)}</pre>
            <code>记录 {result!.id}</code>
          </details>
          {result!.sources.map((source: Row, i: number) => (
            <Source key={i} s={source} />
          ))}
        </>
      ) : (
        <Panel title="设置第一个实验">
          <p className="muted">优先展示当前项目的序列。可以自由更换品种、区间与领先滞后条件。</p>
          {parameters}
          <div className="actions">
            <LoadingButton busy={busy} disabled={!params.x || !params.y} onClick={run}>
              计算并保存
            </LoadingButton>
          </div>
        </Panel>
      )}
      <details className="workspace-details">
        <summary>
          <FlaskConical size={14} />
          领先滞后与条件概率口径
        </summary>
        <p>
          正值表示 X(t) 对 Y(t+滞后)；“期”为对齐后的共同观测，不一定是自然日。条件概率观察此后 Y
          的变化率，负滞后只报告相关性。按可用日期对齐，不向前填充缺失。
        </p>
      </details>
      {settings && (
        <Dialog title="调整实验条件" onClose={() => setSettings(false)}>
          {parameters}
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setSettings(false)}>
              保留条件并关闭
            </button>
            <LoadingButton busy={busy} disabled={!params.x || !params.y} onClick={run}>
              计算并保存
            </LoadingButton>
          </div>
        </Dialog>
      )}
    </>
  )
}
