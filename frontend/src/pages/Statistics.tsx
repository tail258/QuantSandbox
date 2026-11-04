import { t, useLocale } from '../i18n'
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
  useLocale()
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
      setMsg(projectId ? '计算已保存并关联当前项目。' : '计算已保存。')
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
  const xName = optionSeries.find((s) => s.id === params.x)?.name || t('选择 X')
  const yName = optionSeries.find((s) => s.id === params.y)?.name || t('选择 Y')
  const parameters = (
    <>
      <div className="controls wrap">
        <label className="wide">
          {t('解释变量 X')}{' '}
          <select
            aria-label={t('解释变量 X')}
            value={params.x}
            onChange={(e) => change('x', e.target.value)}
          >
            <option value="">{t('选择序列')}</option>
            {optionSeries.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="wide">
          {t('观察变量 Y')}{' '}
          <select
            aria-label={t('观察变量 Y')}
            value={params.y}
            onChange={(e) => change('y', e.target.value)}
          >
            <option value="">{t('选择序列')}</option>
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
          {t('开始日期')}{' '}
          <input
            type="date"
            value={params.start}
            onInput={(e) => change('start', e.currentTarget.value)}
            onChange={(e) => change('start', e.target.value)}
          />
        </label>
        <label>
          {t('结束日期')}{' '}
          <input
            type="date"
            value={params.end}
            onInput={(e) => change('end', e.currentTarget.value)}
            onChange={(e) => change('end', e.target.value)}
          />
        </label>
        <label>
          {t('取样频率')}{' '}
          <select value={params.frequency} onChange={(e) => change('frequency', e.target.value)}>
            <option value="D">{t('日 / 共同观测')}</option>
            <option value="W">{t('周末值（周五）')}</option>
            <option value="M">{t('月末值')}</option>
          </select>
        </label>
        <label>
          {t('相关性变换')}{' '}
          <select value={params.transform} onChange={(e) => change('transform', e.target.value)}>
            <option value="returns">{t('变化率')}</option>
            <option value="diff">{t('一阶差分')}</option>
            <option value="level">{t('原始水平')}</option>
          </select>
        </label>
      </div>
      <div className="controls wrap">
        <label>
          {t('X 领先 Y 的期数')}{' '}
          <input
            type="number"
            min={-120}
            max={120}
            value={params.lag}
            onChange={(e) => change('lag', Number(e.target.value))}
          />
        </label>
        <label>
          {t('条件后观察期数')}{' '}
          <input
            type="number"
            min={1}
            max={120}
            value={params.horizon}
            onChange={(e) => change('horizon', Number(e.target.value))}
          />
        </label>
        <label>
          {t('X 的触发条件')}{' '}
          <select value={params.operator} onChange={(e) => change('operator', e.target.value)}>
            <option value="gt">{t('大于阈值')}</option>
            <option value="lt">{t('小于阈值')}</option>
          </select>
        </label>
        <label>
          {t('阈值（变化率 0.01=1%）')}{' '}
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
        {t('排除重叠窗口（固定步长取样）')}{' '}
      </label>
    </>
  )
  return (
    <>
      <div className="page-title">
        <div>
          <h1>{t('统计实验')}</h1>
          <p>{t('把直觉写成条件，保留样本、基准与区间。')}</p>
        </div>
        {r && (
          <LoadingButton busy={busy} disabled={!params.x || !params.y} onClick={run}>
            {t('计算并保存')}{' '}
          </LoadingButton>
        )}
      </div>
      <div className="research-object-bar">
        <div className="object-identity">
          <strong>
            {xName} <span className="muted">×</span> {yName}
          </strong>
          <small>
            {t('{start} 至 {end} · {frequency} · X 领先 {lag} 期', {
              start: params.start,
              end: params.end,
              frequency: ({ D: t('日 / 共同观测'), W: t('周频'), M: t('月频') } as Row)[
                params.frequency
              ],
              lag: params.lag,
            })}
          </small>
        </div>
        {r && (
          <button className="secondary" onClick={() => setSettings(true)}>
            <SlidersHorizontal size={15} />
            {t('调整实验条件')}{' '}
          </button>
        )}
      </div>
      {msg && <Note>{t(msg)}</Note>}
      {pending && (
        <Note>{t('条件已调整；下方仍显示上次保存结果，点击“计算并保存”应用新条件。')}</Note>
      )}
      {r ? (
        <>
          <div className="research-method-strip">
            <span>
              {t('结果区间 {start} 至 {end}', {
                start: result!.params.start,
                end: result!.params.end,
              })}
            </span>
            <span>
              {t('变换')}{' '}
              {
                ({ returns: t('变化率'), diff: t('一阶差分'), level: t('原始水平') } as Row)[
                  result!.params.transform
                ]
              }
            </span>
            <span>{t('按可用日期对齐 · 缺失不前填')}</span>
          </div>
          <div className="metrics">
            <Metric
              label={t('Pearson 相关系数')}
              value={fmt(r.correlation, 3)}
              sub={t('配对样本 n = {count}', { count: r.n })}
            />
            <Metric
              label={t('条件后上涨概率')}
              value={pct(conditional?.probability)}
              sub={t('命中 {up} / 条件样本 {count}', {
                up: conditional?.up ?? '—',
                count: conditional?.n ?? '—',
              })}
            />
            <Metric
              label={t('无条件上涨概率')}
              value={pct(conditional?.baseline)}
              sub={t('同口径基准 n = {count}', { count: conditional?.baseline_n ?? '—' })}
            />
            <Metric
              label={t('95% 区间')}
              value={
                conditional?.interval
                  ? `${pct(conditional.interval[0])} – ${pct(conditional.interval[1])}`
                  : '—'
              }
              sub={t('Wilson 区间；非因果结论')}
            />
          </div>
          {conditional && conditional.n < 30 && (
            <Note tone="warn">
              {t(
                '条件样本不足 30，概率区间较不稳定。反复筛选参数会增加偶然发现，请保留独立区间验证。',
              )}{' '}
            </Note>
          )}
          {result!.params.transform === 'level' && (
            <Note tone="warn">{t('原始水平相关可能来自共同趋势，建议同时比较变化率或差分。')}</Note>
          )}
          <Panel
            title={t('对齐后的变量')}
            action={
              <a className="button secondary" href={'/api/research/export/' + result!.id}>
                <Download size={14} />
                {t('导出结果')}{' '}
              </a>
            }
          >
            <Chart
              rows={r.points}
              lines={[
                { key: 'x', name: t('X 变换值') },
                { key: 'y', name: t('Y 变换值（已位移）') },
              ]}
              unit={t('两序列同轴；单位不同请分别解读')}
            />
            <p className="muted">{r.method}</p>
          </Panel>
          <details className="workspace-details">
            <summary>{t('本次结果的参数与输入')}</summary>
            <pre>{JSON.stringify(result!.params, null, 2)}</pre>
            <code>
              {t('记录')} {result!.id}
            </code>
          </details>
          {result!.sources.map((source: Row, i: number) => (
            <Source key={i} s={source} />
          ))}
        </>
      ) : (
        <Panel title={t('设置第一个实验')}>
          <p className="muted">
            {t('优先展示当前项目的序列。可以自由更换品种、区间与领先滞后条件。')}
          </p>
          {parameters}
          <div className="actions">
            <LoadingButton busy={busy} disabled={!params.x || !params.y} onClick={run}>
              {t('计算并保存')}{' '}
            </LoadingButton>
          </div>
        </Panel>
      )}
      <details className="workspace-details">
        <summary>
          <FlaskConical size={14} />
          {t('领先滞后与条件概率口径')}{' '}
        </summary>
        <p>
          {t(
            '正值表示 X(t) 对 Y(t+滞后)；“期”为对齐后的共同观测，不一定是自然日。条件概率观察此后 Y 的变化率，负滞后只报告相关性。按可用日期对齐，不向前填充缺失。',
          )}{' '}
        </p>
      </details>
      {settings && (
        <Dialog title={t('调整实验条件')} onClose={() => setSettings(false)}>
          {parameters}
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setSettings(false)}>
              {t('保留条件并关闭')}{' '}
            </button>
            <LoadingButton busy={busy} disabled={!params.x || !params.y} onClick={run}>
              {t('计算并保存')}{' '}
            </LoadingButton>
          </div>
        </Dialog>
      )}
    </>
  )
}
