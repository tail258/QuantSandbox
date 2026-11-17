// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ChanEvent, Replay, Snapshot, Structure } from '../chan/model'
import { setLocale } from '../i18n'
import { ProjectProvider, useProject, type Project } from '../workspace/ProjectContext'
import ChanReplay from './ChanReplay'

const evidence = '{\n  "precision": 10.0000000000000001\n}\n'
const importedEvidence = '{\n  "precision": 9.123456789123456789\n}\n'
const dates = ['2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09']
const candidate: Structure = {
  id: 'fractal:1', status: 'candidate', first_seen_date: dates[2], confirmed_date: null,
  start_index: 1, end_index: 1, start_date: dates[1], end_date: dates[1], low: 8, high: 13,
}
const first: ChanEvent = {
  index: 2, date: dates[2], layer: 'fractals', action: 'created',
  structure: { ...candidate, kind: 'top', date: dates[1], index: 1, price: 13 },
}
const final: ChanEvent = {
  ...first, index: 3, date: dates[3], action: 'confirmed',
  structure: { ...first.structure, status: 'confirmed', confirmed_date: dates[3] },
}
const demo: Replay = {
  input: {
    mode: 'synthetic', price_basis: 'synthetic', snapshot_id: 'fixture', symbol: 'DEMO',
    source: 'Synthetic', start_date: dates[0], end_date: dates[3], row_count: 4, sha256: 'frozen-input',
  },
  bars: dates.map((date, i) => ({ date, open: 10, close: 10 + i, low: 8 - i, high: 12 + i, volume: 40 })),
  result: {
    algorithm: 'daily-chan-v1',
    frames: dates.map((date, index) => ({ date, index, event_start: Math.max(0, index - 2), event_end: Math.max(0, index - 1) })),
    events: [first, final],
  },
  evidence,
}
const respond = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body)))
const props = { status: {}, reload: async () => {}, setPage: () => {} }

function project(id: string, symbol: string): Project {
  return { id, name: id, question: '', symbols: [symbol], links: [], created_at: dates[0], updated_at: dates[0] }
}

function listing(id: string, symbol: string): Snapshot {
  return { id, symbol, start_date: dates[0], end_date: dates[3], row_count: 4, source: 'Provider', price_basis: 'raw_unadjusted' }
}

beforeEach(() => { setLocale('en'); localStorage.clear(); history.replaceState({}, '', '/#chan') })
afterEach(() => { cleanup(); setLocale('en'); vi.unstubAllGlobals() })

it('replays each visible close, updates structure status and overlays, and verifies raw evidence', async () => {
  const calls: [string, unknown][] = []
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => {
    calls.push([path, init.body])
    if (path === '/api/chan/demo') return respond(demo)
    return respond({ ...demo, evidence: init.body, verified: true })
  }))
  const user = userEvent.setup()
  render(<ProjectProvider enabled={false}><ChanReplay {...props} /></ProjectProvider>)
  await user.click(screen.getByRole('button', { name: 'Try the offline example' }))
  expect(await screen.findByRole('heading', { name: 'Synthetic example' })).toBeTruthy()
  expect(within(screen.getByRole('region', { name: 'Observation date' })).getByText('Synthetic example')).toBeTruthy()
  const chart = screen.getByRole('img', { name: 'Daily candlestick chart' })
  const slider = screen.getByRole('slider', { name: 'Replay position' })
  expect(slider.getAttribute('aria-valuetext')).toBe(dates[3])
  expect(chart.querySelectorAll('.chan-candle')).toHaveLength(4)
  expect(chart.querySelector('.fractals.confirmed')).toBeTruthy()
  const changes = screen.getByRole('table', { name: 'Changes at this close' })
  expect(within(changes).getByText('Confirmed')).toBeTruthy()

  await user.click(screen.getByRole('button', { name: 'Previous candle' }))
  expect(slider.getAttribute('aria-valuetext')).toBe(dates[2])
  expect(chart.querySelectorAll('.chan-candle')).toHaveLength(3)
  expect(chart.querySelector('.fractals.candidate')).toBeTruthy()
  expect(chart.querySelector('.fractals.confirmed')).toBeNull()
  expect(within(changes).queryByText(dates[3])).toBeNull()

  await user.click(screen.getByRole('checkbox', { name: 'Fractals' }))
  expect(chart.querySelector('.chan-overlay.fractals')).toBeNull()
  await user.click(screen.getByRole('button', { name: 'Verify evidence' }))
  expect(await screen.findByText('Evidence replay verified. Recomputed structures and events match.')).toBeTruthy()
  expect(slider.getAttribute('aria-valuetext')).toBe(dates[2])

  const file = new File([importedEvidence], 'chan.json', { type: 'application/json' })
  Object.defineProperty(file, 'text', { value: async () => importedEvidence })
  await user.upload(screen.getByLabelText('Open evidence JSON'), file)
  expect(await screen.findByText('Imported evidence')).toBeTruthy()
  expect(calls).toEqual([
    ['/api/chan/demo', undefined], ['/api/chan/replay', evidence], ['/api/chan/replay', importedEvidence],
  ])
  act(() => setLocale('zh'))
  expect(screen.getByRole('heading', { name: '日线缠论重放' })).toBeTruthy()
  expect(screen.getByRole('slider', { name: '重放位置' }).getAttribute('aria-valuetext')).toBe(dates[3])
})

