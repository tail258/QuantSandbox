import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  ArrowRight,
  FolderPlus,
  Link2,
  RefreshCw,
  Save,
  FileText,
  FlaskConical,
} from 'lucide-react'
import type { PageProps } from '../App'
import { api, type Row } from '../api'
import { request, post } from '../http'
import { Panel, Note, Empty, LoadingButton } from '../components'
import { useProject, type Project, type ProjectLink } from '../workspace/ProjectContext'
import Dialog from '../workspace/Dialog'
const tabs = [
  ['overview', '概览'],
  ['evidence', '研究证据'],
  ['experiments', '策略实验'],
  ['conclusion', '结论'],
] as const

export default function Projects({ setPage, status }: PageProps) {
  const { projects, activeProject, selectProject, reloadProjects, linkRecord } = useProject()
  const [records, setRecords] = useState<Row[]>([])
  const [simulations, setSimulations] = useState<Row[]>([])
  const [tab, setTab] = useState('overview')
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [question, setQuestion] = useState('')
  const [symbols, setSymbols] = useState('')
  const [conclusion, setConclusion] = useState('')
  const [kind, setKind] = useState<ProjectLink['kind']>('research')
  const [runId, setRunId] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [search, setSearch] = useState('')
  useEffect(() => {
    let live = true
    Promise.all([api<Row[]>('/runs'), request<{ runs: Row[] }>('/runs')])
      .then(([r, s]) => {
        if (live) {
          setRecords(r)
          setSimulations(s.runs)
        }
      })
      .catch((e) => {
        if (live) setError(e.message)
      })
      .finally(() => {
        if (live) setLoading(false)
      })
    return () => {
      live = false
    }
  }, [])
  useEffect(() => {
    setTab('overview')
    setConclusion(activeProject?.conclusion || '')
    setMessage('')
    setRunId('')
  }, [activeProject?.id])
  useEffect(() => {
    setConclusion(activeProject?.conclusion || '')
  }, [activeProject?.conclusion])
  const links = activeProject?.links || []
  const researchLinks = links.filter((l) => l.kind === 'research')
  const experimentLinks = links.filter((l) => l.kind === 'simulation')
  const recent = [...links].sort((a, b) => b.linked_at.localeCompare(a.linked_at))
  const chosenDatasets = useMemo(
    () => status.datasets.filter((s: Row) => activeProject?.symbols.includes(s.symbol)),
    [status.datasets, activeProject?.symbols],
  )
  const choices = (kind === 'research' ? records : simulations).filter(
    (r) => !links.some((l) => l.kind === kind && l.run_id === r.id),
  )
  const visibleProjects = projects.filter((p) =>
    (p.name + ' ' + p.symbols.join(' ')).toLowerCase().includes(search.toLowerCase()),
  )
  const findRecord = (link: ProjectLink) =>
    (link.kind === 'research' ? records : simulations).find((r) => r.id === link.run_id)
  const openRecord = (link: ProjectLink) =>
    setPage((link.kind === 'research' ? 'runs' : 'simulation') + '?run=' + link.run_id)
  async function action(fn: () => Promise<void>) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await fn()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function create(e: FormEvent) {
    e.preventDefault()
    await action(async () => {
      const project = await post<Project>('/projects', {
        name,
        question,
        symbols: symbols.split(/[,，\s]+/).filter(Boolean),
      })
      await reloadProjects()
      await selectProject(project.id)
      setShowCreate(false)
      setName('')
      setQuestion('')
      setSymbols('')
    })
  }
  async function saveConclusion() {
    if (!activeProject) return
    await action(async () => {
      await request('/projects/' + activeProject.id, {
        method: 'PATCH',
        body: JSON.stringify({ conclusion }),
      })
      await reloadProjects()
      setMessage('项目结论已保存。')
    })
  }
  async function link() {
    if (!runId) return
    await action(async () => {
      await linkRecord(kind, runId)
      setRunId('')
      setMessage('记录已关联到当前项目。')
    })
  }
  const continueResearch = () => {
    if (recent[0]) openRecord(recent[0])
    else setPage(activeProject?.symbols.length ? 'finance' : 'stats')
  }
  const recordList = (items: ProjectLink[], empty: string) =>
    items.length ? (
      <div className="project-record-list">
        {[...items].reverse().map((link) => {
          const record = findRecord(link)
          return (
            <article key={link.kind + link.run_id}>
              <div>
                <span className="record-kind">
                  {link.kind === 'research' ? <FileText size={15} /> : <FlaskConical size={15} />}
                </span>
                <strong>
                  {record?.title || record?.name || (loading ? '正在读取记录' : '已保存记录')}
                </strong>
                <small>
                  {link.linked_at.slice(0, 16).replace('T', ' ')} UTC
                  {record?.status
                    ? ' · ' +
                      (
                        {
                          completed: '已完成',
                          queued: '排队中',
                          running: '计算中',
                          failed: '失败',
                          cancelled: '已取消',
                        } as Row
                      )[record.status]
                    : ''}
                </small>
              </div>
              <button className="secondary" onClick={() => openRecord(link)}>
                查看
                <ArrowRight size={13} />
              </button>
            </article>
          )
        })}
      </div>
    ) : (
      <Empty>{empty}</Empty>
    )
  return (
    <>
      <div className="page-title">
        <div>
          <h1>研究项目</h1>
          <p>选择一个问题，继续观察、验证和归档。</p>
        </div>
        <button
          className={activeProject ? 'secondary' : undefined}
          onClick={() => setShowCreate(true)}
        >
          <FolderPlus size={16} />
          新建项目
        </button>
      </div>
      {error && <Note tone="warn">{error}</Note>}
      {message && <Note>{message}</Note>}
      <div className="project-workspace">
        <section className="project-directory" aria-label="项目目录">
          <div className="project-directory-head">
            <strong>
              项目档案 <small>{projects.length}</small>
            </strong>
            <button
              className="text-button"
              aria-label="刷新项目"
              disabled={busy}
              onClick={() => action(reloadProjects)}
            >
              <RefreshCw size={15} />
            </button>
          </div>
          <input
            aria-label="搜索项目"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="名称或证券代码"
          />
          <div className="project-list">
            {visibleProjects.map((project) => (
              <button
                className={'project-card ' + (activeProject?.id === project.id ? 'selected' : '')}
                aria-pressed={activeProject?.id === project.id}
                key={project.id}
                onClick={() => selectProject(project.id).catch((e) => setError(e.message))}
              >
                <strong>{project.name}</strong>
                <small>{project.symbols.join(' · ') || '未关联证券'}</small>
                <span>
                  {project.links.length} 条记录 · {project.updated_at.slice(5, 10)}
                </span>
              </button>
            ))}
          </div>
          {!projects.length && !loading && (
            <p className="muted">创建项目，保存你的第一个研究问题。</p>
          )}
          {projects.length > 0 && !visibleProjects.length && (
            <p className="muted">没有匹配的项目。</p>
          )}
        </section>
        <section className="project-detail" aria-label="当前项目详情">
          {activeProject ? (
            <>
              <div className="project-detail-heading">
                <div>
                  <span className="eyebrow">当前研究</span>
                  <h2>{activeProject.name}</h2>
                  <p>{activeProject.question || '尚未填写研究问题。'}</p>
                  <div className="project-summary">
                    <span>{activeProject.symbols.join(' · ') || '未关联证券'}</span>
                    <span>{researchLinks.length} 条研究证据</span>
                    <span>{experimentLinks.length} 项策略实验</span>
                  </div>
                </div>
                <button onClick={continueResearch}>
                  继续研究
                  <ArrowRight size={15} />
                </button>
              </div>
              <div className="tabs project-detail-tabs" role="tablist" aria-label="项目内容">
                {tabs.map(([id, label]) => (
                  <button
                    role="tab"
                    aria-selected={tab === id}
                    className={tab === id ? 'selected' : ''}
                    onClick={() => setTab(id)}
                    key={id}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {tab === 'overview' && (
                <>
                  <Panel title="研究路径">
                    <div className="project-next-actions">
                      <button className="secondary" onClick={() => setPage('finance')}>
                        <strong>公司与财务</strong>
                        <small>沿用公司模板与同行</small>
                        <ArrowRight size={15} />
                      </button>
                      <button className="secondary" onClick={() => setPage('stats')}>
                        <strong>统计检验</strong>
                        <small>对照变量与历史区间</small>
                        <ArrowRight size={15} />
                      </button>
                      <button className="secondary" onClick={() => setPage('simulation')}>
                        <strong>策略验证</strong>
                        <small>固定行情，创建对照</small>
                        <ArrowRight size={15} />
                      </button>
                    </div>
                  </Panel>
                  <Panel title="最近关联">
                    {recordList(
                      recent.slice(0, 4),
                      '还没有关联记录。完成分析后会自动加入当前项目，也可在研究证据中手动关联。',
                    )}
                  </Panel>
                  <Panel
                    title="关联证券的数据覆盖"
                    action={
                      <button className="text-button" onClick={() => setPage('data')}>
                        打开数据中心
                        <ArrowRight size={13} />
                      </button>
                    }
                  >
                    {status.loadFailed ? (
                      <p className="muted">暂无法读取数据覆盖，请重试数据服务。</p>
                    ) : status.loading ? (
                      <p className="muted">正在读取数据覆盖…</p>
                    ) : chosenDatasets.length ? (
                      <div className="coverage-list">
                        {chosenDatasets.map((s: Row) => (
                          <div key={s.id}>
                            <strong>{s.name || s.symbol}</strong>
                            <span>
                              {(
                                {
                                  quotes: '股票行情',
                                  finance: '财务报表',
                                  holders: '股东户数',
                                  announcements: '公告',
                                  verification: '交叉核验',
                                  closing_snapshot: '盘后快照',
                                } as Row
                              )[s.kind] || '其他研究数据'}
                            </span>
                            <small>
                              {s.start || '—'} 至 {s.end || '—'} · {s.source}
                            </small>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="muted">
                        当前证券没有匹配的本地缓存。可前往数据中心手动获取或导入。
                      </p>
                    )}
                  </Panel>
                  {activeProject.conclusion && (
                    <Panel title="已保存结论">
                      <p className="project-conclusion-text">{activeProject.conclusion}</p>
                      <button className="text-button" onClick={() => setTab('conclusion')}>
                        继续编辑
                      </button>
                    </Panel>
                  )}
                </>
              )}
              {(tab === 'evidence' || tab === 'experiments') && (
                <>
                  <Panel
                    title={tab === 'evidence' ? '研究证据' : '策略实验'}
                    action={
                      <button
                        className="secondary"
                        onClick={() => setPage(tab === 'evidence' ? 'finance' : 'simulation')}
                      >
                        开始新的{tab === 'evidence' ? '研究' : '实验'}
                      </button>
                    }
                  >
                    {recordList(
                      tab === 'evidence' ? researchLinks : experimentLinks,
                      '该项目暂无此类记录。',
                    )}
                  </Panel>
                  <details className="workspace-details">
                    <summary>关联已有记录</summary>
                    <div className="controls wrap">
                      <label>
                        记录类型
                        <select
                          value={kind}
                          onChange={(e) => {
                            setKind(e.target.value as ProjectLink['kind'])
                            setRunId('')
                          }}
                        >
                          <option value="research">研究分析</option>
                          <option value="simulation">策略实验</option>
                        </select>
                      </label>
                      <label className="grow">
                        已保存记录
                        <select value={runId} onChange={(e) => setRunId(e.target.value)}>
                          <option value="">选择记录</option>
                          {choices.map((r) => (
                            <option value={r.id} key={r.id}>
                              {r.title || r.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <LoadingButton busy={busy} disabled={!runId} onClick={link}>
                        <Link2 size={14} />
                        关联
                      </LoadingButton>
                    </div>
                  </details>
                </>
              )}
              {tab === 'conclusion' && (
                <Panel
                  title="项目结论"
                  action={
                    <LoadingButton busy={busy} onClick={saveConclusion}>
                      <Save size={14} />
                      保存结论
                    </LoadingButton>
                  }
                >
                  <label>
                    判断、反例与后续观察
                    <textarea
                      className="project-conclusion-editor"
                      aria-label="项目结论"
                      value={conclusion}
                      onChange={(e) => setConclusion(e.target.value)}
                      placeholder="记录当前判断、证据、尚未解决的问题，以及什么变化会改变结论。"
                    />
                  </label>
                  <p className="muted">保存在当前研究项目中；需要笔记时再选择导出。</p>
                  <button className="secondary" onClick={() => setPage('obsidian')}>
                    整理为笔记
                    <ArrowRight size={13} />
                  </button>
                </Panel>
              )}
              <details className="workspace-details technical-details">
                <summary>项目记录信息</summary>
                <p>
                  创建 {activeProject.created_at.slice(0, 16).replace('T', ' ')} UTC · 更新{' '}
                  {activeProject.updated_at.slice(0, 16).replace('T', ' ')} UTC
                </p>
                <code>{activeProject.id}</code>
              </details>
            </>
          ) : (
            <Panel title="选择一个研究项目">
              <Empty>
                从左侧选择项目，或新建一个研究问题。
                <button onClick={() => setShowCreate(true)}>新建项目</button>
              </Empty>
            </Panel>
          )}
        </section>
      </div>
      {showCreate && (
        <Dialog title="新建研究项目" onClose={() => setShowCreate(false)}>
          <form onSubmit={create}>
            <label>
              项目名称
              <input
                autoFocus
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：橡胶周期与公司盈利"
              />
            </label>
            <label>
              研究问题
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="希望验证什么，怎样的结果会改变你的判断？"
              />
            </label>
            <label>
              关联证券
              <input
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
                placeholder="六位证券代码，逗号分隔"
              />
            </label>
            <div className="dialog-actions">
              <button type="button" className="secondary" onClick={() => setShowCreate(false)}>
                取消
              </button>
              <LoadingButton busy={busy} type="submit">
                创建项目
              </LoadingButton>
            </div>
          </form>
        </Dialog>
      )}
    </>
  )
}
