import { workspace } from './state'
let toastTimer: ReturnType<typeof setTimeout> | undefined
export const clearNotification = () => {
  clearTimeout(toastTimer)
  workspace.toast = ''
}
export const notify = (message: string) => {
  clearNotification()
  workspace.toast = message
  toastTimer = setTimeout(clearNotification, 4500)
}
