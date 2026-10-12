/**
 * api/client.ts —— fetch 封装(JWT + 统一错误)
 * 与后端 REST 面对齐:auth / chat / config / approve / export / suggestions
 */

const TOKEN_KEY = 'token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

interface RequestOptions {
  method?: string
  body?: unknown
  timeoutMs?: number
}

export async function api<T = any>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = 30000 } = opts
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const resp = await fetch(`/api/v1${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    if (resp.status === 401) {
      setToken(null)
      if (window.location.pathname !== '/login') window.location.href = '/login'
      throw new Error('未登录或登录已过期')
    }
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) {
      const detail = (data as any)?.detail || (data as any)?.message || `HTTP ${resp.status}`
      throw new Error(detail)
    }
    return data as T
  } finally {
    clearTimeout(timer)
  }
}

/** 文件下载(导出 CSV/Excel):Blob 直下 */
export async function apiDownload(path: string, body: unknown, filename: string): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const resp = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`导出失败: HTTP ${resp.status}`)
  const blob = await resp.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}
