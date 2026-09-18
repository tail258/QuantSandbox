export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 30000)
  try {
    const response = await fetch(`/api${path}`, {
      ...init,
      signal: init.signal || controller.signal,
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
    const text = await response.text()
    let body: any
    try {
      body = text ? JSON.parse(text) : null
    } catch {
      body = null
    }
    if (!response.ok) {
      const detail = body?.detail
      const message =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((item: any) => `${item.loc?.slice(1).join('.')}：${item.msg}`).join('；')
            : body?.error || body?.message
      throw new ApiError(
        message || `请求失败（${response.status}），请确认后端已启动。`,
        response.status,
      )
    }
    if (!body) throw new ApiError('服务未返回有效数据，请检查后端连接。', response.status)
    return body as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(
      error instanceof DOMException && error.name === 'AbortError'
        ? '请求超时，请稍后重试。'
        : '无法连接研究服务，请确认后端服务已启动。',
      0,
    )
  } finally {
    window.clearTimeout(timeout)
  }
}

export const post = <T>(path: string, payload: unknown = {}) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(payload) })
export const patch = <T>(path: string, payload: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(payload) })

export async function download(path: string, filename: string) {
  const response = await fetch(`/api${path}`)
  if (!response.ok) throw new Error('导出失败，请稍后重试。')
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
