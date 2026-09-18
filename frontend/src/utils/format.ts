export const number = (value?: number | null, digits = 2) =>
  value == null || !Number.isFinite(value)
    ? '—'
    : new Intl.NumberFormat('zh-CN', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(value)
export const money = (value?: number | null) => (value == null ? '—' : `¥${number(value)}`)
export const percent = (value?: number | null) =>
  value == null || !Number.isFinite(value) ? '—' : `${value > 0 ? '+' : ''}${number(value)}%`
export const dateLabel = (value?: string) => value?.slice(0, 10).replaceAll('-', '.') || '—'
export const signClass = (value?: number | null) =>
  value == null || value === 0 ? '' : value > 0 ? 'positive' : 'negative'
export const statusLabel = (value: string) =>
  ({
    queued: '等待执行',
    running: '计算中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  })[value] || value
export const strategyLabel = (value?: string) =>
  ({
    sma_cross: '双均线策略',
    ma_cross: '双均线策略',
    dual_ma: '双均线策略',
    mean_reversion: '均值回归',
    momentum: '动量策略',
    buy_and_hold: '买入持有',
  })[value || ''] ||
  value ||
  '策略'
