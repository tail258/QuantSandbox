import { reactive } from 'vue'
import type { Catalog, ReplaySession, Run, RunSummary } from '../types'
export const workspace = reactive({
  catalog: null as Catalog | null,
  runs: [] as RunSummary[],
  active: null as Run | null,
  session: null as ReplaySession | null,
  initialized: false,
  loading: false,
  error: '',
  busy: false,
  createOpen: false,
  toast: '',
  cursor: 0,
})
export let selectionToken = 0
export const nextSelection = () => ++selectionToken
