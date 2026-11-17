// @vitest-environment jsdom
import { useState } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { setLocale } from '../i18n'
import TrackedFactors, { type FactorKey, type TrackedFactor } from './TrackedFactors'

const date = '2025-03-20'
const factors: TrackedFactor[] = [
  { key: 'sma20', value: 19.4, as_of: date, basis: 'raw_unadjusted' },
  { key: 'rsi14', value: null, as_of: date, basis: 'raw_unadjusted' },
  { key: 'bollinger20', value: 19, detail: 22.2, lower: 15.8, as_of: date, basis: 'raw_unadjusted' },
]

afterEach(() => { cleanup(); setLocale('en') })

it('applies a checklist change only after Save and retains it for retry on failure', async () => {
  setLocale('en')
  const user = userEvent.setup()
  const persistence = vi.fn<(keys: FactorKey[]) => Promise<void>>()
    .mockRejectedValueOnce(new Error('Provider unavailable'))
    .mockResolvedValueOnce(undefined)
  function Harness() {
    const [selection, setSelection] = useState<FactorKey[]>(['sma20'])
    return <TrackedFactors factors={factors} savedKeys={selection} onSave={async keys => {
      await persistence(keys)
      setSelection(keys)
    }} />
  }
  render(<Harness />)
  await user.click(screen.getByText('Tracked factors (1)'))
  await user.click(screen.getByRole('button', { name: 'Edit selection' }))
  const rsi = screen.getByRole('checkbox', { name: '14-session RSI' })
  await user.click(rsi)
  expect(persistence).not.toHaveBeenCalled()
  expect(screen.queryByText('Insufficient history')).toBeNull()

  await user.click(screen.getByRole('button', { name: 'Save selection' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Could not save the selection. Provider unavailable')
  expect(rsi).toHaveProperty('checked', true)
  expect(persistence).toHaveBeenCalledWith(['sma20', 'rsi14'])
  await user.click(screen.getByRole('button', { name: 'Save selection' }))
  expect(await screen.findByText('Tracked factors (2)')).toBeTruthy()
  expect(screen.getByText('Insufficient history')).toBeTruthy()
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Edit selection' }))
})

it('shows dated historical values without exposing the selection editor', async () => {
  setLocale('zh')
  const user = userEvent.setup()
  const save = vi.fn()
  render(<TrackedFactors factors={factors} savedKeys={['bollinger20']} historical onSave={save} />)
  await user.click(screen.getByText('跟踪因子 (1)'))
  expect(screen.getByText('按当前选择，在历史截点重新计算这些因子。')).toBeTruthy()
  expect(screen.getByText('未复权收盘价 · 上下轨为中轨 ±2 个总体标准差')).toBeTruthy()
  expect(screen.getByText('下轨 15.8 元')).toBeTruthy()
  expect(screen.getByText('上轨 22.2 元')).toBeTruthy()
  expect(screen.getByText(date).getAttribute('datetime')).toBe(date)
  expect(screen.queryByRole('button', { name: '编辑选择' })).toBeNull()
  expect(save).not.toHaveBeenCalled()
})
