// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Finance from './Finance'
import { api } from '../api'
import { post } from '../http'
const context = vi.hoisted(() => ({
  activeProject: { id: 'bank-project', symbols: ['000001', '600036'] },
  reloadProjects: vi.fn(),
}))
vi.mock('../workspace/ProjectContext', () => ({ useProject: () => context }))
vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return { ...actual, api: vi.fn() }
})
vi.mock('../http', () => ({ post: vi.fn() }))
vi.mock('../components', async () => {
  const actual = await vi.importActual<typeof import('../components')>('../components')
  return { ...actual, Chart: () => <div>comparison chart</div> }
})
const report = {
  date: '2026-06-30',
  profit: 100000000,
  assets: 200000000,
  available_date: '2026-08-30',
}
const props = {
  status: {
    metrics: { profit: '归母净利润', assets: '总资产' },
    series: [],
    templates: { bank: { name: '银行' } },
  },
  reload: async () => {},
  setPage: () => {},
}
beforeEach(() => {
  vi.clearAllMocks()
  context.activeProject = { id: 'bank-project', symbols: ['000001', '600036'] }
  context.reloadProjects.mockResolvedValue(undefined)
  vi.mocked(post).mockResolvedValue({})
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.startsWith('/profile/'))
      return {
        name: '银行样例',
        template: 'bank',
        peers: [],
        metrics: ['profit', 'assets'],
        focus: '资产质量与拨备',
      }
    if (path.startsWith('/finance?'))
      return [
        {
          symbol: '000001',
          rows: [report],
          raw_rows: [report],
          source: '公告',
          fetched_at: '2026-11-01',
        },
      ]
    if (path === '/save-finance') return { id: 'financial-run' }
    return {}
  })
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open')
  }
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
describe('project-driven company research', () => {
  it('opens the current project company, inherits peers and associates a saved comparison', async () => {
    const user = userEvent.setup()
    render(<Finance {...props} />)
    await screen.findByText('银行样例')
    expect((screen.getByLabelText('公司代码') as HTMLInputElement).value).toBe('000001')
    expect(screen.queryByRole('dialog')).toBeNull()
    await user.click(screen.getByRole('button', { name: '公司与同行配置' }))
    expect((screen.getByLabelText('同行代码（最多 5 家）') as HTMLInputElement).value).toBe(
      '600036',
    )
    await user.click(screen.getByRole('button', { name: '关闭' }))
    await user.click(screen.getByRole('button', { name: '保存本次比较' }))
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/projects/bank-project/links', {
        kind: 'research',
        run_id: 'financial-run',
      }),
    )
  })
  it('discards a delayed refresh from project A after switching to B, without keeping B busy', async () => {
    const user = userEvent.setup()
    let finishA!: (value: unknown) => void
    const delayedA = new Promise((done) => {
      finishA = done
    })
    let aRefreshFinished = false
    vi.mocked(api).mockImplementation(async (path, body) => {
      if (path.startsWith('/profile/')) {
        const code = path.split('/').at(-1)
        return {
          name: code === '000001' ? '银行 A' : '银行 B',
          template: 'bank',
          peers: [],
          metrics: ['profit', 'assets'],
          focus: '资产质量',
        }
      }
      if (path === '/fetch' && (body as any).symbol === '000001') {
        const value = await delayedA
        aRefreshFinished = true
        return value
      }
      if (path === '/fetch') return { cache_status: '已更新' }
      if (path.startsWith('/finance?')) {
        const isA = path.includes('symbols=000001')
        return [
          {
            symbol: isA ? '000001' : '600036',
            rows: [report],
            raw_rows: [report],
            source: isA ? '公告 A' : '公告 B',
            fetched_at: '2026-11-01',
          },
        ]
      }
      return {}
    })
    const view = render(<Finance {...props} />)
    await screen.findByRole('cell', { name: /000001/ })
    await user.click(screen.getByRole('button', { name: '更新并比较' }))
    await waitFor(() =>
      expect(
        vi
          .mocked(api)
          .mock.calls.some(
            ([path, body]) => path === '/fetch' && (body as any).symbol === '000001',
          ),
      ).toBe(true),
    )
    context.activeProject = { id: 'project-b', symbols: ['600036'] }
    view.rerender(<Finance {...props} />)
    await screen.findByText('银行 B')
    await screen.findByRole('cell', { name: /600036/ })
    expect((screen.getByRole('button', { name: '更新并比较' }) as HTMLButtonElement).disabled).toBe(
      false,
    )
    await act(async () => {
      finishA({ cache_status: '已更新' })
      await delayedA
    })
    await waitFor(() => expect(aRefreshFinished).toBe(true))
    expect((screen.getByLabelText('公司代码') as HTMLInputElement).value).toBe('600036')
    expect(screen.getByRole('cell', { name: /600036/ })).toBeTruthy()
    expect(screen.queryByRole('cell', { name: /000001/ })).toBeNull()
    expect(screen.getByText('公告 B')).toBeTruthy()
    expect(screen.queryByText('公告 A')).toBeNull()
  })
})
