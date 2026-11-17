import type { Candle, ChanEvent, Layer } from '../chan/model'
import type { DecisionLevel } from './DecisionChart'
import type { TrackedFactor } from './TrackedFactors'

export type Condition = { field: 'close' | 'volume' | 'low'; comparison: 'gt' | 'lt' | 'gte' | 'lte'; value: number }
export type Scenario = {
  kind: 'breakout' | 'retest' | 'support_failure' | 'otherwise'
  action: 'review_entry_after_close' | 'review_exit_if_holding' | 'watch'
  conditions: Condition[]
  evidence_roles: DecisionLevel['role'][]
}
export type Plan = {
  rule_version: string; structure_version: string; as_of: string; observation_session: string | null
  data_quality: 'limited' | 'checked'; data_issues: string[]; watch_reason: string
  trend: string; phase: string; level_basis: string | null
  last_center: { id: string; relation: string; phase: string; lower: number; upper: number; confirmed_date: string; used_for_levels: boolean } | null
  volume: { window: number; observed_ratio: number | null; reference: number | null; minimum: number | null }
  levels: DecisionLevel[]; scenarios: Scenario[]
}
export type DecisionInput = {
  id: string; sha256: string; source: string; source_url: string; fetched_at: string
  volume_unit: 'shares' | 'units'; start_date: string | null; end_date: string | null
  last_observed_session: string; expected_session: string | null; historical: boolean
  calendar_source: string; calendar_source_url: string; missing_sessions: string[]; suspended_sessions: string[]; reference_breaks: string[]
}
type Structures = Partial<Record<Layer, (ChanEvent['structure'] & { confirmed_index: number | null; first_seen_index: number })[]>>
export type WeeklyContext = {
  status: 'ready' | 'insufficient' | 'unavailable'; trend: string
  completed_through: string | null; scheduled_completion: string | null
  skipped_weeks: { week_start: string; scheduled_completion: string | null; reason: string }[]
}
export type DecisionSeries = { bars: Candle[]; structures: Structures }
export type CenterObservation = {
  id: string; side: 'above' | 'below'; edge: number; outside_extreme: number
  first_exit_date: string; geometry_date: string; available_date: string; available_index: number
  status: 'intact' | 'reentered' | 'unverifiable'; status_date: string
  center: { lower: number; upper: number; confirmed_date: string }
  departure: { confirmed_date: string }; retest: { confirmed_date: string }
}
export type DecisionResponse = {
  symbol: string; project_id: string | null; status: 'empty' | 'ready' | 'no_active_bars'; warning: string | null
  instrument: { name: string; exchange: string; kind: 'stock' | 'etf'; symbol: string } | null
  input: DecisionInput | null; bars: Candle[]; plan: Plan | null
  weekly: (DecisionSeries & { context: WeeklyContext }) | null
  factors: TrackedFactor[]
  structure_observations: CenterObservation[]
} & DecisionSeries

export function chartEvents(data: DecisionSeries): ChanEvent[] {
  return (Object.entries(data.structures) as [Layer, NonNullable<Structures[Layer]>][])
    .flatMap(([layer, values]) => values.map(structure => ({ layer, structure,
      index: structure.confirmed_index ?? structure.first_seen_index,
      date: structure.confirmed_date ?? structure.first_seen_date,
      action: structure.status === 'confirmed' ? 'confirmed' : 'created',
    } as ChanEvent)))
}
