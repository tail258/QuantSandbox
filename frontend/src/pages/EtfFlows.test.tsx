// @vitest-environment jsdom
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EtfFlows from './EtfFlows'
import { api } from '../api'
import { setLocale } from '../i18n'
vi.mock('../workspace/ProjectContext', () => ({ useProject: () => ({ activeProject: null, linkRecord: vi.fn() }) }))
vi.mock('../EtfEvidence', () => ({ default: () => null }))
vi.mock('../EtfFlowChart', () => ({ default: () => null }))
vi.mock('../api', async () => ({ ...await vi.importActual('../api'), api: vi.fn() }))
const settings = { enabled: true, time: '15:30', timezone: 'Asia/Shanghai', last_job_id: null, status: null }
const dashboard = { universe: { '510300': 'ETF' }, run: null }
const reload = vi.fn(async () => {})
beforeEach(() => {
  setLocale('en')
  reload.mockClear()
  vi.mocked(api).mockReset()
  vi.mocked(api).mockImplementation(async (url) => url === '/etf/refresh-settings' ? settings : dashboard)
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })
it('shows damaged settings in both languages and permits repair without changing the scheduled time', async () => {
  const warning = '刷新设置损坏；自动刷新已暂停，请重新保存设置'
  vi.mocked(api).mockImplementation(async url => url === '/etf/refresh-settings' ? { ...settings, enabled: false, warning } : dashboard)
  const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ ...settings, enabled: false }) }))
  vi.stubGlobal('fetch', fetchMock)
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  expect(await screen.findByText('Refresh settings are damaged. Automatic refresh is paused; save the settings again.')).toBeTruthy()
  setLocale('zh'); expect(await screen.findByText(warning)).toBeTruthy()
  fireEvent.click(screen.getByText('保存时间'))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/research/etf/refresh-settings', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ enabled: false, time: '15:30' }) })))
  await waitFor(() => expect(screen.queryByText(warning)).toBeNull())
  expect((screen.getByLabelText('每天下午自动取数') as HTMLInputElement).checked).toBe(false)
})
it('refreshes recent data explicitly without sending custom history or forced-download parameters', async () => {
  vi.mocked(api).mockImplementation(async (url) => url === '/etf/refresh-settings' ? settings : url === '/etf/refresh-now' ? { id: 'now', status: 'running', stage: '准备', done: 0, total: 25 } : dashboard)
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  expect(await screen.findByLabelText('Fetch automatically every afternoon')).toBeTruthy()
  fireEvent.click(screen.getByText('Refresh now'))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/etf/refresh-now', {}))
  expect(await screen.findByText(/Completed items are cached/)).toBeTruthy()
  expect(screen.queryByText('Updated; showing the actual dates published by sources.')).toBeNull()
})
it('saves local schedule changes with PATCH and preserves the chosen time when disabling', async () => {
  const fetchMock = vi.fn(async (_url, options) => ({ ok: true, json: async () => ({ ...settings, ...JSON.parse(options.body) }) }))
  vi.stubGlobal('fetch', fetchMock)
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  const time = await screen.findByLabelText('Daily fetch time (Shanghai)')
  await waitFor(() => expect((screen.getByLabelText('Fetch automatically every afternoon') as HTMLInputElement).checked).toBe(true))
  fireEvent.change(time, { target: { value: '16:10' } })
  fireEvent.click(screen.getByText('Save time'))
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/research/etf/refresh-settings', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ enabled: true, time: '16:10' }) })))
  await waitFor(() => expect((screen.getByText('Save time') as HTMLButtonElement).disabled).toBe(true))
  fireEvent.click(screen.getByLabelText('Fetch automatically every afternoon'))
  await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith('/api/research/etf/refresh-settings', expect.objectContaining({ body: JSON.stringify({ enabled: false, time: '16:10' }) })))
})
it('resumes an existing job on mount and keeps failure visible without claiming freshness', async () => {
  vi.useFakeTimers()
  vi.mocked(api).mockImplementation(async (url) => url === '/etf/refresh-settings' ? { ...settings, last_job_id: 'existing', status: 'running' } : url === '/etf/jobs/existing' ? { id: 'existing', status: 'failed', error: 'provider unavailable' } : dashboard)
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
  expect(api).toHaveBeenCalledWith('/etf/jobs/existing')
  expect(api).not.toHaveBeenCalledWith('/etf/refresh-now', {})
  expect(screen.getByText(/provider unavailable/)).toBeTruthy()
})
it('ignores late initial responses after unmount', async () => {
  let resolve!: (value: unknown) => void
  vi.mocked(api).mockImplementation((url) => url === '/etf/dashboard' ? new Promise(r => { resolve = r }) : Promise.resolve(settings))
  const view = render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  view.unmount()
  await act(async () => { resolve(dashboard) })
  expect(reload).not.toHaveBeenCalled()
})
it('offers Chinese refresh controls and keeps historical fetching collapsed', async () => {
  setLocale('zh')
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  expect(await screen.findByText('立即刷新')).toBeTruthy()
  expect(screen.getByText('每天下午自动取数')).toBeTruthy()
  expect(screen.queryByText('按自定义日期取数')).toBeNull()
  fireEvent.click(screen.getByText('样本与参数'))
  expect(screen.getByText('按自定义日期取数')).toBeTruthy()
})



it('reloads the dashboard when mount settings arrive with an already completed job', async () => {
  let resolveSettings!: (value: unknown) => void
  vi.mocked(api).mockImplementation((url) => url === '/etf/refresh-settings'
    ? new Promise(resolve => { resolveSettings = resolve }) : Promise.resolve(dashboard))
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  await waitFor(() => expect(api).toHaveBeenCalledWith('/etf/dashboard', {}))
  await act(async () => { resolveSettings({ ...settings, last_job_id: 'finished-before-mount', status: 'completed' }) })
  await waitFor(() => expect(reload).toHaveBeenCalledTimes(1))
  expect(vi.mocked(api).mock.calls.filter(([url]) => url === '/etf/dashboard')).toHaveLength(2)
  expect(screen.queryByText('Updated; showing the actual dates published by sources.')).toBeNull()
})
it('detects a scheduled job completed between settings polls and reloads only once', async () => {
  vi.useFakeTimers()
  let completed = false
  vi.mocked(api).mockImplementation(async (url) => url === '/etf/refresh-settings'
    ? { ...settings, last_job_id: completed ? 'fast-scheduled-job' : null, status: completed ? 'completed' : null }
    : dashboard)
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
  completed = true
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(reload).toHaveBeenCalledTimes(1)
  expect(vi.mocked(api).mock.calls.filter(([url]) => url === '/etf/dashboard')).toHaveLength(2)
  await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
  expect(reload).toHaveBeenCalledTimes(1)
  expect(vi.mocked(api).mock.calls.filter(([url]) => url === '/etf/dashboard')).toHaveLength(2)
})

it('translates the last-attempt state into Chinese', async () => {
  setLocale('zh')
  vi.mocked(api).mockImplementation(async (url) => url === '/etf/refresh-settings'
    ? { ...settings, last_attempt: '2026-11-06T15:30:00+08:00', status: 'completed' } : dashboard)
  render(<EtfFlows reload={reload} status={{}} setPage={vi.fn()} />)
  expect(await screen.findByText(/上次尝试.*已完成/)).toBeTruthy()
  expect(screen.queryByText(/completed/)).toBeNull()
})
