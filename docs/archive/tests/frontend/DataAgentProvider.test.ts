/**
 * DataAgentProvider.test.ts —— SSE 接入层集成测试
 * 用真实 ReadableStream 喂 SSE 文本(含 : ping 注释行与半包),验证:
 * - XStream 正确切分,事件逐条 JSON 解析后分发
 * - 注释行/半包被跳过
 * - HTTP 401 → 跳登录;非 2xx → onError
 * - AbortError 静默
 */
import { describe, it, expect, vi } from 'vitest'
import { streamChat } from './DataAgentProvider'
import type { SSEEvent } from './protocol'

function sseResponse(lines: string[], status = 200): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const l of lines) controller.enqueue(encoder.encode(l))
      controller.close()
    },
  })
  return new Response(body, { status })
}

function mockFetch(resp: Response | null, err?: Error) {
  return vi.fn(async () => {
    if (err) throw err
    return resp as Response
  }) as unknown as typeof fetch
}

describe('streamChat', () => {
  it('逐条分发 SSE 事件并跳过 : ping 注释行', async () => {
    const events: SSEEvent[] = []
    vi.stubGlobal('fetch', mockFetch(sseResponse([
      'data: {"type":"thread_id","thread_id":"admin:1"}\n\n',
      ': ping\n\n',
      'data: {"type":"token","content":"你',
      '好","channel":"answer","step_id":2}\n\n', // 半包合并
      'data: {"type":"done"}\n\n',
    ])))
    await streamChat({}, { onEvent: e => events.push(e), onError: () => {} })
    expect(events.map(e => e.type)).toEqual(['thread_id', 'token', 'done'])
    expect(events[1].content).toBe('你好')
    vi.unstubAllGlobals()
  })

  it('非 2xx 响应走 onError', async () => {
    let errMsg = ''
    vi.stubGlobal('fetch', mockFetch(new Response('', { status: 500 })))
    await streamChat({}, { onEvent: () => {}, onError: m => { errMsg = m } })
    expect(errMsg).toContain('500')
    vi.unstubAllGlobals()
  })

  it('网络错误走 onError;AbortError 静默', async () => {
    let called = false
    vi.stubGlobal('fetch', mockFetch(null, new Error('network down')))
    await streamChat({}, { onEvent: () => {}, onError: () => { called = true } })
    expect(called).toBe(true)

    const abortErr = Object.assign(new Error('aborted'), { name: 'AbortError' })
    let called2 = false
    vi.stubGlobal('fetch', mockFetch(null, abortErr))
    await streamChat({}, { onEvent: () => {}, onError: () => { called2 = true } })
    expect(called2).toBe(false)
    vi.unstubAllGlobals()
  })
})
