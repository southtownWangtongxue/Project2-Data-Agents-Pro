import { ref } from 'vue'

/* SSE 事件回调接口 */
export interface SSEEventCallbacks {
  /* 状态更新：如"正在分析..." */
  onStatus?: (content: string) => void
  /* Schema 信息 */
  onSchema?: (content: string) => void
  /* 自然语言文本（分析/回答） */
  onText?: (content: string) => void
  /* 流式 Token 输出（逐字渲染） */
  onToken?: (content: string) => void
  /* Agent 推理/思考过程（阶段状态） */
  onThinking?: (agent: string, phase: string, content: string) => void
  /* 模型思考内容增量（Phase 4：与正文 token 类型化隔离，折叠展示） */
  onReasoning?: (content: string) => void
  /* 工具调用事件 */
  onToolCall?: (toolName: string, meta: Record<string, unknown>) => void
  /* 工具调用结果 */
  onToolResult?: (toolName: string, meta: Record<string, unknown>) => void
  /* 生成的 SQL 语句 */
  onSQL?: (content: string) => void
  /* 查询结果数据 */
  onResult?: (data: any[], columns: string[]) => void
  /* 数据分析洞察 */
  onAnalysis?: (content: string) => void
  /* ECharts 图表配置 */
  onChart?: (config: Record<string, unknown>) => void
  /* 错误信息（含错误码 + 可重试标识） */
  onError?: (error: string, code?: string, recoverable?: boolean) => void
  /* 流正常结束 */
  onDone?: () => void
  /* 高危 SQL 需要审批 */
  onApprovalRequired?: (threadId: string, question: string, sql: string, reason: string) => void
  /* 会话 thread_id（流开始时推送） */
  onThreadId?: (threadId: string) => void
  /* Clarifier 意图确认追问 */
  onClarification?: (content: string, options: string[], clarifyId: string) => void
  /* Planner 执行计划 */
  onPlan?: (intent: string, intentLabel: string, steps: string[], chartSuitable: boolean) => void
  /* 会话标题（SSE 实时推送，无需额外 HTTP 请求） */
  onTitle?: (threadId: string, title: string, nodeIndex: number) => void
  /* 节点开始：实时通知前端管道进度（节点开始而非完成） */
  onNodeStarted?: (agent: string, label: string) => void
}

/* SSE 事件数据格式（后端推送的 JSON 结构） */
interface SSEEventData {
  type: string
  content?: string
  data?: any[]
  columns?: string[]
  config?: Record<string, unknown>
  error?: string
  /* approval_required 事件专用字段 */
  thread_id?: string
  question?: string
  sql?: string
  reason?: string
  /* thinking 事件专用字段 */
  agent?: string
  phase?: string
  /* tool_call / tool_result 事件专用字段 */
  tool_name?: string
  name?: string        // 新协议字段（DeepAgent 通用任务模式）
  args?: string        // tool_call 新增：工具参数
  status?: string      // tool_result 新增：执行状态
  /* error 增强字段 */
  code?: string
  recoverable?: boolean
  /* clarification 追问事件专用字段 */
  text?: string
  options?: string[]
  clarify_id?: string
  /* plan 执行计划事件专用字段 */
  intent?: string
  intent_label?: string
  steps?: string[]
  chart_suitable?: boolean
  /* title 标题事件专用字段 */
  node_index?: number
  /* node_started 事件专用字段 */
  label?: string
}

/**
 * SSE 流式接收 Composable
 * 使用 fetch + ReadableStream 方式读取后端推送的 SSE 事件流
 */
