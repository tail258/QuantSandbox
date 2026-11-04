import { t, useLocale, setLocale } from './i18n'
import { setTheme, useTheme } from './theme'
import { Component, lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Database,
  ChartNoAxesCombined,
  ChartLine,
  FlaskConical,
  Users,
  Files,
  ShieldCheck,
  Layers3,
  Footprints,
  FolderKanban,
  NotebookPen,
  Play,
  Menu,
  X,
} from 'lucide-react'
import { api, type Row } from './api'
import { Empty, Note } from './components'
import { ProjectProvider, useProject, withProject } from './workspace/ProjectContext'
import './workspace.css'

const pages = {
  projects: lazy(() => import('./pages/Projects')),
  data: lazy(() => import('./pages/DataCenter')),
  finance: lazy(() => import('./pages/Finance')),
  industry: lazy(() => import('./pages/Industry')),
  etf: lazy(() => import('./pages/EtfFlows')),
  national: lazy(() => import('./pages/NationalTeam')),
  stats: lazy(() => import('./pages/Statistics')),
  evidence: lazy(() => import('./pages/Evidence')),
  simulation: lazy(() => import('./pages/Simulation')),
  runs: lazy(() => import('./pages/Runs')),
  obsidian: lazy(() => import('./pages/Obsidian')),
}
const groups = [
  {
    id: 'research',
    label: '研究',
    items: [
      ['projects', '研究项目', FolderKanban],
      ['finance', '公司与财务', ChartNoAxesCombined],
      ['industry', '产业周期', ChartLine],
    ],
  },
  {
    id: 'market',
    label: '市场观察',
    items: [
      ['etf', 'ETF 资金', Layers3],
      ['national', '国家队足迹', Footprints],
      ['evidence', '筹码与情绪', Users],
    ],
  },
  {
    id: 'validation',
    label: '验证',
    items: [
      ['stats', '统计实验', FlaskConical],
      ['simulation', '策略与推演', Play],
    ],
  },
  {
    id: 'archive',
    label: '数据与归档',
    items: [
      ['data', '数据中心', Database],
      ['runs', '分析记录', Files],
      ['obsidian', 'Obsidian', NotebookPen],
    ],
  },
] as const
const route = () => location.hash.slice(1).split('?')[0] || 'projects'
export type PageProps = { status: Row; reload: () => Promise<void>; setPage: (p: string) => void }
class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <Note tone="warn">
        <p>{t('页面加载失败，请重新加载工作台。')}</p>
        <button className="secondary" onClick={() => location.reload()}>
          {t('重新加载')}
        </button>
      </Note>
    ) : (
      this.props.children
    )
  }
}
function Workspace() {
  const locale = useLocale()
  const theme = useTheme()
  const { activeProject, projects, selectProject, error: projectError } = useProject()
  const [page, setPage] = useState(route)
  const [mobileGroup, setMobileGroup] = useState('research')
  const [moreOpen, setMoreOpen] = useState(false)
  const [status, setStatus] = useState<Row>({
    datasets: [],
    series: [],
    templates: {},
    metrics: {},
    events: [],
    loading: true,
  })
  const [error, setError] = useState('')
  const reload = useCallback(async () => {
    try {
      setStatus({ ...(await api('/status')), loading: false, loadFailed: false })
      setError('')
    } catch (error) {
      setStatus((old) => ({ ...old, loading: false, loadFailed: true }))
      throw error
    }
  }, [])
  useEffect(() => {
    let live = true
    reload().catch((e) => {
      if (live) setError(e.message)
    })
    const onhash = () => setPage(route())
    window.addEventListener('hashchange', onhash)
    return () => {
      live = false
      window.removeEventListener('hashchange', onhash)
    }
  }, [reload])
  useEffect(() => {
    window.scrollTo(0, 0)
    const group = groups.find((g) => g.items.some((item) => item[0] === page))
    if (group) setMobileGroup(group.id)
    setMoreOpen(false)
  }, [page])
  const go = useCallback(
    (target: string) => {
      const next = withProject(target, activeProject?.id)
      location.hash = next
      setPage(target.split('?')[0])
      setMoreOpen(false)
    },
    [activeProject?.id],
  )
  const active =
    groups.flatMap((g) => [...g.items]).find((item) => item[0] === page) || groups[0].items[0]
  const activeGroup = groups.find((g) => g.items.some((item) => item[0] === page)) || groups[0]
  const Page = pages[active[0]]
  const mobileItems = groups.find((g) => g.id === mobileGroup)?.items || groups[0].items
  return (
    <div className="shell workspace-shell">
      <aside className="workspace-rail">
        <a className="brand" href={'#' + withProject('projects', activeProject?.id)}>
          QuantSandbox<small>{t('投资研究 · 策略验证')}</small>
        </a>
        <nav className="grouped-navigation" aria-label={t('主导航')}>
          {groups.map((group) => (
            <div className="nav-group" key={group.id}>
              <span className="nav-group-label">{t(group.label)}</span>
              {group.items.map(([id, label, Icon]) => (
                <button
                  key={id}
                  className={page === id ? 'active' : ''}
                  aria-current={page === id ? 'page' : undefined}
                  onClick={() => go(id)}
                >
                  <Icon size={18} />
                  {t(label)}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <ShieldCheck size={16} />
          <div>
            {t('本地研究 · 市场只读')}<small>{t('数据与计算留在你的设备')}</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="workspace-header">
          <div className="workspace-breadcrumb">
            <span>{t(activeGroup.label)}</span>
            <b>/</b>
            <strong>{t(active[1])}</strong>
          </div>
          <label className="header-project-picker">
            <span>{t('当前项目')}</span>
            <select
              aria-label={t('当前研究项目')}
              value={activeProject?.id || ''}
              onChange={(e) => selectProject(e.target.value).catch(() => {})}
            >
              <option value="">{t('独立研究')}</option>
              {projects.map((p) => (
                <option value={p.id} key={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="language-picker theme-picker">
            <span>{t('界面主题')}</span>
            <select aria-label={t('界面主题')} value={theme} onChange={e => setTheme(e.target.value === 'terminal' ? 'terminal' : 'light')}>
              <option value="light">{t('经典浅色')}</option>
              <option value="terminal">{t('金融终端')}</option>
            </select>
          </label>
          <label className="language-picker">
            <span>{t('界面语言')}</span>
            <select aria-label="Language / 语言" value={locale} onChange={e => setLocale(e.target.value === 'zh' ? 'zh' : 'en')}>
              <option value="en">English</option>
              <option value="zh">中文</option>
            </select>
          </label>
          <span className="workspace-local">
            <i />
            {t('本地运行')}
          </span>
        </header>
        <div className="mobile-navigation" aria-label={t('手机导航')}>
          <div className="mobile-primary">
            {[
              ['research', '研究'],
              ['market', '市场'],
              ['validation', '验证'],
            ].map(([id, label]) => (
              <button
                className={mobileGroup === id && !moreOpen ? 'selected' : ''}
                key={id}
                onClick={() => {
                  setMobileGroup(id)
                  setMoreOpen(false)
                }}
              >
                {t(label)}
              </button>
            ))}
            <button
              className={moreOpen ? 'selected' : ''}
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen(!moreOpen)}
            >
              {moreOpen ? <X size={15} /> : <Menu size={15} />}{t('更多')}
            </button>
          </div>
          <div className="mobile-secondary">
            {(moreOpen ? groups[3].items : mobileItems).map(([id, label, Icon]) => (
              <button key={id} className={page === id ? 'selected' : ''} onClick={() => go(id)}>
                <Icon size={14} />
                {t(label)}
              </button>
            ))}
          </div>
        </div>
        {activeProject && page !== 'projects' && (
          <div className="project-context-strip">
            <a href={'#' + withProject('projects', activeProject.id)}>{activeProject.name}</a>
            <span>{activeProject.symbols.join(' · ') || t('未关联证券')}</span>
            <small>{activeProject.question || t('项目研究')}</small>
          </div>
        )}
        <main>
          {error && (
            <Note tone="warn">
              {t('研究数据服务：')}{t(error)}
              <button
                className="text-button"
                onClick={() => reload().catch((e) => setError(e.message))}
              >
                {t('重试')}
              </button>
            </Note>
          )}
          {projectError && <Note tone="warn">{t(projectError)}</Note>}
          <PageBoundary key={page}>
            <Suspense fallback={<Empty>{t('正在打开{page}…', {page: t(active[1])})}</Empty>}>
              <Page status={status} reload={reload} setPage={go} />
            </Suspense>
          </PageBoundary>
        </main>
        <footer>
          QuantSandbox <span>{t('来源可追溯 · 参数可复算 · 研究与验证相连')}</span>
        </footer>
      </div>
    </div>
  )
}
export default function App() {
  return (
    <ProjectProvider>
      <Workspace />
    </ProjectProvider>
  )
}
