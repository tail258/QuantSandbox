export const chanPage = 'chan'

export const layers = ['merged_bars', 'fractals', 'strokes', 'segments', 'centers'] as const
export type Layer = typeof layers[number]

export type Candle = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type Structure = {
  id: string
  status: 'candidate' | 'confirmed'
  first_seen_date: string
  confirmed_date: string | null
  start_index: number
  end_index: number
  start_date: string
  end_date: string
  high: number
  low: number
}

type Directed = Structure & {
  direction: 'up' | 'down'
  start_price: number
  end_price: number
}

type ByLayer = {
  merged_bars: Structure
  fractals: Structure & { kind: 'top' | 'bottom'; index: number; date: string; price: number }
  strokes: Directed
  segments: Directed & { confirmation_rule?: 'overlap' | 'gap_reversal' | 'first_break' | null }
  centers: Structure & {
    lower: number
    upper: number
    phase: 'forming' | 'active' | 'closed'
    expansion_candidate?: boolean
    previous_range_relation?: 'disjoint_above' | 'disjoint_below' | 'touching' | 'overlapping' | null
  }
}

export type ChanEvent = {
  [K in Layer]: {
    index: number
    date: string
    layer: K
    action: 'created' | 'revised' | 'confirmed' | 'removed'
    structure: ByLayer[K]
  }
}[Layer]

export type Frame = { index: number; date: string; event_start: number; event_end: number }

export type ChanResult = {
  algorithm: string
  frames: Frame[]
  events: ChanEvent[]
}

export type Snapshot = {
  id: string
  symbol: string
  start_date: string
  end_date: string
  row_count: number
  price_basis: 'raw_unadjusted' | 'synthetic'
  source: string
}

export type ChanInput = Omit<Snapshot, 'id'> & {
  mode: 'project' | 'synthetic'
  project_id?: string | null
  snapshot_id: string
  sha256: string
  source_sha256?: string | null
  source_url?: string | null
  fetched_at?: string | null
  coverage?: {
    observed_rows: number
    excluded_suspension_dates: string[]
    missing_session_dates: string[] | null
    unknown_suspension_count: number
    cash_dividend_ex_dates: string[]
    calendar_verified: boolean
  }
}

export type Replay = {
  input: ChanInput
  bars: Candle[]
  result: ChanResult
  evidence: string
  verified?: boolean
}

export function stateAtFrame(events: ChanEvent[], frame: Frame) {
  const live = new Map<string, ChanEvent>()
  for (let i = 0; i < frame.event_end; i++) {
    const event = events[i]
    const key = `${event.layer}:${event.structure.id}`
    if (event.action === 'removed') live.delete(key)
    else live.set(key, event)
  }
  return [...live.values()]
}
