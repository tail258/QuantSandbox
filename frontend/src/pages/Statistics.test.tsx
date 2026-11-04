// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Statistics from './Statistics'
import { setLocale } from '../i18n'
import { api } from '../api'
import { post } from '../http'
const context = vi.hoisted(() => ({
  activeProject: {
    id: 'p1',
    symbols: ['600519', '000858'],
    links: [{ kind: 'research', run_id: 'statistics1' }],
  },
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
  return { ...actual, Chart: () => <div>aligned observations</div> }
})
const saved = {
  id: 'statistics1',
  kind: 'statistics',
  params: {
    x: 'old-a:close',
    y: 'old-b:close',
    start: '2025-01-01',
    end: '2026-10-28',
    frequency: 'D',
    transform: 'returns',
    lag: 0,
    horizon: 5,
    threshold: 0,
    operator: 'gt',
    nonoverlap: true,
  },
  sources: [
    { id: 'old-a:close', name: '归档X', source: '公开来源A' },
    { id: 'old-b:close', name: '归档Y', source: '公开来源B' },
  ],
  result: {
    correlation: 0.321,
    n: 123,
    conditional: {
      probability: 0.6,
      n: 50,
      up: 30,
      baseline: 0.5,
      baseline_n: 123,
      interval: [0.47, 0.72],
    },
    points: [],
    method: '固定快照',
  },
}
const props = {
  status: {
    series: [
      {
        id: 'new-a:close',
        name: '最新X',
        symbol: '600519',
        start: '2025-01-01',
        end: '2026-10-28',
      },
      {
        id: 'new-b:close',
        name: '最新Y',
        symbol: '000858',
        start: '2025-01-01',
        end: '2026-10-28',
      },
    ],
  },
  reload: async () => {},
  setPage: () => {},
}
beforeEach(() => {
  setLocale('zh')
  vi.clearAllMocks()
  context.reloadProjects.mockResolvedValue(undefined)
  vi.mocked(post).mockResolvedValue({})
  vi.mocked(api).mockImplementation(async (path) =>
    path === '/runs' ? [saved] : { ...saved, result: { ...saved.result, correlation: 0.654 } },
  )
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open')
  }
})
afterEach(() => {
  cleanup()
  setLocale('en')
  vi.restoreAllMocks()
})
describe('saved statistical research workspace', () => {
  it('shows one inline calculation action and no duplicate settings form before a first result', async () => {
    vi.mocked(api).mockImplementation(async (path) => (path === '/runs' ? [] : {}))
    render(<Statistics {...props} />)
    await waitFor(() =>
      expect((screen.getByLabelText('解释变量 X') as HTMLSelectElement).value).toBe('new-a:close'),
    )
    expect((screen.getByLabelText('观察变量 Y') as HTMLSelectElement).value).toBe('new-b:close')
    expect(screen.getAllByRole('button', { name: '计算并保存' })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: '调整实验条件' })).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('keeps the saved result and frozen source selection while editing, then associates the recalculation', async () => {
    const user = userEvent.setup()
    render(<Statistics {...props} />)
    await screen.findByText('0.321')
    expect(screen.queryByRole('dialog')).toBeNull()
    await user.click(screen.getByRole('button', { name: '调整实验条件' }))
    expect((screen.getByLabelText('解释变量 X') as HTMLSelectElement).value).toBe('old-a:close')
    const threshold = screen.getByLabelText('阈值（变化率 0.01=1%）')
    await user.clear(threshold)
    await user.type(threshold, '0.02')
    await user.click(screen.getByRole('button', { name: '保留条件并关闭' }))
    expect(screen.getByText('0.321')).toBeTruthy()
    expect(screen.getByText(/下方仍显示上次保存结果/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '计算并保存' }))
    await screen.findByText('0.654')
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/projects/p1/links', {
        kind: 'research',
        run_id: 'statistics1',
      }),
    )
  })
})
