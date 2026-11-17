// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setLocale } from '../i18n'
import StockDecision from './StockDecision'

const mocks = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('../http', () => ({ request: mocks.request }))
vi.mock('../workspace/ProjectContext', () => ({ useProject: () => ({ activeProject: null }) }))
vi.mock('../decision/DecisionChart', () => ({ default: ({ selectedId }: { selectedId: string | null }) => <output>{selectedId ?? '未定位'}</output> }))

function data(symbol: string, name: string) {
  const evidence = { layer: 'fractals', id: 'fractal:5', index: 5, geometry_date: '2025-01-27', confirmed_date: '2025-01-29' }
  return { symbol, project_id: null, status: 'ready', warning: null,
    instrument: { name, exchange: 'SSE', kind: 'stock', symbol },
    input: { id: '0123456789abcdef0123', source_url: 'https://example.test/price', source: 'Fixture',
      calendar_source_url: 'https://example.test/calendar', calendar_source: 'Fixture calendar', missing_sessions: [],
      suspended_sessions: [], reference_breaks: [], volume_unit: 'shares', start_date: '2025-01-21', end_date: '2025-01-30' },
    bars: [], structures: { fractals: [{ id: evidence.id, status: 'confirmed', confirmed_date: '2025-01-29', first_seen_date: '2025-01-29' }] },
    plan: { observation_session: '2025-01-31', as_of: '2025-01-30', data_quality: 'checked', data_issues: [],
      trend: 'rising', phase: 'inside_range', volume: { observed_ratio: 1.2 }, level_basis: 'confirmed_fractals', last_center: null,
      watch_reason: 'no_clear_entry_room', levels: [{ role: 'support', price: 10.25, evidence }],
      scenarios: [{ kind: 'support_failure', action: 'review_exit_if_holding', evidence_roles: ['support'],
        conditions: [{ field: 'close', comparison: 'lt', value: 10.25 }] }, { kind: 'otherwise', action: 'watch', evidence_roles: [], conditions: [] }] } }
}

function changeRoute(hash: string) {
  window.history.replaceState(null, '', hash)
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

describe('stock decision detail', () => {
  beforeEach(() => {
    setLocale('zh')
    mocks.request.mockReset()
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2025-01-31T10:00:00+08:00'))
  })
  afterEach(() => { cleanup(); vi.restoreAllMocks(); window.history.replaceState(null, '', '#') })

  it('shows cached structure while refreshing but enables current conditions only when refreshed', async () => {
    changeRoute('#stock?symbol=600105')
    let finish!: (value: ReturnType<typeof data>) => void
    mocks.request.mockImplementation((_: string, options: RequestInit) => options.method === 'POST'
      ? new Promise(resolve => { finish = resolve }) : Promise.resolve(data('600105', '永鼎股份')))
    render(<StockDecision/>)
    await screen.findByRole('heading', { name: '永鼎股份' })
    expect(screen.queryByRole('heading', { name: '支撑失效' })).toBeNull()
    await act(() => finish(data('600105', '永鼎股份')))
    await screen.findByRole('heading', { name: '支撑失效' })
    const linkedEvidence = screen.getAllByRole('button', { name: /支撑 \/ 失效位/ })
    fireEvent.click(linkedEvidence[linkedEvidence.length - 1])
    expect(screen.getAllByText('fractal:5')).toHaveLength(2)
  })

  it('cannot replace a new symbol with a late response from the previous URL', async () => {
    changeRoute('#stock?symbol=600105')
    let old!: (value: ReturnType<typeof data>) => void
    mocks.request.mockImplementation((path: string, options: RequestInit) => {
      if (path.includes('600105') && options.method === 'POST') return new Promise(resolve => { old = resolve })
      return Promise.resolve(data(path.includes('600105') ? '600105' : '000338', path.includes('600105') ? '永鼎股份' : '潍柴动力'))
    })
    render(<StockDecision/>)
    await screen.findByRole('heading', { name: '永鼎股份' })
    act(() => changeRoute('#stock?symbol=000338'))
    await screen.findByRole('heading', { name: '潍柴动力' })
    await act(() => old(data('600105', '永鼎股份')))
    expect(screen.queryByRole('heading', { name: '永鼎股份' })).toBeNull()
    await waitFor(() => expect(mocks.request.mock.calls.some(([path]) => path.includes('/000338/refresh'))).toBe(true))
  })

  it('reads a pinned retrospective view without contacting the quotes provider', async () => {
    changeRoute('#stock?symbol=600105&snapshot=0123456789abcdef0123&as_of=2025-01-30')
    const sample = data('600105', '永鼎股份')
    mocks.request.mockResolvedValue({ ...sample, input: { ...sample.input, historical: true, expected_session: '2025-01-30' },
      plan: { ...sample.plan, data_quality: 'limited', scenarios: sample.plan.scenarios.slice(-1) } })
    render(<StockDecision/>)
    await screen.findByRole('heading', { name: '永鼎股份' })
    expect(mocks.request).toHaveBeenCalledTimes(1)
    expect(mocks.request.mock.calls[0][0]).toContain('snapshot_id=0123456789abcdef0123&as_of=2025-01-30')
    expect(screen.getByText('历史回看 · 截点 2025-01-30')).toBeTruthy()
  })

  it('retires a live condition once its Shanghai observation session closes', async () => {
    changeRoute('#stock?symbol=600105')
    mocks.request.mockResolvedValue(data('600105', '永鼎股份'))
    render(<StockDecision/>)
    await screen.findByRole('heading', { name: '支撑失效' })
    vi.mocked(Date.now).mockReturnValue(Date.parse('2025-01-31T15:01:00+08:00'))
    act(() => window.dispatchEvent(new Event('focus')))
    expect(screen.queryByRole('heading', { name: '支撑失效' })).toBeNull()
    expect(screen.getByText('该观察日已收盘，请刷新后查看新的条件。')).toBeTruthy()
    expect(mocks.request).toHaveBeenCalledTimes(2)
  })
})
