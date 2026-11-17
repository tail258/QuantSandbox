// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setLocale } from '../i18n'
import StrategyDemo from './StrategyDemo'

// Noncanonical spacing and number precision help detect parsing and reserializing the evidence.
const baselineEvidence = '{\n  "sample": 1.234567890123456789\n}\n'
const comparisonEvidence = '{\n  "sample": 2.234567890123456789\n}\n'
const baseline = {
  synthetic: true,
  snapshot: { sha256: 'snapshot-fixed', start_date: '2023-10-02', end_date: '2024-06-28', rows: 195, version: 'fixture', suspension_dates: ['2024-03-04'] },
  parameters: { fast_period: 5, slow_period: 20 },
  period: { start_date: '2024-01-01', end_date: '2024-06-28', observations: 130, warmup_rows: 65 },
  account: { initial_cash: 1000000, position_size: .3, commission_rate: .0003, min_commission: 5, tax_rate: .0005, slippage_bps: 5 },
  metrics: { total_return: -2.2257, benchmark_return: -17.9842, max_drawdown: -5.8868, trade_count: 6, total_fees: 1000 },
  series: [{ date: '2024-01-01', equity: 1000000, benchmark: 990000 }, { date: '2024-06-28', equity: 977743, benchmark: 820158 }],
  trades: [{ date: '2024-01-09', signal_date: '2024-01-08', action: 'buy', price: 10.005, shares: 100, fee: 5, evidence: { execution_open: 10 } }],
  result_sha256: 'result-baseline',
  evidence: baselineEvidence,
}
const comparison = {
  ...baseline,
  parameters: { fast_period: 8, slow_period: 20 },
  metrics: { ...baseline.metrics, total_return: -3.5 },
  result_sha256: 'result-comparison',
  evidence: comparisonEvidence,
}
function respond(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }))
}

beforeEach(() => setLocale('en'))
afterEach(() => { cleanup(); setLocale('en'); vi.unstubAllGlobals() })

it('runs a baseline, compares edited windows, and replays the selected original evidence with a live language switch', async () => {
  const requests: { path: string; payload: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => {
    const payload = JSON.parse(String(init.body))
    requests.push({ path, payload })
    if (path === '/api/demo/strategy/run') return respond(payload.fast_period ? comparison : baseline)
    return respond({
      synthetic: true, matched: true, snapshot_sha256: 'snapshot-fixed',
      result_sha256: payload.evidence === baselineEvidence ? 'result-baseline' : 'result-comparison',
      compared_fields: ['metrics', 'series', 'trades', 'decisions'], different_fields: [],
    })
  }))
  const user = userEvent.setup()
  render(<StrategyDemo />)
  expect(screen.getByRole('heading', { name: 'Daily strategy demo' })).toBeTruthy()
  expect(requests).toEqual([])
  expect(screen.queryByRole('button', { name: 'Replay evidence' })).toBeNull()

  await user.click(screen.getByRole('button', { name: 'Run baseline' }))
  const results = await screen.findByRole('table', { name: 'Backtest results' })
  expect(within(results).getByText('-2.23%')).toBeTruthy()
  expect(within(results).getByText('-17.98%')).toBeTruthy()
  expect(screen.getByText('130')).toBeTruthy()
  expect(screen.getByText('2024-03-04')).toBeTruthy()
  expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Backtest results' }))

  const fast = screen.getByRole<HTMLInputElement>('spinbutton', { name: 'Fast window (days)' })
  expect(fast.value).toBe('5')
  await user.clear(fast)
  await user.type(fast, '60')
  await user.click(screen.getByRole('button', { name: 'Run comparison' }))
  expect(screen.getByRole('alert').textContent).toContain('Use whole numbers')
  expect(requests).toHaveLength(1)
  await user.clear(fast)
  await user.type(fast, '8')
  await user.click(screen.getByRole('button', { name: 'Run comparison' }))
  expect(await within(results).findByText('-3.5%')).toBeTruthy()
  const target = screen.getByRole<HTMLSelectElement>('combobox', { name: 'Result to replay' })
  expect(target.value).toBe('comparison')

  await user.click(screen.getByRole('button', { name: 'Replay evidence' }))
  expect((await screen.findByRole('status')).textContent).toContain('Replay matched the original result.')
  act(() => setLocale('zh'))
  expect(screen.getByRole('heading', { name: '日线策略演示' })).toBeTruthy()
  expect(screen.getByRole('status').textContent).toContain('重放与原结果一致。')
  expect(fast.value).toBe('8')

  await user.selectOptions(target, 'baseline')
  expect(screen.queryByRole('status')).toBeNull()
  await user.click(screen.getByRole('button', { name: '重放证据' }))
  expect((await screen.findByRole('status')).textContent).toContain('result-baseline')
  expect(requests).toEqual([
    { path: '/api/demo/strategy/run', payload: {} },
    { path: '/api/demo/strategy/run', payload: { fast_period: 8, slow_period: 20 } },
    { path: '/api/demo/strategy/replay', payload: { evidence: comparisonEvidence } },
    { path: '/api/demo/strategy/replay', payload: { evidence: baselineEvidence } },
  ])
})

it('rejects an unrelated comparison snapshot and refuses to display a false replay match', async () => {
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => {
    const payload = JSON.parse(String(init.body))
    if (path === '/api/demo/strategy/run') return respond(payload.fast_period ? { ...comparison, snapshot: { ...comparison.snapshot, sha256: 'snapshot-other' } } : baseline)
    return respond({ synthetic: true, matched: true, snapshot_sha256: 'snapshot-fixed', result_sha256: 'different-result', compared_fields: ['metrics'], different_fields: [] })
  }))
  const user = userEvent.setup()
  render(<StrategyDemo />)
  await user.click(screen.getByRole('button', { name: 'Run baseline' }))
  const fast = await screen.findByRole('spinbutton', { name: 'Fast window (days)' })
  await user.clear(fast)
  await user.type(fast, '8')
  await user.click(screen.getByRole('button', { name: 'Run comparison' }))
  expect((await screen.findByRole('alert')).textContent).toContain('different snapshot')
  expect(screen.queryByRole('columnheader', { name: 'Comparison 8 / 20' })).toBeNull()

  await user.click(screen.getByRole('button', { name: 'Replay evidence' }))
  expect(await screen.findByText('Replay did not match the original result.')).toBeTruthy()
  expect(screen.queryByRole('status')).toBeNull()
})
