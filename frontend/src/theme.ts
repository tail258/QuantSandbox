import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'terminal'
export const themeStorageKey = 'quantsandbox.theme'
const listeners = new Set<() => void>()
function readTheme(): Theme {
  try { return localStorage.getItem(themeStorageKey) === 'terminal' ? 'terminal' : 'light' }
  catch { return 'light' }
}
let theme = readTheme()
export const getTheme = () => theme
function applyTheme() {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'terminal' ? '#0B0D0F' : '#06656a')
}
export function setTheme(next: Theme) {
  if (next !== 'light' && next !== 'terminal') return
  try { localStorage.setItem(themeStorageKey, next) } catch { /* Preference works for this session. */ }
  if (next !== theme) {
    theme = next
    applyTheme()
    listeners.forEach(listener => listener())
  } else applyTheme()
}
function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export const useTheme = (): Theme => useSyncExternalStore(subscribe, getTheme, () => 'light')
applyTheme()
if (typeof window !== 'undefined') window.addEventListener('storage', event => {
  if (event.key === themeStorageKey || event.key === null) {
    const next = readTheme()
    if (next !== theme) {
      theme = next
      applyTheme()
      listeners.forEach(listener => listener())
    }
  }
})
