import { request } from '../api/http'
import { toRunSummary, type Run } from '../types'
import { workspace, selectionToken } from './state'
const pending = new Map<string, { promise: Promise<Run>; controller: AbortController }>()
export function cancelPolling(id?: string) {
  for (const [key, task] of pending)
    if (!id || key === id) {
      task.controller.abort()
      pending.delete(key)
    }
}
function delay(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer)
      reject(new DOMException('Cancelled', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve()
    }, 750)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
  })
}
export function pollRun(id: string): Promise<Run> {
  const existing = pending.get(id)
  if (existing) return existing.promise
  const controller = new AbortController(),
    token = selectionToken
  const promise = (async () => {
    for (let attempt = 0; attempt < 900; attempt++) {
      const run = await request<Run>(`/runs/${id}`, { signal: controller.signal })
      if (controller.signal.aborted) throw new DOMException('Cancelled', 'AbortError')
      const index = workspace.runs.findIndex((item) => item.id === id)
      if (index >= 0) workspace.runs[index] = toRunSummary(run)
      const selected = workspace.active?.id === id && token === selectionToken
      if (selected) workspace.active = run
      if (['completed', 'failed', 'cancelled'].includes(run.status)) {
        if (selected)
          workspace.cursor = Math.max(
            0,
            (run.result && 'series' in run.result ? run.result.series.length : 1) - 1,
          )
        if (run.status === 'failed') throw new Error(run.error?.message || '研究任务执行失败')
        return run
      }
      await delay(controller.signal)
    }
    throw new Error('任务仍在运行，可在研究档案中查看进度。')
  })().finally(() => {
    if (pending.get(id)?.controller === controller) pending.delete(id)
  })
  pending.set(id, { promise, controller })
  return promise
}
