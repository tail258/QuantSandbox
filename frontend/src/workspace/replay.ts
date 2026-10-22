import { post } from '../api/http'
import type { ReplaySession } from '../types'
import { workspace, selectionToken } from './state'
let operation = 0
export async function startSession() {
  const run = workspace.active
  if (!run) return
  const token = selectionToken,
    version = ++operation
  const session = await post<ReplaySession>(`/runs/${run.id}/sessions`, { cursor: 0 })
  if (token !== selectionToken || version !== operation || workspace.active?.id !== run.id) return
  workspace.session = session
  workspace.cursor = 0
}
async function updateSession(action: string, payload = {}) {
  const session = workspace.session
  if (!session) return
  const token = selectionToken,
    version = ++operation
  const updated = await post<ReplaySession>(`/sessions/${session.id}/${action}`, payload)
  if (token === selectionToken && version === operation && workspace.session?.id === session.id)
    workspace.session = updated
}
export const advanceSession = (steps: number) => updateSession('advance', { steps })
export const revealSession = () => updateSession('reveal')
