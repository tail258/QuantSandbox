// @vitest-environment jsdom
import { useState } from 'react'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { getLocale, localeStorageKey, setLocale, t } from './i18n'
import { getTheme, setTheme, themeStorageKey } from './theme'

vi.mock('./pages/Projects', () => ({ default: function Draft() {
  const [value, setValue] = useState('')
  return <input aria-label="Research draft" value={value} onChange={e => setValue(e.target.value)} />
} }))
beforeEach(() => {
  localStorage.clear()
  setLocale('en')
  setTheme('light')
  localStorage.removeItem(localeStorageKey)
  location.hash = '#projects'
  vi.stubGlobal('scrollTo', vi.fn())
  vi.stubGlobal('fetch', vi.fn(async (input) => {
    const body = String(input) === '/api/projects' ? { projects: [] } : { datasets: [], series: [], templates: {}, metrics: {} }
    return { ok: true, text: async () => JSON.stringify(body), json: async () => body }
  }))
})
afterEach(() => {
  cleanup()
  setLocale('en')
  setTheme('light')
  localStorage.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
describe('workbench language preference', () => {
  it('starts in English and switches live without losing a research draft', async () => {
    const user = userEvent.setup()
    render(<App />)
    const input = await screen.findByRole('textbox', {name: 'Research draft'})
    await user.type(input, '橡胶研究 draft')
    expect(document.documentElement.lang).toBe('en')
    expect(document.title).toBe('QuantSandbox · Investment Research Workbench')
    expect(screen.getByRole('navigation', {name: 'Main navigation'})).toBeTruthy()
    await user.selectOptions(screen.getByRole('combobox', {name: 'Language / 语言'}), 'zh')
    expect(screen.getByRole('navigation', {name: '主导航'})).toBeTruthy()
    expect(document.documentElement.lang).toBe('zh-CN')
    expect(localStorage.getItem(localeStorageKey)).toBe('zh')
    expect((input as HTMLInputElement).value).toBe('橡胶研究 draft')
    await user.selectOptions(screen.getByRole('combobox', {name: 'Language / 语言'}), 'en')
    expect(screen.getByRole('navigation', {name: 'Main navigation'})).toBeTruthy()
    expect((input as HTMLInputElement).value).toBe('橡胶研究 draft')
  })
  it('keeps the selected language when the app remounts', async () => {
    setLocale('zh')
    const first = render(<App />)
    await screen.findByRole('textbox', {name: 'Research draft'})
    first.unmount()
    render(<App />)
    expect((screen.getByRole('combobox', {name: 'Language / 语言'}) as HTMLSelectElement).value).toBe('zh')
    expect(screen.getByRole('navigation', {name: '主导航'})).toBeTruthy()
  })
  it('syncs another tab and falls back to English for invalid or cleared preferences', async () => {
    render(<App />)
    await screen.findByRole('textbox', {name: 'Research draft'})
    act(() => {
      localStorage.setItem(localeStorageKey, 'zh')
      window.dispatchEvent(new StorageEvent('storage', {key: localeStorageKey}))
    })
    expect(screen.getByRole('navigation', {name: '主导航'})).toBeTruthy()
    act(() => {
      localStorage.setItem(localeStorageKey, 'unsupported')
      window.dispatchEvent(new StorageEvent('storage', {key: localeStorageKey}))
    })
    await waitFor(() => expect(getLocale()).toBe('en'))
    expect(document.documentElement.lang).toBe('en')
    act(() => {
      setLocale('zh')
      localStorage.clear()
      window.dispatchEvent(new StorageEvent('storage', {key: null}))
    })
    expect(getLocale()).toBe('en')
  })
  it('interpolates complete phrases and preserves unmatched source content', () => {
    expect(t('正在打开{page}…', {page: 'Projects'})).toBe('Opening Projects…')
    expect(t('海南橡胶研究原文')).toBe('海南橡胶研究原文')
    setLocale('zh')
    expect(t('正在打开{page}…', {page: '研究项目'})).toBe('正在打开研究项目…')
  })
  it('switches themes independently of language without resetting the current draft', async () => {
    const user = userEvent.setup()
    const view = render(<App />)
    const input = await screen.findByRole('textbox', {name: 'Research draft'})
    await user.type(input, 'Theme QA 研究')
    expect(document.documentElement.dataset.theme).toBe('light')
    await user.selectOptions(screen.getByRole('combobox', {name: 'Appearance'}), 'terminal')
    expect(document.documentElement.dataset.theme).toBe('terminal')
    expect(localStorage.getItem(themeStorageKey)).toBe('terminal')
    expect((input as HTMLInputElement).value).toBe('Theme QA 研究')
    await user.selectOptions(screen.getByRole('combobox', {name: 'Language / 语言'}), 'zh')
    expect((screen.getByRole('combobox', {name: '界面主题'}) as HTMLSelectElement).value).toBe('terminal')
    expect((input as HTMLInputElement).value).toBe('Theme QA 研究')
    view.unmount()
    render(<App />)
    expect((screen.getByRole('combobox', {name: '界面主题'}) as HTMLSelectElement).value).toBe('terminal')
    await user.selectOptions(screen.getByRole('combobox', {name: '界面主题'}), 'light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.lang).toBe('zh-CN')
  })
  it('syncs theme changes from another tab and recovers from an unsupported preference', () => {
    render(<App />)
    act(() => {
      localStorage.setItem(themeStorageKey, 'terminal')
      window.dispatchEvent(new StorageEvent('storage', {key: themeStorageKey}))
    })
    expect(document.documentElement.dataset.theme).toBe('terminal')
    act(() => {
      localStorage.setItem(themeStorageKey, 'unsupported')
      window.dispatchEvent(new StorageEvent('storage', {key: themeStorageKey}))
    })
    expect(getTheme()).toBe('light')
  })
  it('translates an already-visible transport error after language changes', () => {
    const error = '请求失败（503），请确认后端已启动。'
    expect(t(error)).toBe('Request failed (503). Check that the backend is running.')
    setLocale('zh')
    expect(t(error)).toBe(error)
  })
  it('allows session switching when browser storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => setLocale('zh')).not.toThrow()
    expect(getLocale()).toBe('zh')
    expect(t('重试')).toBe('重试')
  })
})
