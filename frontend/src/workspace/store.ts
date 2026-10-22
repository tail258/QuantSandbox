import { computed } from 'vue'
import { request, post, download } from '../api/http'
import {
  toRunSummary,
  type Catalog,
  type Run,
  type RunConfig,
  type RunSummary,
  type RunList,
} from '../types'

import { workspace, selectionToken, nextSelection } from './state'
import { notify, clearNotification } from './ui'
import { pollRun, cancelPolling } from './polling'
export { workspace, notify, pollRun }
export { startSession, advanceSession, revealSession } from './replay'
let initialization: Promise<void> | undefined
let busyTasks = 0
const beginBusy = () => {
  busyTasks++
  workspace.busy = true
}
const endBusy = () => {
  workspace.busy = --busyTasks > 0
}
export const sourceLabel = computed(() =>
  workspace.session?.synthetic || workspace.active?.synthetic
    ? '合成数据'
    : workspace.active?.config.source === 'akshare'
      ? 'AKShare 行情'
      : '研究空间',
)
export const currentResult = computed(
  () =>
    workspace.session?.result ||
    (workspace.active &&
    (workspace.active.kind === 'backtest' || workspace.active.kind === 'branch')
      ? workspace.active.result
      : null),
)
export const runMetrics = (run: Run | RunSummary) => {
  if ('metrics' in run) return run.metrics || {}
  return run.result ? ('metrics' in run.result ? run.result.metrics : run.result.baseline) : {}
}
export const tickerName = (ticker: string) =>
  workspace.catalog?.tickers.find((item) => item.ticker === ticker)?.name || ticker
export const currentStrategyLabel = computed(
  () =>
    workspace.catalog?.strategies.find(
      (item) => item.name === workspace.active?.config.strategy.name,
    )?.label || '研究',
)
export async function refreshRuns() {
  const data = await request<RunList>('/runs')
  workspace.runs = data.runs
  return data.runs
}
export async function chooseRun(id: string) {
  if (workspace.active) cancelPolling(workspace.active.id)
  const token = nextSelection()
  workspace.loading = true
  workspace.error = ''
  workspace.session = null
  workspace.active = null
  workspace.cursor = 0
  try {
    const run = await request<Run>(`/runs/${id}`)
    if (token !== selectionToken) return
    workspace.active = run
    workspace.cursor = Math.max(
      0,
      (run.result && 'series' in run.result ? run.result.series.length : 1) - 1,
    )
    localStorage.setItem('qs.active', id)
    if (['queued', 'running'].includes(run.status)) {
      void pollRun(id).catch((error) => {
        if (token === selectionToken && workspace.active?.id === id) workspace.error = error.message
      })
    }
  } catch (error) {
    if (token === selectionToken) workspace.error = (error as Error).message
  } finally {
    if (token === selectionToken) workspace.loading = false
  }
}
export async function submitRun(config: RunConfig) {
  const token = nextSelection()
  beginBusy()
  workspace.error = ''
  workspace.session = null
  try {
    const run = await post<Run>('/runs', config)
    if (token !== selectionToken) return run
    workspace.active = run
    workspace.runs.unshift(toRunSummary(run))
    workspace.createOpen = false
    localStorage.setItem('qs.active', run.id)
    await pollRun(run.id)
    if (token === selectionToken) notify('回测已完成')
    return run
  } catch (error) {
    if (token !== selectionToken) return
    workspace.error = (error as Error).message
    throw error
  } finally {
    endBusy()
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
      }
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
  const token = selectionToken
  beginBusy()
  try {
    const run = await post<Run>(`/runs/${workspace.active.id}/branch`, {
      name,
      fork_date: forkDate,
      account: { position_size: positionSize },
    })
    await refreshRuns()
    if (token !== selectionToken) return
    await chooseRun(run.id)
    const branchSelection = selectionToken
    await pollRun(run.id)
    if (branchSelection === selectionToken) notify('历史分支已创建')
  } finally {
    endBusy()
  }
}
export function disposeWorkspace() {
  nextSelection()
  cancelPolling()
  clearNotification()
  initialization = undefined
}
export async function createExample() {
  if (!workspace.catalog) return
  return submitRun({
    ...JSON.parse(JSON.stringify(workspace.catalog.defaults)),
    name: '双均线 · 示例研究',
    source: 'demo',
  })
}
