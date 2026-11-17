// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import type { Candle, ChanEvent } from '../chan/model'
import { setLocale } from '../i18n'
import DecisionChart, { type DecisionLevel } from './DecisionChart'

const bars: Candle[] = Array.from({ length: 130 }, (_, i) => ({
  date: new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10),
  open: 9, low: 8, high: 12, close: 11, volume: 400_000 + i,
}))

function fractal(id: string, index: number, kind: 'top' | 'bottom', confirmed: boolean): ChanEvent {
  const date = bars[index].date
  const firstSeen = bars[index + 1].date
  return { layer: 'fractals', action: confirmed ? 'confirmed' : 'created', index: index + 1, date: firstSeen,
    structure: { id, kind, index, date, price: kind === 'top' ? 12 : 8,
      start_index: index, end_index: index, start_date: date, end_date: date, high: 12, low: 8,
      status: confirmed ? 'confirmed' : 'candidate', first_seen_date: firstSeen, confirmed_date: confirmed ? firstSeen : null } }
}

const structures = [fractal('old', 13, 'bottom', true), fractal('top', 110, 'top', true), fractal('pending', 127, 'bottom', false)]
const center: ChanEvent = {
  layer: 'centers', action: 'confirmed', index: 115, date: bars[115].date,
  structure: { id: 'center', start_index: 109, end_index: 114, high: 12, low: 8, upper: 11, lower: 9, phase: 'active',
    start_date: bars[109].date, end_date: bars[114].date, status: 'confirmed', first_seen_date: bars[114].date, confirmed_date: bars[115].date },
}

afterEach(() => { cleanup(); setLocale('en') })

it('inspects candle volume and named structures, including provisional status, and selects with the keyboard', async () => {
  setLocale('en')
  const user = userEvent.setup()
  const select = vi.fn()
  const { container } = render(<DecisionChart bars={bars} structures={structures} levels={[]} selectedId={null} onSelect={select} volumeUnit="shares" />)
  expect(container.querySelectorAll('.decision-volume-bar')).toHaveLength(80)
  expect(screen.getByText('400,129')).toBeTruthy()

  const pending = screen.getByRole('button', { name: /Bottom fractal.*Provisional/ })
  await user.hover(pending)
  expect(within(screen.getByRole('region', { name: 'Chart evidence' })).getByText('Provisional')).toBeTruthy()
  expect(within(screen.getByRole('region', { name: 'Chart evidence' })).getByText(bars[128].date)).toBeTruthy()
  await user.unhover(pending)

  await user.tab()
  for (let i = 0; i < 6; i++) await user.tab()
  expect(document.activeElement).toBe(pending)
  await user.keyboard('{ArrowLeft}{Enter}')
  expect(document.activeElement).toBe(screen.getByRole('button', { name: /Top fractal.*Confirmed/ }))
  expect(select).toHaveBeenCalledWith('top', undefined)

  await user.click(screen.getByRole('checkbox', { name: 'Fractals' }))
  expect(screen.queryByRole('button', { name: /Top fractal/ })).toBeNull()
})

it('moves the window to selected historical evidence and distinguishes two levels from one center', async () => {
  setLocale('en')
  const user = userEvent.setup()
  const select = vi.fn()
  const evidence: DecisionLevel['evidence'] = { layer: 'centers', id: 'center', index: 114,
    geometry_date: bars[114].date, confirmed_date: bars[115].date }
  const levels: DecisionLevel[] = [{ role: 'support', price: 9, evidence }, { role: 'resistance', price: 11, evidence }]
  const data = { bars, structures: [...structures, center], levels, onSelect: select, volumeUnit: 'shares' }
  const view = render(<DecisionChart {...data} selectedId="old" />)
  const candle = (index: number) => view.container.querySelector(`.decision-candle[data-date="${bars[index].date}"]`)
  expect(candle(13)).toBeTruthy()
  expect(candle(129)).toBeNull()
  expect(view.container.querySelector('.decision-anchor[data-evidence-id="old"]')).toBeTruthy()
  expect(screen.getByText('Price levels are from the latest close.')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: 'Show latest candles' }))
  expect(candle(13)).toBeNull()
  expect(candle(129)).toBeTruthy()

  await user.click(screen.getByRole('button', { name: /Resistance 11/ }))
  expect(select).toHaveBeenCalledWith('center', 'resistance')
  view.rerender(<DecisionChart {...data} selectedId="center" selectedRole="resistance" />)
  expect(screen.getByRole('button', { name: /Resistance 11/ }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByRole('button', { name: /Support 9/ }).getAttribute('aria-pressed')).toBe('false')
  expect(view.container.querySelector('.decision-anchor[data-evidence-id="center"]')).toBeTruthy()
})
