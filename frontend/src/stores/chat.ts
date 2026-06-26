import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useSSE } from '@/composables/useSSE'
import { useApprovalStore } from '@/stores/approval'
import apiClient from '@/api/client'
import { downloadFile } from '@/api/client'

/* 消息类型定义 */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  type?: 'text' | 'sql' | 'result' | 'chart' | 'analysis' | 'status' | 'error' | 'thinking' | 'tool_call' | 'tool_result' | 'clarification' | 'plan'
  content?: string
  sql?: string
  data?: any[]
  columns?: string[]
  chartConfig?: Record<string, unknown>
  /* thinking 卡片字段 */
  agent?: string
  phase?: string
  /* tool 卡片字段 */
  toolName?: string
  toolMeta?: Record<string, unknown>
  /* 错误重试 */
  errorCode?: string
  recoverable?: boolean
  /* thinking 折叠状态 */
  collapsed?: boolean
  /* clarification 追问字段 */
  clarifyOptions?: string[]
  /* plan 执行计划字段 */
  planIntent?: string
  planIntentLabel?: string
  planSteps?: string[]
  planChartSuitable?: boolean
}

/* 会话摘要类型 */
export interface SessionInfo {
  thread_id: string
  title: string
  question: string
  created_at: string
  message_count: number
}

/* 生成唯一消息 ID */
function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 9)
}

