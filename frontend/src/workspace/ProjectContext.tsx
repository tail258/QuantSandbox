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
export function withProject(route: string, projectId?: string) {
  const [page, query = ''] = route.split('?')
  const params = new URLSearchParams(query)
  if (projectId) params.set('project', projectId)
  else params.delete('project')
  return page + (params.size ? '?' + params.toString() : '')
}
function queryProject() {
  return new URLSearchParams(location.hash.split('?')[1] || '').get('project') || ''
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [error, setError] = useState('')
  const activeId = useRef('')
  const selection = useRef(0)
  const mounted = useRef(true)
  const selectProject = useCallback(async (id: string) => {
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
      if (!mounted.current || generation !== selection.current) return
      activeId.current = project.id
      setActiveProject(project)
      setProjects((items) =>
        items.some((p) => p.id === project.id)
          ? items.map((p) => (p.id === project.id ? project : p))
          : [project, ...items],
      )
      localStorage.setItem(storageKey, project.id)
      const next = withProject(location.hash.slice(1) || 'projects', project.id)
      if (location.hash.slice(1) !== next) location.hash = next
    } catch (e) {
      if (mounted.current && generation === selection.current)
        setError(e instanceof Error ? e.message : '项目读取失败')
      throw e
    }
  }, [])
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
    mounted.current = true
    let live = true
    request<{ projects: Project[] }>('/projects')
      .then(async (list) => {
        if (!live) return
        setProjects(list.projects)
        const wanted = queryProject() || localStorage.getItem(storageKey) || list.projects[0]?.id
        if (wanted && list.projects.some((p) => p.id === wanted)) await selectProject(wanted)
        else if (wanted) setError('指定研究项目不存在，请重新选择。')
      })
      .catch((e) => {
        if (live) setError(e.message)
      })
    const hash = () => {
      const id = queryProject()
      if (id && id !== activeId.current) selectProject(id).catch(() => {})
    }
    window.addEventListener('hashchange', hash)
    return () => {
      live = false
      mounted.current = false
      selection.current++
      window.removeEventListener('hashchange', hash)
    }
  }, [selectProject])
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
