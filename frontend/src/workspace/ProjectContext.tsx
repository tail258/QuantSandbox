import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { request, post } from '../http'

export type ProjectLink = { kind: 'research' | 'simulation'; run_id: string; linked_at: string }
export type Project = {
  id: string
  name: string
  question: string
  symbols: string[]
  links: ProjectLink[]
  conclusion?: string
  created_at: string
  updated_at: string
}
type ProjectContextValue = {
  activeProject: Project | null
  projects: Project[]
  selectProject: (id: string) => Promise<void>
  reloadProjects: () => Promise<void>
  linkRecord: (kind: ProjectLink['kind'], runId: string, projectId?: string | null) => Promise<void>
  error: string
}
const ProjectContext = createContext<ProjectContextValue | null>(null)
const storageKey = 'quantsandbox.activeProject'
export const strategyDemoPage = 'strategy-demo'
export const stockPage = 'stock'
export function withProject(route: string, projectId?: string) {
  const [page, query = ''] = route.split('?')
  const params = new URLSearchParams(query)
  if (projectId && page !== strategyDemoPage) params.set('project', projectId)
  else params.delete('project')
  return page + (params.size ? '?' + params.toString() : '')
}
function queryProject() {
  const [page, query] = location.hash.slice(1).split('?')
  return page === strategyDemoPage ? '' : new URLSearchParams(query || '').get('project') || ''
}

export function ProjectProvider({ children, enabled = true }: { children: ReactNode; enabled?: boolean }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [error, setError] = useState('')
  const activeId = useRef('')
  const selection = useRef(0)
  const mounted = useRef(true)
  const loadProject = useCallback(async (id: string, fromLink = false) => {
    const generation = ++selection.current
    setError('')
    if (!id) {
      activeId.current = ''
      setActiveProject(null)
      localStorage.removeItem(storageKey)
      location.hash = withProject(location.hash.slice(1) || 'projects')
      return
    }
    try {
      const project = await request<Project>('/projects/' + encodeURIComponent(id))
      if (!mounted.current || generation !== selection.current || (fromLink && id !== queryProject())) return
      activeId.current = project.id
      setActiveProject(project)
      setProjects((items) =>
        items.some((p) => p.id === project.id)
          ? items.map((p) => (p.id === project.id ? project : p))
          : [project, ...items],
      )
      localStorage.setItem(storageKey, project.id)
      if (fromLink) return
      const current = location.hash.slice(1)
      // Standalone detail links remain standalone even when another project
      // is restored from this browser's last project selection.
      const next = (!current || current.split('?')[0] === stockPage) && !queryProject() ? current : withProject(current, project.id)
      if (location.hash.slice(1) !== next) location.hash = next
    } catch (e) {
      if (mounted.current && generation === selection.current && (!fromLink || id === queryProject()))
        setError(e instanceof Error ? e.message : '项目读取失败')
      throw e
    }
  }, [])
  const selectProject = useCallback((id: string) => loadProject(id), [loadProject])
  const reloadProjects = useCallback(async () => {
    const list = await request<{ projects: Project[] }>('/projects')
    if (!mounted.current) return
    setProjects(list.projects)
    if (activeId.current) {
      const active = list.projects.find((p) => p.id === activeId.current)
      if (active) setActiveProject(active)
      else {
        activeId.current = ''
        setActiveProject(null)
        localStorage.removeItem(storageKey)
      }
    }
    setError('')
  }, [])
  const linkRecord = useCallback(
    async (kind: ProjectLink['kind'], runId: string, projectId?: string | null) => {
      const id = projectId === undefined ? activeId.current : projectId
      if (!id) return
      const updated = await post<Project>('/projects/' + id + '/links', { kind, run_id: runId })
      if (!mounted.current) return
      setProjects((items) => items.map((p) => (p.id === id ? updated : p)))
      if (activeId.current === id) setActiveProject(updated)
    },
    [],
  )
  useEffect(() => {
    if (!enabled) return
    mounted.current = true
    let live = true
    let routeProject = queryProject()
    const startup = selection.current
    request<{ projects: Project[] }>('/projects')
      .then(async (list) => {
        if (!live) return
        setProjects(list.projects)
        if (startup !== selection.current || routeProject !== queryProject()) return
        const wanted = routeProject || localStorage.getItem(storageKey) || list.projects[0]?.id
        if (wanted && list.projects.some((p) => p.id === wanted)) await loadProject(wanted, Boolean(routeProject))
        else if (wanted) setError('指定研究项目不存在，请重新选择。')
      })
      .catch((e) => {
        if (live) setError(e.message)
      })
    const hash = () => {
      const id = queryProject()
      if (id === routeProject) return
      routeProject = id
      selection.current++
      setError('')
      if (id && id !== activeId.current) loadProject(id, true).catch(() => {})
    }
    window.addEventListener('hashchange', hash)
    return () => {
      live = false
      mounted.current = false
      selection.current++
      window.removeEventListener('hashchange', hash)
    }
  }, [enabled, loadProject])
  return (
    <ProjectContext.Provider
      value={{ activeProject, projects, selectProject, reloadProjects, linkRecord, error }}
    >
      {children}
    </ProjectContext.Provider>
  )
}
export function useProject() {
  const context = useContext(ProjectContext)
  if (!context) throw new Error('useProject must be used within ProjectProvider')
  return context
}