it('limits analysis to the selected project and ignores an old response after switching projects', async () => {
  const alpha = project('alpha', '000338')
  const beta = project('beta', '000962')
  let oldSignal: AbortSignal | null | undefined
  let finishOld: (response: Response) => void = () => {}
  const pending = new Promise<Response>(resolve => { finishOld = resolve })
  vi.stubGlobal('fetch', vi.fn((path: string, init: RequestInit) => {
    switch (path) {
      case '/api/projects': return respond({ projects: [alpha, beta] })
      case '/api/projects/alpha': return respond(alpha)
      case '/api/projects/beta': return respond(beta)
      case '/api/projects/alpha/chan/snapshots': return respond({ snapshots: [listing('alpha-bars', '000338')] })
      case '/api/projects/beta/chan/snapshots': return respond({ snapshots: [listing('beta-bars', '000962')] })
      case '/api/projects/alpha/chan/analyze':
        expect(init.body).toBe('{"snapshot_id":"alpha-bars"}')
        oldSignal = init.signal
        return pending
      case '/api/projects/beta/chan/analyze':
        expect(init.body).toBe('{"snapshot_id":"beta-bars"}')
        return respond({ ...demo, input: { ...demo.input, mode: 'project', symbol: '000962' } })
      default: throw new Error(path)
    }
  }))
  function ChangeProject() {
    const { selectProject } = useProject()
    return <button onClick={() => void selectProject('beta')}>Switch project</button>
  }
  const user = userEvent.setup()
  render(<ProjectProvider><ChangeProject /><ChanReplay {...props} /></ProjectProvider>)
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Project snapshot' }), 'alpha-bars')
  await user.click(screen.getByRole('button', { name: 'Recognize structures' }))
  const pendingSignal = oldSignal
  expect(pendingSignal?.aborted).toBe(false)
  await user.click(screen.getByRole('button', { name: 'Switch project' }))
  await screen.findByRole('option', { name: /^000962/ })
  expect(screen.queryByRole('option', { name: /^000338/ })).toBeNull()
  expect(pendingSignal?.aborted).toBe(true)
  await act(async () => finishOld(new Response(JSON.stringify({ ...demo, input: { ...demo.input, mode: 'project', symbol: '000338' } }))))
  expect(screen.queryByRole('heading', { name: '000338' })).toBeNull()
  await user.selectOptions(screen.getByRole('combobox', { name: 'Project snapshot' }), 'beta-bars')
  await user.click(screen.getByRole('button', { name: 'Recognize structures' }))
  expect(await screen.findByRole('heading', { name: '000962' })).toBeTruthy()
})
