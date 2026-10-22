import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { toRunSummary, type Run, type RunConfig } from '../types'
vi.mock('../api/http', () => ({ request: vi.fn(), post: vi.fn(), download: vi.fn() }))
import { request, post } from '../api/http'
import { workspace, initialize, disposeWorkspace, chooseRun, submitRun, runMetrics } from './store'
import { pollRun, cancelPolling } from './polling'
import { startSession } from './replay'
const deferred = <T>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
const run = (id: string, status = 'completed') =>
  ({
    id,
    kind: 'backtest',
    status,
    result: { series: [{ date: '2024-01-01' }, { date: '2024-01-02' }] },
  }) as Run
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: vi.fn() })
  Object.assign(workspace, {
    runs: [],
    active: null,
    session: null,
    cursor: 0,
    initialized: false,
    error: '',
  })
})
afterEach(() => {
  disposeWorkspace()
  vi.useRealTimers()
})
it('opens an empty archive without creating a demo', async () => {
  vi.mocked(request).mockImplementation(async (path) =>
    path === '/catalog' ? { defaults: {} } : { runs: [] },
  )
  await initialize()
  expect(workspace.initialized).toBe(true)
  expect(workspace.runs).toEqual([])
  expect(post).not.toHaveBeenCalled()
})
it('ignores selection responses that arrive after the next selection', async () => {
  const first = deferred<Run>()
  vi.mocked(request).mockImplementation((path) =>
    path === '/runs/old' ? first.promise : Promise.resolve(run('new')),
  )
  const old = chooseRun('old')
  await chooseRun('new')
  first.resolve(run('old'))
  await old
  expect(workspace.active?.id).toBe('new')
})
it('shares a poll and prevents stale completion from moving the current cursor', async () => {
  const response = deferred<Run>()
  workspace.active = run('old')
  workspace.runs = [toRunSummary(run('old'))]
  vi.mocked(request).mockImplementation((path) =>
    path === '/runs/old' ? response.promise : Promise.resolve(run('new')),
  )
  const first = pollRun('old'),
    second = pollRun('old')
  expect(first).toBe(second)
  // A new selection cancels the selected task; its response must not update the new selection.
  const cancelled = first.catch((error) => error)
  await chooseRun('new')
  workspace.cursor = 7
  response.resolve(run('old'))
  await cancelled
  expect(workspace.active?.id).toBe('new')
  expect(workspace.cursor).toBe(7)
})
it('cancels pending poll timers and permits a fresh polling lifecycle', async () => {
  vi.useFakeTimers()
  vi.mocked(request).mockResolvedValue(run('a', 'running'))
  const task = pollRun('a').catch((error) => error)
  await vi.advanceTimersByTimeAsync(0)
  cancelPolling()
  expect((await task).name).toBe('AbortError')
  await vi.advanceTimersByTimeAsync(3000)
  expect(request).toHaveBeenCalledTimes(1)
  vi.mocked(request).mockResolvedValue(run('a'))
  expect((await pollRun('a')).status).toBe('completed')
})
it('does not attach an old replay session after switching research', async () => {
  const response = deferred<unknown>()
  workspace.active = run('old')
  vi.mocked(post).mockReturnValue(response.promise)
  vi.mocked(request).mockResolvedValue(run('new'))
  const start = startSession()
  await chooseRun('new')
  response.resolve({ id: 'session', run_id: 'old' })
  await start
  expect(workspace.session).toBeNull()
})

it('does not publish a failure from a polling task after a selection switch', async () => {
  const response = deferred<Run>()
  workspace.active = run('old')
  vi.mocked(request).mockImplementation((path) =>
    path === '/runs/old' ? response.promise : Promise.resolve(run('new')),
  )
  const task = pollRun('old').catch((error) => error)
  await chooseRun('new')
  response.resolve({ ...run('old', 'failed'), error: { code: 'failed', message: 'old failure' } })
  await task
  expect(workspace.error).toBe('')
  expect(workspace.active?.id).toBe('new')
})

it('suppresses obsolete submission failures and keeps busy until all submissions settle', async () => {
  const firstPost = deferred<Run>(),
    secondPost = deferred<Run>()
  vi.mocked(post).mockReturnValueOnce(firstPost.promise).mockReturnValueOnce(secondPost.promise)
  vi.mocked(request).mockResolvedValue(run('selected'))
  const first = submitRun({} as RunConfig),
    second = submitRun({} as RunConfig)
  await chooseRun('selected')
  firstPost.resolve(run('old'))
  await expect(first).resolves.toBeDefined()
  expect(workspace.busy).toBe(true)
  secondPost.resolve(run('other'))
  await second
  expect(workspace.busy).toBe(false)
  expect(workspace.active?.id).toBe('selected')
  expect(workspace.error).toBe('')
})
it('uses baseline metrics for experiment detail and strips results from summaries', () => {
  const pressure = {
    ...run('pressure'),
    kind: 'pressure',
    result: { kind: 'stress', baseline: { total_return: 12 }, scenarios: [] },
  } as Run
  expect(runMetrics(pressure).total_return).toBe(12)
  const summary = toRunSummary(pressure)
  expect(summary.metrics?.total_return).toBe(12)
  expect('result' in summary).toBe(false)
})

it('does not reject a submitting caller when switching cancels its old poll', async () => {
  const response = deferred<Run>()
  vi.mocked(post).mockResolvedValue(run('old', 'running'))
  vi.mocked(request).mockImplementation((path) =>
    path === '/runs/old' ? response.promise : Promise.resolve(run('new')),
  )
  const submission = submitRun({} as RunConfig)
  await Promise.resolve()
  await chooseRun('new')
  response.resolve(run('old'))
  await expect(submission).resolves.toBeUndefined()
  expect(workspace.active?.id).toBe('new')
  expect(workspace.error).toBe('')
})
