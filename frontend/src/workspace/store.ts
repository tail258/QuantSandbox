import { computed, reactive } from 'vue'
import { request, post, download } from '../api/http'
import type { Catalog, ReplaySession, Run, RunConfig } from '../types'

export const workspace = reactive({
  catalog: null as Catalog | null,
  runs: [] as Run[],
  active: null as Run | null,
  session: null as ReplaySession | null,
  initialized: false,
  loading: false,
  error: '',
  busy: false,
  createOpen: false,
  toast: '',
  cursor: 0,
})
let selectionToken = 0
let initialization: Promise<void> | undefined
let toastTimer: number
export const notify = (message: string) => {
  workspace.toast = message
  window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    workspace.toast = ''
  }, 4500)
}
export const sourceLabel = computed(() =>
  workspace.session?.synthetic || workspace.active?.synthetic
    ? '合成数据'
    : workspace.active?.config.source === 'akshare'
      ? 'AKShare 行情'
      : '研究空间',
)
export const currentResult = computed(
  () => workspace.session?.result || workspace.active?.result || null,
)
export const runMetrics = (run: Run) => run.metrics || run.result?.metrics || {}
export const tickerName = (ticker: string) =>
  workspace.catalog?.tickers.find((item) => item.ticker === ticker)?.name || ticker
export const currentStrategyLabel = computed(
  () =>
    workspace.catalog?.strategies.find(
      (item) => item.name === workspace.active?.config.strategy.name,
    )?.label || '研究',
)
export async function refreshRuns() {
  const data = await request<{ runs: Run[] }>('/runs')
  workspace.runs = data.runs
  return data.runs
}
export async function chooseRun(id: string) {
  const token = ++selectionToken
  workspace.loading = true
  workspace.error = ''
  workspace.session = null
  workspace.active = null
  workspace.cursor = 0
  try {
    const run = await request<Run>(`/runs/${id}`)
    if (token !== selectionToken) return
    workspace.active = run
    workspace.cursor = Math.max(0, (run.result?.series?.length || 1) - 1)
    localStorage.setItem('qs.active', id)
  } catch (error) {
    if (token === selectionToken) workspace.error = (error as Error).message
  } finally {
    if (token === selectionToken) workspace.loading = false
  }
}
export async function pollRun(id: string) {
  const token = selectionToken
  for (let attempt = 0; attempt < 900; attempt++) {
    const run = await request<Run>(`/runs/${id}`)
    const index = workspace.runs.findIndex((item) => item.id === id)
    if (index >= 0) workspace.runs[index] = run
    if (workspace.active?.id === id && token === selectionToken) workspace.active = run
    if (['completed', 'failed', 'cancelled'].includes(run.status)) {
      if (workspace.active?.id === id)
        workspace.cursor = Math.max(0, (run.result?.series?.length || 1) - 1)
      await refreshRuns()
      if (run.status === 'failed') throw new Error(run.error?.message || '研究任务执行失败')
      return run
    }
    await new Promise((resolve) => window.setTimeout(resolve, 750))
  }
  throw new Error('任务仍在运行，可在研究档案中查看进度。')
}
export async function submitRun(config: RunConfig) {
  workspace.busy = true
  workspace.error = ''
  workspace.session = null
  try {
    const run = await post<Run>('/runs', config)
    ++selectionToken
    workspace.active = run
    workspace.runs.unshift(run)
    workspace.createOpen = false
    localStorage.setItem('qs.active', run.id)
    await pollRun(run.id)
    notify('回测已完成')
    return run
  } catch (error) {
    workspace.error = (error as Error).message
    throw error
  } finally {
    workspace.busy = false
  }
}
export async function initialize() {
  if (initialization) return initialization
  initialization = (async () => {
    workspace.loading = true
    workspace.error = ''
    try {
      const [catalog, runs] = await Promise.all([request<Catalog>('/catalog'), refreshRuns()])
      workspace.catalog = catalog
      const saved = localStorage.getItem('qs.active')
      const chosen =
        runs.find((run) => run.id === saved && ['backtest', 'branch'].includes(run.kind)) ||
        runs.find((run) => ['backtest', 'branch'].includes(run.kind))
      if (chosen) {
        await chooseRun(chosen.id)
        if (['queued', 'running'].includes(chosen.status))
          void pollRun(chosen.id).catch((error) => {
            workspace.error = error.message
          })
      } else
        await submitRun({
          ...structuredClone(catalog.defaults),
          name: '双均线 · 基线研究',
          source: 'demo',
        })
      workspace.initialized = true
    } catch (error) {
      workspace.error = (error as Error).message
      initialization = undefined
    } finally {
      workspace.loading = false
    }
  })()
  return initialization
}
export async function exportRun(id = workspace.active?.id) {
  if (!id) return
  try {
    await download(`/runs/${id}/export`, `quantsandbox-${id.slice(0, 8)}.json`)
    notify('研究证据包已导出')
  } catch (error) {
    workspace.error = (error as Error).message
  }
}
export async function createBranch(name: string, forkDate: string, positionSize: number) {
  if (!workspace.active) return
  workspace.busy = true
  try {
    const run = await post<Run>(`/runs/${workspace.active.id}/branch`, {
      name,
      fork_date: forkDate,
      account: { position_size: positionSize },
    })
    await refreshRuns()
    await chooseRun(run.id)
    await pollRun(run.id)
    notify('历史分支已创建')
  } finally {
    workspace.busy = false
  }
}
export async function startSession() {
  if (!workspace.active) return
  workspace.session = await post<ReplaySession>(`/runs/${workspace.active.id}/sessions`, {
    cursor: 0,
  })
  workspace.cursor = 0
}
export async function advanceSession(steps: number) {
  if (!workspace.session) return
  workspace.session = await post<ReplaySession>(`/sessions/${workspace.session.id}/advance`, {
    steps,
  })
}
export async function revealSession() {
  if (!workspace.session) return
  workspace.session = await post<ReplaySession>(`/sessions/${workspace.session.id}/reveal`)
}
