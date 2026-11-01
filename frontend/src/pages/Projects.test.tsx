// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Projects from './Projects'
import { api } from '../api'
import { post, request } from '../http'
const context = vi.hoisted(() => ({
  activeProject: null as any,
  projects: [] as any[],
  selectProject: vi.fn(),
  reloadProjects: vi.fn(),
  linkRecord: vi.fn(),
}))
vi.mock('../workspace/ProjectContext', () => ({ useProject: () => context }))
vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return { ...actual, api: vi.fn() }
})
vi.mock('../http', () => ({ post: vi.fn(), request: vi.fn() }))
const props = { status: { datasets: [] }, reload: async () => {}, setPage: vi.fn() }
beforeEach(() => {
  vi.clearAllMocks()
  const project = {
    id: 'p1',
    name: '公司周期研究',
    question: '利润与现金流是否同步？',
    symbols: ['600519'],
    conclusion: '原有结论',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    links: [{ kind: 'research', run_id: 'r1', linked_at: '2026-11-01T01:00:00Z' }],
  }
  context.activeProject = project
  context.projects = [project]
  context.selectProject.mockResolvedValue(undefined)
  context.reloadProjects.mockResolvedValue(undefined)
  context.linkRecord.mockResolvedValue(undefined)
  vi.mocked(api).mockResolvedValue([{ id: 'r1', title: '已冻结的财务比较' }])
  vi.mocked(request).mockImplementation(async (path) => (path === '/runs' ? { runs: [] } : {}))
  vi.mocked(post).mockResolvedValue({ id: 'p2' })
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
describe('project master-detail workspace', () => {
  it('keeps creation out of the main view and opens it as a focused dialog', async () => {
    const user = userEvent.setup()
    render(<Projects {...props} />)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('heading', { name: '公司周期研究' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '新建项目' }))
    expect(screen.getByRole('dialog', { name: '新建研究项目' })).toBeTruthy()
    await user.type(screen.getByLabelText('项目名称'), '新研究')
    await user.type(screen.getByLabelText('关联证券'), '000001,600036')
    await user.click(screen.getByRole('button', { name: '创建项目' }))
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/projects',
        expect.objectContaining({ name: '新研究', symbols: ['000001', '600036'] }),
      ),
    )
    expect(context.selectProject).toHaveBeenCalledWith('p2')
  })
  it('saves the conclusion to the current project and opens namespaced research records', async () => {
    const user = userEvent.setup()
    render(<Projects {...props} />)
    await screen.findByText('已冻结的财务比较')
    await user.click(screen.getByRole('tab', { name: '结论' }))
    const input = screen.getByLabelText('项目结论')
    await user.clear(input)
    await user.type(input, '现金流仍需观察')
    await user.click(screen.getByRole('button', { name: '保存结论' }))
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        '/projects/p1',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ conclusion: '现金流仍需观察' }),
        }),
      ),
    )
    await user.click(screen.getByRole('tab', { name: '研究证据' }))
    await user.click(screen.getByRole('button', { name: '查看' }))
    expect(props.setPage).toHaveBeenCalledWith('runs?run=r1')
  })
})
