/**
 * DataAgentProvider.ts —— 自定义 Chat Provider(SSE 接入层)
 *
 * 按官方 x-sdk 分层:本文件是「请求协议层」—— fetch SSE + XStream 解析,
 * 事件全量交给 store reducer(领域层),不做 UI 决策。
 * 与 Vue useSSE 的手写 buffer 切分相比:改用官方 XStream(注释行/半包/取消语义内置)。
 */
import { XStream } from '@ant-design/x-sdk'
import type { SSEEvent } from './protocol'

export interface StreamHandlers {
  /** 全量 SSE 事件(已 JSON 解析) */
  onEvent: (ev: SSEEvent) => void
  /** 连接级失败(HTTP 错误/网络中断) */
  onError: (message: string) => void
}

/** 发起一轮 SSE 对话并消费事件流 */
export async function streamChat(
  body: Record<string, unknown>,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let resp: Response
  try {
    const token = localStorage.getItem('token')
    resp = await fetch('/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') return // 用户主动停止:静默
    handlers.onError(`网络错误: ${(e as Error)?.message || '未知'}`)
    return
  }

  if (!resp.ok) {
    if (resp.status === 401) {
      localStorage.removeItem('token')
      if (window.location.pathname !== '/login') window.location.href = '/login'
      return
    }
    handlers.onError(`SSE 连接失败: HTTP ${resp.status}`)
    return
  }
  if (!resp.body) {
    handlers.onError('SSE 连接失败: 响应体为空')
    return
  }

  try {
    // XStream:按 \n\n 切分事件、解析字段行;注释行(: ping)无 data 字段,自然跳过
    for await (const chunk of XStream({ readableStream: resp.body })) {
      const raw = (chunk as { data?: string }).data
      if (!raw) continue
      let ev: SSEEvent
      try {
        ev = JSON.parse(raw)
      } catch {
        continue // 半包/哨兵行:静默跳过
      }
      handlers.onEvent(ev)
    }
  } catch (e) {
    if ((e as Error)?.name !== 'AbortError') {
      handlers.onError(`流读取中断: ${(e as Error)?.message || '未知'}`)
    }
  }
}
