import { useSyncExternalStore } from 'react'
import { coreMessages } from './i18n/core'
import { researchMessages } from './i18n/research'
import { simulationMessages } from './i18n/simulation'
import { marketMessages } from './i18n/market'
import { usMessages } from './i18n/us'

export type Locale = 'en' | 'zh'
export const localeStorageKey = 'quantsandbox.locale'
const messages: Record<string, string> = { ...coreMessages, ...researchMessages, ...simulationMessages, ...marketMessages, ...usMessages }
const listeners = new Set<() => void>()
function readLocale(): Locale {
  try { return localStorage.getItem(localeStorageKey) === 'zh' ? 'zh' : 'en' } catch { return 'en' }
}
let locale: Locale = readLocale()
export const getLocale = () => locale
export const numberLocale = () => locale === 'zh' ? 'zh-CN' : 'en-US'
function updateDocument() {
  if (typeof document === 'undefined') return
  document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
  document.title = locale === 'zh' ? 'QuantSandbox · 投资分析工作台' : 'QuantSandbox · Investment Research Workbench'
}
export function setLocale(next: Locale) {
  if (next !== 'en' && next !== 'zh') return
  try { localStorage.setItem(localeStorageKey, next) } catch { /* Session switching also works without storage. */ }
  if (next !== locale) {
    locale = next
    updateDocument()
    listeners.forEach(listener => listener())
  } else updateDocument()
}
function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export function useLocale(): Locale {
  return useSyncExternalStore(subscribe, getLocale, () => 'en')
}
/** Translate interface copy only; never pass user text or archived evidence here. */
export function t(source: string, values?: Record<string, string | number>): string {
  // HTTP errors retain their source text in state so an existing notice can switch language.
  const requestFailure = /^请求失败（(\d+)），请确认后端已启动。$/.exec(source)
  if (requestFailure) return t('请求失败（{status}），请确认后端已启动。', {status: requestFailure[1]})
  const translated = locale === 'en' ? messages[source] ?? source : source
  return translated.replace(/\{(\w+)\}/g, (match, key: string) => values?.[key] === undefined ? match : String(values[key]))
}
updateDocument()
if (typeof window !== 'undefined') {
  window.addEventListener('storage', event => {
    if (event.key === localeStorageKey || event.key === null) {
      const next = readLocale()
      if (next !== locale) {
        locale = next
        updateDocument()
        listeners.forEach(listener => listener())
      }
    }
  })
}
