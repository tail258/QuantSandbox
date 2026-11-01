import { useEffect, useState } from 'react'
import { Download, History, Link2 } from 'lucide-react'
import type { PageProps } from '../App'
import { api, fmt, type Row } from '../api'
import { Panel, Note, Empty, RawTable, Source } from '../components'
import { useProject } from '../workspace/ProjectContext'
const names: Row = {
  national: '国家队足迹',
  etf: 'ETF资金',
  statistics: '统计实验',
  finance: '财务比较',
}
export default function Runs({ setPage }: PageProps) {
  const { activeProject, linkRecord } = useProject()
  const [runs, setRuns] = useState<Row[]>([])
  const [selected, setSelected] = useState<Row | null>(null)
  const [msg, setMsg] = useState('')
  const [projectOnly, setProjectOnly] = useState(!!activeProject)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let live = true
    api<Row[]>('/runs')
      .then(async (rows) => {
        if (!live) return
        setRuns(rows)
        const id = new URLSearchParams(location.hash.split('?')[1] || '').get('run')
        if (id) {
          const record = rows.find((r) => r.id === id) || (await api<Row>('/runs/' + id))
          if (live) setSelected(record || null)
        }
      })
      .catch((e) => {
        if (live) setMsg(e.message)
      })
      .finally(() => {
        if (live) setLoading(false)
      })
    return () => {
      live = false
    }
  }, [])
  useEffect(() => {
    setProjectOnly(!!activeProject)
    if (!new URLSearchParams(location.hash.split('?')[1] || '').get('run')) setSelected(null)
  }, [activeProject?.id])
  const linked = (id: string) =>
    activeProject?.links.some((link) => link.kind === 'research' && link.run_id === id)
  const visible = runs.filter((record) => !projectOnly || !activeProject || linked(record.id))
  async function replay() {
    if (!selected) return
    setMsg('')
    try {
      const next =
        selected.kind === 'statistics'
          ? await api('/analyze', selected.params)
          : selected.kind === 'national'
            ? await api('/national/dashboard', { run_id: selected.id, ...selected.params })
            : selected.kind === 'etf'
              ? await api('/etf/dashboard', { run_id: selected.id })
              : null
      if (next) {
        const result = next.run?.result || next.result
        setMsg(
          JSON.stringify(result) === JSON.stringify(selected.result)
            ? '复算一致：原始快照与计算结果完全相同。'
            : '结果有差异，请核对计算版本。',
        )
      } else setMsg('财务归档保留原始结果、公司配置与输入快照；此处不重新获取报表。')
    } catch (e: any) {
      setMsg(e.message)
    }
  }
  return (
    <>
      <div className="page-title">
        <div>
          <h1>分析记录</h1>
          <p>固定输入与参数，回到已有证据继续研究。</p>
        </div>
        <button onClick={() => setPage('stats')}>
          <History size={15} />
          新建统计实验
        </button>
      </div>
      <div className="data-directory-summary">
        <span>{runs.length} 条近期分析记录</span>
        {activeProject && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={projectOnly}
              onChange={(e) => setProjectOnly(e.target.checked)}
            />
            仅当前项目
          </label>
        )}
        <span>导出附 Markdown、CSV、参数与输入快照</span>
      </div>
      {msg && <Note>{msg}</Note>}
      {selected && (
        <Panel
          title={selected.title}
          action={
            <div className="actions">
              <button className="secondary" onClick={replay}>
                复核原结果
              </button>
              <button onClick={() => setPage('obsidian?kind=research&run=' + selected.id)}>
                整理笔记
              </button>
            </div>
          }
        >
          <div className="research-method-strip">
            <span>
              {names[selected.kind]} · {selected.created_at.slice(0, 16).replace('T', ' ')} UTC
            </span>
            <span>计算版本 {selected.version}</span>
          </div>
          {selected.kind === 'statistics' && (
            <p>
              相关系数 {fmt(selected.result.correlation, 4)} · 配对样本 n = {selected.result.n}
            </p>
          )}
          {selected.kind === 'national' && (
            <p>
              研究截至 {selected.result.research_asof} · 份额截至 {selected.result.asof}
            </p>
          )}
          {selected.kind === 'etf' && (
            <p>
              份额截至 {selected.result.asof} · 样本 {selected.result.universe.length} 只
            </p>
          )}
          {activeProject && !linked(selected.id) && (
            <button
              className="text-button"
              onClick={() =>
                linkRecord('research', selected.id)
                  .then(() => setMsg('记录已关联当前项目。'))
                  .catch((e) => setMsg(e.message))
              }
            >
              <Link2 size={14} />
              关联当前项目
            </button>
          )}
          <div className="actions result-table-controls">
            <a className="button secondary" href={'/api/research/export/' + selected.id}>
              <Download size={14} />
              下载分析包
            </a>
            <button className="text-button" onClick={() => setSelected(null)}>
              收起详情
            </button>
          </div>
          <details className="workspace-details">
            <summary>冻结参数与输入快照</summary>
            <pre>{JSON.stringify(selected.params, null, 2)}</pre>
            <p>输入快照</p>
            <code>{selected.inputs.join(' / ')}</code>
            <p>记录 {selected.id}</p>
          </details>
          {['etf', 'national'].includes(selected.kind) && (
            <details className="workspace-details">
              <summary>逐日结果</summary>
              <RawTable rows={selected.result.daily} />
            </details>
          )}
          {selected.kind === 'finance' && (
            <RawTable
              rows={selected.result.flatMap((company: Row) =>
                company.rows.slice(-4).map((row: Row) => ({
                  公司: company.symbol,
                  报告期: row.date,
                  '营业收入（亿元）': row.revenue == null ? '—' : fmt(row.revenue / 1e8, 2),
                  '归母净利润（亿元）': row.profit == null ? '—' : fmt(row.profit / 1e8, 2),
                  '经营现金流（亿元）': row.cashflow == null ? '—' : fmt(row.cashflow / 1e8, 2),
                })),
              )}
            />
          )}
          {selected.sources?.map((source: Row, i: number) => (
            <Source key={i} s={source} />
          ))}
        </Panel>
      )}
      <Panel title="已保存分析">
        {loading ? (
          <Empty>正在读取记录…</Empty>
        ) : visible.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>分析</th>
                  <th>类型</th>
                  <th>保存时间（UTC）</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((record) => (
                  <tr key={record.id}>
                    <td>{record.title}</td>
                    <td>{names[record.kind]}</td>
                    <td>
                      {record.created_at.slice(0, 16).replace('T', ' ')}
                      <small>v{record.version}</small>
                    </td>
                    <td>
                      <button className="text-button" onClick={() => setSelected(record)}>
                        查看记录
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>
            {activeProject && projectOnly
              ? '该项目还没有关联分析，可在研究页面保存，或切换查看全部记录。'
              : '还没有已保存的分析。'}
          </Empty>
        )}
      </Panel>
    </>
  )
}
