import {numberLocale} from './i18n'

/** Source precision for new quotes; preserve up to eight decimals in older caches. */
export function quotePrice(quote: {price?: unknown; price_decimals?: unknown}): string {
  const value = quote.price
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  const precision = quote.price_decimals
  const known = typeof precision === 'number' && Number.isInteger(precision) && precision >= 0 && precision <= 20
  return value.toLocaleString(numberLocale(), {
    minimumFractionDigits: known ? precision : 0,
    maximumFractionDigits: known ? precision : 8,
  })
}