export function useSSE() {
  /* 是否正在连接 */
  const connecting = ref(false)

  /* AbortController 用于取消请求 */
  let abortController: AbortController | null = null

  /* 防止 SSE done 事件与 finally 块重复调用 onDone
   * （提升到 useSSE 作用域，供 dispatchEvent 访问） */
  let doneReceived = false

  /**
   * 建立 SSE 连接并持续读取流数据
   * @param url - SSE 接口地址
   * @param body - 请求体（JSON 对象）
   * @param callbacks - 事件回调集合
   */
  async function connect(
    url: string,
    body: object,
    callbacks: SSEEventCallbacks,
  ): Promise<void> {
    // 中止上一次连接
    disconnect()

    connecting.value = true
    abortController = new AbortController()
    let hasError = false
    doneReceived = false  // 每次连接重置

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      const token = localStorage.getItem('token')
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: abortController.signal,
      })

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('token')
          if (window.location.pathname !== '/login') {
            window.location.href = '/login'
          }
          return
        }
        throw new Error(`SSE 连接失败: HTTP ${response.status}`)
      }
      if (!response.body) {
        throw new Error('SSE 连接失败: 响应体为空')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      // 持续读取流数据
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // 将新数据追加到缓冲区
        buffer += decoder.decode(value, { stream: true })

        // 按行分割，最后一行可能不完整，保留在 buffer 中
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          // 跳过空行和 SSE 注释行
          if (!trimmed || trimmed.startsWith(':')) continue

          // 解析 "data: {...}" 格式
          if (trimmed.startsWith('data: ')) {
            let jsonStr = trimmed.slice(6).trim()
            if (!jsonStr) continue
            // 去除可能混入的尾随控制字符（如 NUL）；trim() 只能清除空白，无法清除控制字符
            jsonStr = Array.from(jsonStr).filter((ch) => ch.charCodeAt(0) >= 32).join('')
            if (!jsonStr) continue

            try {
              const event: SSEEventData = JSON.parse(jsonStr)
              dispatchEvent(event, callbacks)
            } catch {
              // done 等哨兵事件（或控制字符导致）解析失败时不告警，避免噪声
              if (!/type["']?\s*:\s*["']?done/.test(jsonStr)) {
                console.warn('[SSE] JSON 解析失败:', jsonStr)
              }
            }
          }
        }
      }
    } catch (error: unknown) {
      // 用户主动取消（AbortError），不视为错误
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      hasError = true
      const errMsg =
        error instanceof Error ? error.message : '未知网络错误'
      callbacks.onError?.(errMsg, 'NETWORK_ERROR', false)
    } finally {
      connecting.value = false
      // 只有非错误、非取消、且未通过 done 事件触发过的情况才调用 onDone
      if (!hasError && !doneReceived && abortController && !abortController.signal.aborted) {
        callbacks.onDone?.()
      }
      abortController = null
    }
  }

  /**
   * 根据 SSE 事件 type 分发到对应的回调函数
   */
  function dispatchEvent(
    event: SSEEventData,
    callbacks: SSEEventCallbacks,
  ): void {
    switch (event.type) {
      case 'status':
        callbacks.onStatus?.(event.content || '')
        break
      case 'schema':
        callbacks.onSchema?.(event.content || '')
        break
      case 'token':
        callbacks.onToken?.(event.content || '')
        break
      case 'thinking':
        callbacks.onThinking?.(
          event.agent || '',
          event.phase || '',
          event.content || '',
        )
        break
      case 'reasoning':
        callbacks.onReasoning?.(event.content || '')
        break
      case 'tool_call': {
        // 兼容新旧协议: tool_name(旧) / name(新 DeepAgent)
        const toolName = event.name || event.tool_name || ''
        const meta: Record<string, unknown> = {}
        if (event.sql) meta.sql = (event.sql as string).slice(0, 200)
        if (event.args) meta.args = event.args  // 新协议：工具参数
        if (event.content) meta.info = event.content
        if (event.agent) meta.agent = event.agent
        if (event.phase) meta.phase = event.phase
        callbacks.onToolCall?.(toolName, meta)
        break
      }
      case 'tool_result': {
        const toolName = event.name || event.tool_name || ''
        const meta: Record<string, unknown> = {}
        if (event.content) meta.result = (event.content as string).slice(0, 200)
        if (event.status) meta.status = event.status  // 新协议：执行状态
        callbacks.onToolResult?.(toolName, meta)
        break
      }
      case 'sql':
        callbacks.onSQL?.(event.content || '')
        break
      case 'text':
        callbacks.onText?.(event.content || '')
        break
      case 'result':
        callbacks.onResult?.(event.data || [], event.columns || [])
        break
      case 'error':
        callbacks.onError?.(
          event.error || event.content || '未知错误',
          event.code,
          event.recoverable,
        )
        break
      case 'done':
        doneReceived = true
        callbacks.onDone?.()
        break
      case 'analysis':
        callbacks.onAnalysis?.(event.content || '')
        break
      case 'chart':
        callbacks.onChart?.(event.config || {})
        break
      case 'approval_required':
        callbacks.onApprovalRequired?.(
          event.thread_id || '',
          event.question || '',
          event.sql || '',
          event.reason || '',
        )
        break
      case 'thread_id':
        callbacks.onThreadId?.(event.thread_id || '')
        break
      case 'clarification':
        callbacks.onClarification?.(
          event.text || event.content || '',
          event.options || [],
          event.clarify_id || '',
        )
        break
      case 'plan':
        callbacks.onPlan?.(
          event.intent || '',
          event.intent_label || '',
          event.steps || [],
          event.chart_suitable || false,
        )
        break
      case 'title':
        callbacks.onTitle?.(
          event.thread_id || '',
          event.content || '',
          event.node_index || 0,
        )
        break
      case 'node_started':
        callbacks.onNodeStarted?.(event.agent || '', event.label || event.agent || '')
        break
      default:
        console.warn('[SSE] 未知事件类型:', event.type)
    }
  }

  /**
   * 断开 SSE 连接（取消正在进行的请求）
   */
  function disconnect(): void {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    connecting.value = false
  }

  return {
    connecting,
    connect,
    disconnect,
  }
}
