// @vitest-environment jsdom
import { useRef } from 'react'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectProvider, useProject, withProject, type Project } from './ProjectContext'

const makeProject = (id: string, name: string): Project => ({
  id,
  name,
  question: name + ' question',
  symbols: ['600519'],
  links: [],
  conclusion: '',
  created_at: '2026-11-01',
  updated_at: '2026-11-01',
})
let projects = [makeProject('alpha', 'Alpha'), makeProject('beta', 'Beta')]
let calls: Array<{ path: string; body: any }> = []
function Consumer() {
  const { activeProject, selectProject, linkRecord } = useProject()
  const captured = useRef<string | null>(null)
  return (
    <>
      <output aria-label="current">{activeProject?.name || 'Independent'}</output>
      <button onClick={() => selectProject('beta')}>Switch Beta</button>
      <button
        onClick={() => {
          captured.current = activeProject?.id || null
        }}
      >
        Capture origin
      </button>
      <button onClick={() => linkRecord('research', 'run-alpha', captured.current)}>
        Save originating analysis
      </button>
    </>
  )
}
beforeEach(() => {
  projects = [makeProject('alpha', 'Alpha'), makeProject('beta', 'Beta')]
  calls = []
  localStorage.clear()
  history.replaceState(null, '', '#finance?run=frozen&project=alpha')
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input, init) => {
      const path = String(input),
        body = init?.body ? JSON.parse(String(init.body)) : null
      calls.push({ path, body })
      let value: unknown
      if (path === '/api/projects') value = { projects }
      else if (path.endsWith('/links')) {
        const id = path.split('/')[3]
        const project = projects.find((p) => p.id === id)!
        value = { ...project, links: [{ ...body, linked_at: '2026-11-01' }] }
      } else value = projects.find((p) => path === '/api/projects/' + p.id)
      return { ok: true, status: 200, text: async () => JSON.stringify(value) }
    }),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
describe('shared project workspace', () => {
  it('honors a deep-linked project and preserves the selected record when changing project', async () => {
    const user = userEvent.setup()
    render(
      <ProjectProvider>
        <Consumer />
      </ProjectProvider>,
    )
    await screen.findByText('Alpha')
    await user.click(screen.getByRole('button', { name: 'Switch Beta' }))
    await screen.findByText('Beta')
    expect(location.hash).toContain('project=beta')
    expect(location.hash).toContain('run=frozen')
    expect(localStorage.getItem('quantsandbox.activeProject')).toBe('beta')
  })
  it('associates an in-flight analysis with its captured project after the user switches', async () => {
    const user = userEvent.setup()
    render(
      <ProjectProvider>
        <Consumer />
      </ProjectProvider>,
    )
    await screen.findByText('Alpha')
    await user.click(screen.getByRole('button', { name: 'Capture origin' }))
    await user.click(screen.getByRole('button', { name: 'Switch Beta' }))
    await screen.findByText('Beta')
    await user.click(screen.getByRole('button', { name: 'Save originating analysis' }))
    await waitFor(() =>
      expect(
        calls.some((c) => c.path === '/api/projects/alpha/links' && c.body?.run_id === 'run-alpha'),
      ).toBe(true),
    )
    expect(screen.getByLabelText('current').textContent).toBe('Beta')
  })
  it('keeps record parameters when constructing contextual navigation', () => {
    expect(withProject('obsidian?kind=research&run=abc', 'alpha')).toBe(
      'obsidian?kind=research&run=abc&project=alpha',
    )
  })
})
