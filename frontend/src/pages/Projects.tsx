import { t, useLocale } from '../i18n'
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
  useLocale()
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
                  {record?.title || record?.name || (loading ? t('正在读取记录') : t('已保存记录'))}
                </strong>
                <small>
                  {link.linked_at.slice(0, 16).replace('T', ' ')} UTC
                  {record?.status
                    ? ' · ' +
                      (
                        {
                          completed: t('已完成'),
                          queued: t('排队中'),
                          running: t('计算中'),
                          failed: t('失败'),
                          cancelled: t('已取消'),
                        } as Row
                      )[record.status]
                    : ''}
                </small>
              </div>
              <button className="secondary" onClick={() => openRecord(link)}>
                {t('查看')} <ArrowRight size={13} />
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
          <h1>{t('研究项目')}</h1>
          <p>{t('选择一个问题，继续观察、验证和归档。')}</p>
        </div>
        <button
          className={activeProject ? 'secondary' : undefined}
          onClick={() => setShowCreate(true)}
        >
          <FolderPlus size={16} />
          {t('新建项目')}{' '}
        </button>
      </div>
      {error && <Note tone="warn">{t(error)}</Note>}
      {message && <Note>{t(message)}</Note>}
      <div className="project-workspace">
        <section className="project-directory" aria-label={t('项目目录')}>
          <div className="project-directory-head">
            <strong>
              {t('项目档案')} <small>{projects.length}</small>
            </strong>
            <button
              className="text-button"
              aria-label={t('刷新项目')}
              disabled={busy}
              onClick={() => action(reloadProjects)}
            >
              <RefreshCw size={15} />
            </button>
          </div>
          <input
            aria-label={t('搜索项目')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('名称或证券代码')}
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
                <small>{project.symbols.join(' · ') || t('未关联证券')}</small>
                <span>
                  {t('{count} 条记录', { count: project.links.length })} ·{' '}
                  {project.updated_at.slice(5, 10)}
                </span>
              </button>
            ))}
          </div>
          {!projects.length && !loading && (
            <p className="muted">{t('创建项目，保存你的第一个研究问题。')}</p>
          )}
          {projects.length > 0 && !visibleProjects.length && (
            <p className="muted">{t('没有匹配的项目。')}</p>
          )}
        </section>
        <section className="project-detail" aria-label={t('当前项目详情')}>
          {activeProject ? (
            <>
              <div className="project-detail-heading">
                <div>
                  <span className="eyebrow">{t('当前研究')}</span>
                  <h2>{activeProject.name}</h2>
                  <p>{activeProject.question || t('尚未填写研究问题。')}</p>
                  <div className="project-summary">
                    <span>{activeProject.symbols.join(' · ') || t('未关联证券')}</span>
                    <span>{t('{count} 条研究证据', { count: researchLinks.length })}</span>
                    <span>{t('{count} 项策略实验', { count: experimentLinks.length })}</span>
                  </div>
                </div>
                <button onClick={continueResearch}>
                  {t('继续研究')} <ArrowRight size={15} />
                </button>
              </div>
              <div className="tabs project-detail-tabs" role="tablist" aria-label={t('项目内容')}>
                {tabs.map(([id, label]) => (
                  <button
                    role="tab"
                    aria-selected={tab === id}
                    className={tab === id ? 'selected' : ''}
                    onClick={() => setTab(id)}
                    key={id}
                  >
                    {t(label)}
                  </button>
                ))}
              </div>
              {tab === 'overview' && (
                <>
                  <Panel title={t('研究路径')}>
                    <div className="project-next-actions">
                      <button className="secondary" onClick={() => setPage('finance')}>
                        <strong>{t('公司与财务')}</strong>
                        <small>{t('沿用公司模板与同行')}</small>
                        <ArrowRight size={15} />
                      </button>
                      <button className="secondary" onClick={() => setPage('stats')}>
                        <strong>{t('统计检验')}</strong>
                        <small>{t('对照变量与历史区间')}</small>
                        <ArrowRight size={15} />
                      </button>
                      <button className="secondary" onClick={() => setPage('simulation')}>
                        <strong>{t('策略验证')}</strong>
                        <small>{t('固定行情，创建对照')}</small>
                        <ArrowRight size={15} />
                      </button>
                    </div>
                  </Panel>
                  <Panel title={t('最近关联')}>
                    {recordList(
                      recent.slice(0, 4),
                      t('还没有关联记录。完成分析后会自动加入当前项目，也可在研究证据中手动关联。'),
                    )}
                  </Panel>
                  <Panel
                    title={t('关联证券的数据覆盖')}
                    action={
                      <button className="text-button" onClick={() => setPage('data')}>
                        {t('打开数据中心')} <ArrowRight size={13} />
                      </button>
                    }
                  >
                    {status.loadFailed ? (
                      <p className="muted">{t('暂无法读取数据覆盖，请重试数据服务。')}</p>
                    ) : status.loading ? (
                      <p className="muted">{t('正在读取数据覆盖…')}</p>
                    ) : chosenDatasets.length ? (
                      <div className="coverage-list">
                        {chosenDatasets.map((s: Row) => (
                          <div key={s.id}>
                            <strong>{s.name || s.symbol}</strong>
                            <span>
                              {(
                                {
                                  quotes: t('股票行情'),
                                  finance: t('财务报表'),
                                  holders: t('股东户数'),
                                  announcements: t('公告'),
                                  verification: t('交叉核验'),
                                  closing_snapshot: t('盘后快照'),
                                } as Row
                              )[s.kind] || t('其他研究数据')}
                            </span>
                            <small>
                              {s.start || '—'} {t('至')} {s.end || '—'} · {s.source}
                            </small>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="muted">
                        {t('当前证券没有匹配的本地缓存。可前往数据中心手动获取或导入。')}{' '}
                      </p>
                    )}
                  </Panel>
                  {activeProject.conclusion && (
                    <Panel title={t('已保存结论')}>
                      <p className="project-conclusion-text">{activeProject.conclusion}</p>
                      <button className="text-button" onClick={() => setTab('conclusion')}>
                        {t('继续编辑')}{' '}
                      </button>
                    </Panel>
                  )}
                </>
              )}
              {(tab === 'evidence' || tab === 'experiments') && (
                <>
                  <Panel
                    title={tab === 'evidence' ? t('研究证据') : t('策略实验')}
                    action={
                      <button
                        className="secondary"
                        onClick={() => setPage(tab === 'evidence' ? 'finance' : 'simulation')}
                      >
                        {tab === 'evidence' ? t('开始新的研究') : t('开始新的实验')}
                      </button>
                    }
                  >
                    {recordList(
                      tab === 'evidence' ? researchLinks : experimentLinks,
                      t('该项目暂无此类记录。'),
                    )}
                  </Panel>
                  <details className="workspace-details">
                    <summary>{t('关联已有记录')}</summary>
                    <div className="controls wrap">
                      <label>
                        {t('记录类型')}{' '}
                        <select
                          value={kind}
                          onChange={(e) => {
                            setKind(e.target.value as ProjectLink['kind'])
                            setRunId('')
                          }}
                        >
                          <option value="research">{t('研究分析')}</option>
                          <option value="simulation">{t('策略实验')}</option>
                        </select>
                      </label>
                      <label className="grow">
                        {t('已保存记录')}{' '}
                        <select value={runId} onChange={(e) => setRunId(e.target.value)}>
                          <option value="">{t('选择记录')}</option>
                          {choices.map((r) => (
                            <option value={r.id} key={r.id}>
                              {r.title || r.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <LoadingButton busy={busy} disabled={!runId} onClick={link}>
                        <Link2 size={14} />
                        {t('关联')}{' '}
                      </LoadingButton>
                    </div>
                  </details>
                </>
              )}
              {tab === 'conclusion' && (
                <Panel
                  title={t('项目结论')}
                  action={
                    <LoadingButton busy={busy} onClick={saveConclusion}>
                      <Save size={14} />
                      {t('保存结论')}{' '}
                    </LoadingButton>
                  }
                >
                  <label>
                    {t('判断、反例与后续观察')}{' '}
                    <textarea
                      className="project-conclusion-editor"
                      aria-label={t('项目结论')}
                      value={conclusion}
                      onChange={(e) => setConclusion(e.target.value)}
                      placeholder={t(
                        '记录当前判断、证据、尚未解决的问题，以及什么变化会改变结论。',
                      )}
                    />
                  </label>
                  <p className="muted">{t('保存在当前研究项目中；需要笔记时再选择导出。')}</p>
                  <button className="secondary" onClick={() => setPage('obsidian')}>
                    {t('整理为笔记')} <ArrowRight size={13} />
                  </button>
                </Panel>
              )}
              <details className="workspace-details technical-details">
                <summary>{t('项目记录信息')}</summary>
                <p>
                  {t('创建')} {activeProject.created_at.slice(0, 16).replace('T', ' ')}{' '}
                  {t('UTC · 更新')} {activeProject.updated_at.slice(0, 16).replace('T', ' ')} UTC
                </p>
                <code>{activeProject.id}</code>
              </details>
            </>
          ) : (
            <Panel title={t('选择一个研究项目')}>
              <Empty>
                {t('从左侧选择项目，或新建一个研究问题。')}{' '}
                <button onClick={() => setShowCreate(true)}>{t('新建项目')}</button>
              </Empty>
            </Panel>
          )}
        </section>
      </div>
      {showCreate && (
        <Dialog title={t('新建研究项目')} onClose={() => setShowCreate(false)}>
          <form onSubmit={create}>
            <label>
              {t('项目名称')}{' '}
              <input
                autoFocus
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('例如：橡胶周期与公司盈利')}
              />
            </label>
            <label>
              {t('研究问题')}{' '}
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={t('希望验证什么，怎样的结果会改变你的判断？')}
              />
            </label>
            <label>
              {t('关联证券')}{' '}
              <input
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
                placeholder={t('六位证券代码，逗号分隔')}
              />
            </label>
            <div className="dialog-actions">
              <button type="button" className="secondary" onClick={() => setShowCreate(false)}>
                {t('取消')}{' '}
              </button>
              <LoadingButton busy={busy} type="submit">
                {t('创建项目')}{' '}
              </LoadingButton>
            </div>
          </form>
        </Dialog>
      )}
    </>
  )
}
