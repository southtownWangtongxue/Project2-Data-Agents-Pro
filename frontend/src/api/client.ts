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
    console.error('[API Error]', error.response?.data || error.message)
    return Promise.reject(error)
  },
)

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
