import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'

/* 创建 axios 实例 */
const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/* 请求拦截器：自动附加 JWT Token */
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)

/* 响应拦截器：401 自动跳转登录页 */
client.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      // 防止重复跳转
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    console.error('[API Error]', getApiErrorMessage(error, error.message))
    return Promise.reject(error)
  },
)

/**
 * 从 axios 错误中提取可展示的提示文案。
 *
 * 后端错误体形如 `{"detail": "需要管理员权限"}`（或 422 的 detail 数组），
 * 直接把对象塞进 ElMessage / console 会显示成 `[object Object]`，
 * 排查与提示都不可用。这里统一归一化：
 *   1. detail 为字符串 → 直接返回（如「需要管理员权限」）
 *   2. detail 为数组（参数校验）→ 取首条 msg
 *   3. detail 为对象 → 取 msg / message 字段
 *   4. 均无 → 返回 fallback（调用方传入，如「加载失败」）
 */
export function getApiErrorMessage(error: unknown, fallback = '请求失败'): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data
  if (typeof data === 'string' && data) return data
  if (data && typeof data === 'object') {
    const detail = (data as Record<string, unknown>).detail
    if (typeof detail === 'string' && detail) return detail
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as Record<string, unknown> | string
      if (typeof first === 'string') return first
      const msg = (first as Record<string, unknown>)?.msg
      if (typeof msg === 'string' && msg) return msg
    }
    if (detail && typeof detail === 'object') {
      const msg = (detail as Record<string, unknown>).msg ?? (detail as Record<string, unknown>).message
      if (typeof msg === 'string' && msg) return msg
    }
  }
  const message = (error as { message?: string })?.message
  return typeof message === 'string' && message ? message : fallback
}

/* 响应拦截器已在运行时解包 response.data，
 * 此处重写类型让 get/post/put/patch/delete 返回 data 而非 AxiosResponse，
 * 避免调用方访问 .documents/.providers 等字段时产生 TS2339 误报。 */
interface DataApiClient {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  patch<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T>
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T>
}

export default client as unknown as DataApiClient

/**
 * 文件下载工具函数
 * 用于导出功能的文件下载（CSV / Excel 等）
 *
 * @param url - 接口地址（相对路径）
 * @param body - 请求体（JSON 序列化）
 * @param filename - 下载文件名
 */
export async function downloadFile(url: string, body: object, filename: string): Promise<void> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(`/api/v1${url}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    throw new Error(`下载失败: HTTP ${response.status}`)
  }

  const blob = await response.blob()
  const downloadUrl = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = downloadUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(downloadUrl)
}
