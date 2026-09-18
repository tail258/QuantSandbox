export interface StrategyConfig {
  name: string
  parameters: Record<string, number>
}
export interface AccountConfig {
  initial_cash: number
  commission_rate: number
  tax_rate: number
  min_commission: number
  slippage_bps: number
  position_size: number
}
export interface RunConfig {
  name: string
  tickers: string[]
  start_date: string
  end_date: string
  source: string
  strategy: StrategyConfig
  account: AccountConfig
}
export interface ParameterSpec {
  key: string
  label: string
  default: number
  min: number
  max: number
  step?: number
}
export interface StrategySpec {
  name: string
  label: string
  description: string
  parameters: ParameterSpec[]
}
export interface DataSource {
  id: string
  name: string
  available: boolean
  synthetic: boolean
  notice?: string
  start_date?: string
  end_date?: string
}
export interface Catalog {
  tickers: { ticker: string; name: string; sector?: string; demo_name?: string }[]
  strategies: StrategySpec[]
  sources: DataSource[]
  defaults: RunConfig
  capabilities: string[]
}
export interface Metrics {
  final_equity?: number
  total_return?: number
  annualized_return?: number
  max_drawdown?: number
  trade_count?: number
  closed_trade_count?: number
  win_rate?: number
  benchmark_return?: number
  excess_return?: number
  sharpe_ratio?: number
  [key: string]: number | null | undefined
}
export interface Position {
  shares: number
  cost_basis: number
  market_value: number
  unrealized_pnl: number
  entry_date?: string
}
export interface EquityPoint {
  date: string
  equity: number
  cash: number
  drawdown?: number
  benchmark?: number
  daily_return?: number
  positions?: Record<string, Position>
}
export interface Bar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  fast_ma?: number
  slow_ma?: number
}
export interface Evidence {
  strategy?: string
  parameters?: Record<string, number>
  close?: number
  indicators?: Record<string, number | null>
  signal?: string
  observed_at?: string
  execution_rule?: string
  [key: string]: unknown
}
export interface Trade {
  date: string
  ticker: string
  action: 'buy' | 'sell'
  shares: number
  price: number
  fee: number
  value?: number
  reason: string
  signal_date: string
  evidence: Evidence
  realized_pnl?: number | null
  round_trip_closed?: boolean
  round_trip_pnl?: number | null
}
export interface Decision {
  date: string
  ticker: string
  action: string
  status: string
  reason: string
  evidence: Evidence
}
export interface ExperimentVariant {
  name?: string
  id?: string
  value?: number
  metrics: Metrics
  delta_return?: number
  [key: string]: unknown
}
export interface Result {
  metrics: Metrics
  series: EquityPoint[]
  bars: Record<string, Bar[]>
  trades: Trade[]
  decisions: Decision[]
  checkpoints?: unknown[]
  assumptions?: string[]
  config?: RunConfig
  baseline?: Metrics
  scenarios?: ExperimentVariant[]
  variants?: ExperimentVariant[]
  parameter?: string
  best_value?: number
  folds?: Record<string, unknown>[]
  replay_verification?: Record<string, unknown>
  [key: string]: unknown
}
export interface Run {
  id: string
  name: string
  status: string
  progress: number
  created_at: string
  updated_at: string
  config: RunConfig
  kind: string
  parent_id: string | null
  branch?: { fork_date?: string }
  result: Result | null
  error?: { code: string; message: string } | null
  synthetic: boolean
  metrics?: Metrics
  manifest?: unknown[]
}
export interface ReplaySession {
  id: string
  run_id: string
  cursor: number
  date: string
  total_steps: number
  revealed: boolean
  revealed_at: string | null
  source: string
  synthetic: boolean
  result: Result
}
export interface Dataset {
  ticker: string
  source: string
  synthetic: boolean
  sha256: string
  rows: number
  start_date: string
  end_date: string
  created_at: string
  version: string
  price_basis: string
  volume_unit: string
  notice?: string
}
export interface Note {
  id: string
  run_id?: string | null
  title: string
  body: string
  created_at: string
  updated_at: string
}