/* 聊天状态管理 Store */
export const useChatStore = defineStore('chat', () => {
  /* SSE 连接管理 */
  const { connect: sseConnect, disconnect: sseDisconnect } = useSSE()

  /* 消息列表 */
  const messages = ref<ChatMessage[]>([])

  /* 是否正在加载（等待后端响应） */
  const isLoading = ref(false)

  /* 最后发送的问题（用于重试） */
  const lastQuestion = ref('')

  /* 当前会话 thread_id（SSE 流返回后设置） */
  const currentThreadId = ref('')

  /* 当前正在流式更新的 token 消息 ID */
  let activeTokenMsgId: string | null = null

  /* 最后一个助手文本消息 ID（用于流式光标动画） */
  const lastAssistantMsgId = ref('')

  /* 当前活跃的 Agent（用于去重：某些 Agent 的 token 流不显示为独立文本） */
  let currentAgent: string | null = null

  /* 会话列表 */
  const sessions = ref<SessionInfo[]>([])

  /* 会话列表加载状态 */
  const sessionsLoading = ref(false)

  /* 动态问题建议（基于表结构） */
  const suggestions = ref<string[]>([])
  const suggestionsLoading = ref(false)

  /* 多轮对话：轮次信息（用于 NodeSeparator 和快捷跳转） */
  interface TurnInfo { index: number; title: string; question: string }
  const turns = ref<TurnInfo[]>([])
  const currentTurnIndex = ref(0)

  /* 任务清单（替代旧的水平管道） */
  interface TaskItem {
    key: string
    label: string
    status: 'pending' | 'running' | 'completed'
    startedAt?: number
  }
  const tasks = ref<TaskItem[]>([])
  const tasksCollapsed = ref(false)
  const pipelinePhaseMap: Record<string, string> = {
    clarify_plan: '意图分析',
    clarifier: '意图分析',
    planner: '生成计划',
    misc_agent: '处理请求',
    schema_agent: '加载表结构',
    sql_coder: '生成SQL',
    security: '安全审核',
    execute_sql: '执行查询',
    chart_direct: '加载缓存',
    quality_gate: '质量评估',
    analyst: '数据分析',
    reporter: '生成图表',
    answer: '生成回答',
    rag_agent: '知识检索',
    finish: '完成',
  }

  function initTasks() {
    tasks.value = []
    tasksCollapsed.value = false
  }

  function updateTask(key: string, label: string) {
    const displayLabel = label || pipelinePhaseMap[key] || key
    const existing = tasks.value.find(t => t.key === key)
    if (existing) {
      existing.status = 'completed'
    } else {
      // 标记之前所有任务为完成，添加新任务
      tasks.value.forEach(t => { if (t.status === 'running') t.status = 'completed' })
      tasks.value.push({ key, label: displayLabel, status: 'running', startedAt: Date.now() })
    }
  }

  function completeAllTasks() {
    tasks.value.forEach(t => { t.status = 'completed' })
    // 自动折叠：2 秒后收起
    setTimeout(() => { tasksCollapsed.value = true }, 2000)
  }

  /* 发送消息：添加用户消息 -> 调用 SSE -> 处理各类事件 -> 添加对应消息 */
  async function sendMessage(text: string) {
    if (!text.trim() || isLoading.value) return

    lastQuestion.value = text.trim()

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      type: 'text',
      content: text.trim(),
    }
    messages.value.push(userMsg)

    isLoading.value = true
    initTasks()  // 重置任务清单

    // 构建完整对话历史发送给后端（支持多轮追问）
    const chatMessages = messages.value
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content || '' }))

    // 调用 SSE 流式接口
    await sseConnect(
      '/api/v1/chat/completions',
      {
        messages: [...chatMessages, { role: 'user', content: text.trim() }],
        stream: true,
        // 多轮对话：复用当前会话的 thread_id
        thread_id: currentThreadId.value || undefined,
      },
      {
        /* SSE 流返回当前会话 thread_id */
        onThreadId(threadId: string) {
          currentThreadId.value = threadId
        },

        /* 节点开始：实时更新管道进度（在节点实际开始时触发，非完成后） */
        onNodeStarted(agent: string, label: string) {
          const labelText = label || pipelinePhaseMap[agent] || agent
          updateTask(agent, labelText)
        },

        /* Clarifier 追问：意图不够明确，展示追问卡片 */
        onClarification(content: string, options: string[], _clarifyId: string) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'system',
            type: 'clarification',
            content,
            clarifyOptions: options,
          })
        },

        /* Planner 执行计划 */
        onPlan(intent: string, intentLabel: string, steps: string[], chartSuitable: boolean) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'system',
            type: 'plan',
            planIntent: intent,
            planIntentLabel: intentLabel,
            planSteps: steps,
            planChartSuitable: chartSuitable,
          })
        },

        /* 状态更新：如"正在分析..." */
        onStatus(content: string) {
          messages.value.push({
            id: generateId(),
            role: 'system',
            type: 'status',
            content,
          })
        },

        /* Schema 信息 */
        onSchema(_content: string) {
          // 表结构信息已在 status 消息中体现，此处不再额外展示
        },

        /* 节点开始 —— 实时更新管道进度（在节点真正开始时触发） */
        onNodeStarted(agent: string, label: string) {
          updatePipeline(agent, label)
        },

        /* Agent 推理过程 → 更新流水线进度 + 设置活跃 Agent 上下文 */
        onThinking(agent: string, phase: string, content: string) {
          activeTokenMsgId = null
          currentAgent = agent  // 追踪当前活跃的 Agent（用于去重）
          const label = pipelinePhaseMap[agent] || content || agent
          updateTask(agent, label)
          // 仅保留有实质性内容的思考卡片（如 quality_gate 的评估反馈）
          if (content && content.length > 30) {
            messages.value.push({
              id: generateId(),
              role: 'system',
              type: 'thinking',
              agent,
              phase,
              content,
              collapsed: false,
            })
          }
        },

        /* 流式 Token 输出 —— 智能去重：sql_coder/rag_agent 的 token 不显示为独立文本 */
        onToken(content: string) {
          // sql_coder / rag_agent 的 token 流由格式化卡片展示，不重复渲染为文本
          if (currentAgent === 'sql_coder' || currentAgent === 'rag_agent') {
            return
          }
          // analyst / misc_agent 的 token 正常流式输出（Markdown 逐字渲染）
          if (activeTokenMsgId) {
            const msg = messages.value.find(m => m.id === activeTokenMsgId)
            if (msg) {
              msg.content = (msg.content || '') + content
            }
          } else {
            activeTokenMsgId = generateId()
            lastAssistantMsgId.value = activeTokenMsgId
            messages.value.push({
              id: activeTokenMsgId,
              role: 'assistant',
              type: 'text',
              content: content,
            })
          }
        },

        /* 工具调用 —— 紧凑型卡片（无内容预览，纯管道指示器） */
        onToolCall(toolName: string, meta: Record<string, unknown>) {
          activeTokenMsgId = null
          // 过滤出有用字段（去重后的简单预览）
          const cleanMeta: Record<string, unknown> = {}
          for (const [k, v] of Object.entries(meta)) {
            if (v !== undefined && v !== null && v !== '' && k !== 'sql' && k !== 'sql_preview') {
              cleanMeta[k] = v
            }
          }
          messages.value.push({
            id: generateId(),
            role: 'system',
            type: 'tool_call',
            toolName,
            toolMeta: Object.keys(cleanMeta).length ? cleanMeta : undefined,
            collapsed: true,
          })
        },

        /* 工具调用结果 —— 紧凑型卡片 */
        onToolResult(toolName: string, meta: Record<string, unknown>) {
          // 清理当前 Agent 上下文
          if (toolName === 'sql_coder' || toolName === 'analyst' || toolName === 'rag_agent') {
            currentAgent = null
          }
          const cleanMeta: Record<string, unknown> = {}
          for (const [k, v] of Object.entries(meta)) {
            if (v !== undefined && v !== null && v !== '' && k !== 'sql_preview') {
              cleanMeta[k] = v
            }
          }
          messages.value.push({
            id: generateId(),
            role: 'system',
            type: 'tool_result',
            toolName,
            toolMeta: Object.keys(cleanMeta).length ? cleanMeta : undefined,
            collapsed: true,
          })
        },

        /* 自然语言文本（分析/回答） */
        onText(content: string) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'assistant',
            type: 'text',
            content: content,
          })
        },

        /* 生成的 SQL 语句 */
        onSQL(content: string) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'assistant',
            type: 'sql',
            sql: content,
          })
        },

        /* 查询结果数据 */
        onResult(data: any[], columns: string[]) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'assistant',
            type: 'result',
            data,
            columns,
          })
        },

        /* 错误信息（含错误码） */
        onError(error: string, code?: string, recoverable?: boolean) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'assistant',
            type: 'error',
            content: error,
            errorCode: code,
            recoverable: recoverable ?? false,
          })
          isLoading.value = false
        },

        /* 数据分析洞察 */
        onAnalysis(content: string) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'assistant',
            type: 'analysis',
            content,
          })
        },

        /* ECharts 图表配置 */
        onChart(config: Record<string, unknown>) {
          activeTokenMsgId = null
          messages.value.push({
            id: generateId(),
            role: 'assistant',
            type: 'chart',
            chartConfig: config,
          })
        },

        /* 高危 SQL 需要审批 */
        onApprovalRequired(threadId: string, question: string, sql: string, reason: string) {
          activeTokenMsgId = null
          const approvalStore = useApprovalStore()
          approvalStore.addTask({ threadId, question, sql, reason })
        },

        /* 会话标题（SSE 实时推送） */
        onTitle(threadId: string, title: string, _nodeIndex: number) {
          if (!title) return
          // 直接更新本地会话列表中的标题（无需额外 HTTP 请求）
          const session = sessions.value.find(s => s.thread_id === threadId)
          if (session) {
            session.title = title
          } else {
            // 新建会话：会话尚未在列表中，直接插入
            sessions.value.unshift({
              thread_id: threadId,
              title,
              question: lastQuestion.value,
              created_at: new Date().toISOString(),
              message_count: 0,
            })
          }
        },

        /* 流结束 */
        onDone() {
          activeTokenMsgId = null
          isLoading.value = false
          // 标记所有任务为已完成，2 秒后自动折叠
          completeAllTasks()
          // 记录当前轮次（多轮对话用）
          currentTurnIndex.value = turns.value.length
          // 刷新会话列表 + 加载节点信息
          loadSessions()
          if (currentThreadId.value) {
            loadSessionNodes()
          }
        },
      },
    )
  }

  /* 重试最后一条消息 */
  async function retryLastMessage() {
    if (!lastQuestion.value) return
    // 移除最后一条用户消息和之后的所有消息
    const idx = messages.value.findLastIndex(
      m => m.role === 'user' && m.content === lastQuestion.value,
    )
    if (idx >= 0) {
      messages.value.splice(idx)
    }
    await sendMessage(lastQuestion.value)
  }

  /* 清空消息列表并断开连接 */
  function clearMessages() {
    sseDisconnect()
    messages.value = []
    isLoading.value = false
    activeTokenMsgId = null
    lastQuestion.value = ''
    currentThreadId.value = ''
    turns.value = []
    currentTurnIndex.value = 0
    tasks.value = []
    tasksCollapsed.value = false
  }

  /* 新建会话：清空当前对话 */
  function newSession() {
    clearMessages()
  }

  /* 中止当前生成 */
  function stopGeneration() {
    sseDisconnect()
    activeTokenMsgId = null
    isLoading.value = false
  }

  /* 加载当前会话的节点信息（用于多轮对话导航） */
  async function loadSessionNodes() {
    if (!currentThreadId.value) return
    try {
      const data = await apiClient.get(`/chat/sessions/${currentThreadId.value}`) as {
        nodes: { index: number; title: string; question: string }[]
      }
      if (data.nodes && data.nodes.length > 0) {
        turns.value = data.nodes.map(n => ({
          index: n.index,
          title: n.title || `第${n.index + 1}轮`,
          question: n.question || '',
        }))
      }
    } catch {
      // 静默失败，不影响主流程
    }
  }

  /* 加载会话列表 */
  async function loadSessions() {
    sessionsLoading.value = true
    try {
      const data = await apiClient.get('/chat/sessions')
      sessions.value = data as SessionInfo[]
    } catch {
      sessions.value = []
    } finally {
      sessionsLoading.value = false
    }
  }

  /* 加载历史会话消息 —— 加载所有轮次，全部显示 */
  async function loadSession(threadId: string) {
    isLoading.value = true
    try {
      const data = await apiClient.get(`/chat/sessions/${threadId}`) as {
        thread_id: string
        title: string
        nodes: { index: number; title: string; question: string }[]
        messages: ChatMessage[]
      }
      currentThreadId.value = threadId
      // 恢复轮次信息
      if (data.nodes && data.nodes.length > 0) {
        turns.value = data.nodes.map(n => ({
          index: n.index,
          title: n.title || `第${n.index + 1}轮`,
          question: n.question || '',
        }))
        currentTurnIndex.value = data.nodes.length - 1
      }
      // 确保每条消息有唯一 ID，并限制结果数据量防止内存卡顿
      const restored = (data.messages || []).map((msg: ChatMessage) => {
        const m: ChatMessage = { ...msg, id: generateId() }
        // 历史会话的查询结果最多保留 50 行，减轻 Vue 响应式开销
        if (m.type === 'result' && m.data && m.data.length > 50) {
          m.data = m.data.slice(0, 50)
        }
        return m
      })
      messages.value = restored
    } catch (err) {
      console.error('[chat] 加载历史会话失败:', err)
    } finally {
      isLoading.value = false
    }
  }

  /* 更新会话标题（Phase E.4） */
  async function editSessionTitle(threadId: string, newTitle: string) {
    try {
      await apiClient.patch(`/chat/sessions/${threadId}`, { title: newTitle })
      const session = sessions.value.find(s => s.thread_id === threadId)
      if (session) {
        session.title = newTitle
      }
    } catch (err) {
      console.error('[chat] 更新标题失败:', err)
    }
  }

  /* 删除会话 */
  async function deleteSession(threadId: string) {
    try {
      await apiClient.delete(`/chat/sessions/${threadId}`)
      sessions.value = sessions.value.filter(s => s.thread_id !== threadId)
    } catch {
      console.error('[chat] 删除会话失败:', threadId)
    }
  }

  /* 导出数据为 CSV 或 Excel */
  async function exportData(data: any[], columns: string[], format: 'csv' | 'excel') {
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-')
    try {
      await downloadFile(
        `/export/${format}`,
        { data, columns, format, filename: `data-export-${timestamp}` },
        `data-export-${timestamp}.${format === 'excel' ? 'xlsx' : 'csv'}`,
      )
    } catch (err) {
      console.error(`[chat] ${format} 导出失败:`, err)
    }
  }

  /* 加载基于表结构的动态问题建议 */
  async function loadSuggestions(forceRefresh = false) {
    if (suggestionsLoading.value) return
    suggestionsLoading.value = true
    try {
      const params = forceRefresh ? '?force_refresh=true' : ''
      const data = await apiClient.get(`/chat/suggestions${params}`, { timeout: 8000 }) as { questions: string[]; cached: boolean }
      if (data.questions && data.questions.length > 0) {
        suggestions.value = data.questions
      }
    } catch (err) {
      console.warn('[chat] 加载问题建议失败，使用默认模板:', err)
      // 使用硬编码的兜底建议
      if (!suggestions.value || suggestions.value.length === 0) {
        suggestions.value = [
          '统计各表的数据量',
          '查看数据库中所有的表',
          '帮我分析数据库整体概况',
        ]
      }
    } finally {
      suggestionsLoading.value = false
    }
  }

  return {
    messages,
    isLoading,
    currentThreadId,
    sessions,
    sessionsLoading,
    suggestions,
    suggestionsLoading,
    turns,
    currentTurnIndex,
    tasks,
    tasksCollapsed,
    lastAssistantMsgId,
    sendMessage,
    retryLastMessage,
    clearMessages,
    newSession,
    stopGeneration,
    loadSessions,
    loadSession,
    loadSessionNodes,
    editSessionTitle,
    deleteSession,
    exportData,
    loadSuggestions,
  }
})
