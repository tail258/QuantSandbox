// @vitest-environment jsdom
import type { ReactNode } from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Chart } from './components'
import { setLocale, t } from './i18n'

// Keep the Chart boundary under test independent of responsive SVG measurements.
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Line: ({ name }: { name: string }) => <span data-testid="series-name">{name}</span>,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  CartesianGrid: () => null,
  Legend: () => null,
}))

beforeEach(() => setLocale('en'))
afterEach(() => {
  cleanup()
  setLocale('en')
})

it('preserves imported series names and units that collide with translated interface words', () => {
  expect(t('研究')).not.toBe('研究')
  expect(t('股')).not.toBe('股')
  const rows = [{ date: '2024-01-02', value: 123 }]
  render(<Chart rows={rows} lines={[{ key: 'value', name: '研究' }]} unit="股" />)
  expect(screen.getByTestId('series-name').textContent).toBe('研究')
  expect(screen.getByText('股')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Export SVG' })).toBeTruthy()
  act(() => setLocale('zh'))
  expect(screen.getByTestId('series-name').textContent).toBe('研究')
  expect(screen.getByText('股')).toBeTruthy()
  expect(screen.getByRole('button', { name: '导出 SVG' })).toBeTruthy()
  expect(rows).toEqual([{ date: '2024-01-02', value: 123 }])
})

it('renders a chart without a unit and accepts caller-translated built-in labels', () => {
  render(
    <Chart
      rows={[{ date: '2024-01-02', value: 123 }]}
      lines={[{ key: 'value', name: t('策略权益') }]}
    />,
  )
  expect(screen.getByTestId('series-name').textContent).toBe(t('策略权益'))
  expect(screen.getByRole('button', { name: 'Export SVG' })).toBeTruthy()
})
