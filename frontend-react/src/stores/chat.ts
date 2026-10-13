/**
 * stores/chat.ts —— 对话领域状态(zustand)
 *
 * 移植 Vue chat.ts 的已修复语义:按 stepId 分槽的流式正文(并行节点不串写)、
 * 步骤分组、channel=sql 流式 SQL 卡片、thinkingMode 前端开关、排队发送、
 * 多轮 thread_id 复用、/cancel 停止。
 * 事件分发全部走 sdk/reducer(纯函数,有单测覆盖);本文件只负责任务编排与网络。
 */
import { create } from 'zustand'
import { api, apiDownload } from '@/api/client'
import {
  applyEvent,
  initialChatState,
  resolveApproval,
  type ChatState,
} from '@/sdk/reducer'
import { streamChat } from '@/sdk/DataAgentProvider'
import { E, type Msg, type SSEEvent } from '@/sdk/protocol'

/* ── 会话摘要 ── */
export interface SessionInfo {
  thread_id: string
  title: string
  question: string
  created_at: string
  message_count: number
}

interface PerfInfo {
  durationMs: number
  firstTokenMs: number
  tokens: number
  tokPerSec: number | null
  llmMs: number
  toolMs: number
  inputTokens: number
}

interface ChatStore {
  /* 领域状态 */
  chat: ChatState
  isLoading: boolean
  sessions: SessionInfo[]
  sessionsLoading: boolean
  turns: { index: number; title: string; question: string }[]
  currentTurnIndex: number
  lastPerf: PerfInfo | null
  contextUsage: { estimatedTokens: number; window: number }
  suggestions: string[]
  suggestionsLoading: boolean
  /* 输入区状态 */
  mode: string
  webSearch: boolean
  model: string
  /* thinking_mode:当前模型是否开启思考展示(关→仅隐藏,不丢弃) */
  thinkingModeEnabled: boolean
  /* 消息反馈(like/dislike);后端暂无上报端点,仅本地会话内生效 */
  feedbacks: Record<string, 'like' | 'dislike'>
  /* 排队(运行中再发送则入队) */
  pendingQueue: { text: string; mode: string; webSearch: boolean }[]

  /* actions */
  sendMessage: (text: string, mode?: string, webSearch?: boolean, model?: string) => Promise<void>
  cancelGeneration: () => void
  retryLastMessage: () => Promise<void>
  loadSessions: () => Promise<void>
  loadSession: (threadId: string) => Promise<void>
  deleteSession: (threadId: string) => Promise<void>
  editSessionTitle: (threadId: string, title: string) => Promise<void>
  setMode: (m: string) => void
  setWebSearch: (v: boolean) => void
  setModel: (m: string) => void
  setFeedback: (msgId: string, value: 'like' | 'dislike' | 'default') => void
  resolveApprovalMsg: (msgId: string, state: 'approved' | 'rejected', comment: string) => Promise<void>
  exportData: (data: any[], columns: string[], format: 'csv' | 'excel') => Promise<void>
  loadSuggestions: (force?: boolean) => Promise<void>
  clearMessages: () => void
  newSession: () => void
}

const STORAGE_MODEL_KEY = 'selectedModelId'
const abortRef: { current: AbortController | null } = { current: null }

export const useChatStore = create<ChatStore>((set, get) => {
  /** 拉取一轮 SSE 并在事件流上驱动 reducer */
  const runStream = async (question: string, mode: string, webSearch: boolean, model: string | undefined, threadId: string) => {
    const state = get()
    // 构建对话历史(SQL/结果消息转摘要,与 Vue 端一致)
    const history = state.chat.messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => {
        if (m.kind === 'sql' && m.sql) return { role: m.role, content: `[上轮生成的SQL]: ${m.sql}` }
        if (m.kind === 'result' && m.data) {
          const cols = (m.columns || []).join(', ')
          return { role: m.role, content: `[查询结果]: ${m.data.length} 条, 列: ${cols}` }
        }
        return { role: m.role, content: m.content || '' }
      })

    const streamStart = Date.now()
    let firstTokenTime: number | null = null
    let tokenCount = 0
    let estimatedChars = 0
    let toolMsAccum = 0
    let toolWindowStart: number | null = null

    const finalizePerf = () => {
      if (toolWindowStart !== null) {
        toolMsAccum += Date.now() - toolWindowStart
        toolWindowStart = null
      }
      const durationMs = Date.now() - streamStart
      const firstTokenMs = firstTokenTime !== null ? firstTokenTime - streamStart : durationMs
      const generateMs = firstTokenTime !== null ? Date.now() - firstTokenTime : 1
      const tokPerSec = generateMs >= 1000 ? Math.round((tokenCount / generateMs) * 1000) : null
      set({
        lastPerf: {
          durationMs,
          firstTokenMs,
          tokens: tokenCount,
          tokPerSec,
          llmMs: Math.max(generateMs - toolMsAccum, 0),
          toolMs: toolMsAccum,
          inputTokens: history.reduce((sum, m) => sum + Math.ceil((m.content || '').length / 3), 0),
        },
      })
      set(s => ({ contextUsage: { ...s.contextUsage, estimatedTokens: s.contextUsage.estimatedTokens + Math.ceil(estimatedChars / 3) } }))
    }

    const onEvent = (ev: SSEEvent) => {
      const s = get()
      if (ev.type === E.TITLE) {
        if (ev.thread_id && ev.content) {
          set({
            sessions: s.sessions.map(x =>
              x.thread_id === ev.thread_id ? { ...x, title: ev.content! } : x,
            ),
          })
        }
        return
      }
      if (ev.type === E.TOKEN) {
        tokenCount += 1
        estimatedChars += (ev.content || '').length
        if (firstTokenTime === null) firstTokenTime = Date.now()
      }
      if (ev.type === E.TOOL_CALL && toolWindowStart === null) toolWindowStart = Date.now()
      if (ev.type === E.TOOL_RESULT && toolWindowStart !== null) {
        toolMsAccum += Date.now() - toolWindowStart
        toolWindowStart = null
      }
      if (ev.type === E.THREAD_ID && ev.thread_id) set({ chat: { ...s.chat, threadId: ev.thread_id } })
      set(st => ({ chat: applyEvent(st.chat, ev) }))
      if (ev.type === E.DONE) {
        finalizePerf()
        set({ isLoading: false })
        get().loadSessions()
      }
    }

    set({ isLoading: true })
    await streamChat(
      {
        messages: [...history, { role: 'user', content: question }],
        stream: true,
        mode,
        web_search: webSearch,
        model,
        thread_id: threadId || undefined,
      },
      { onEvent, onError: msg => {
        set(st => ({ chat: applyEvent(st.chat, { type: E.ERROR, error: msg, recoverable: true }) }))
        set({ isLoading: false })
        finalizePerf()
      } },
      abortRef.current?.signal,
    )
    // 流自然结束(异常路径)兜底解锁
    if (get().isLoading) {
      set({ isLoading: false })
      finalizePerf()
    }
  }

  return {
    chat: initialChatState(),
    isLoading: false,
    sessions: [],
    sessionsLoading: false,
    turns: [],
    currentTurnIndex: 0,
    lastPerf: null,
    contextUsage: { estimatedTokens: 0, window: 131072 },
    suggestions: [],
    suggestionsLoading: false,
    mode: 'data',
    webSearch: false,
    model: localStorage.getItem(STORAGE_MODEL_KEY) || '',
    thinkingModeEnabled: true,
    feedbacks: {},
    pendingQueue: [],

    sendMessage: async (text, mode = get().mode, webSearch = get().webSearch, model = get().model) => {
      if (!text.trim()) return
      if (get().isLoading) {
        set(s => ({ pendingQueue: [...s.pendingQueue, { text: text.trim(), mode, webSearch }] }))
        return
      }
      set(s => ({
        chat: {
          ...s.chat,
          messages: [...s.chat.messages, { id: `u_${Date.now().toString(36)}`, role: 'user', kind: 'text', content: text.trim() }],
        },
      }))
      const threadId = get().chat.threadId
      abortRef.current = new AbortController()
      await runStream(text.trim(), mode, webSearch, model || undefined, threadId)
      // 排队 flush
      const q = get().pendingQueue
      if (q.length) {
        const [next, ...rest] = q
        set({ pendingQueue: rest })
        await get().sendMessage(next.text, next.mode, next.webSearch)
      }
    },

    cancelGeneration: () => {
      const threadId = get().chat.threadId
      if (threadId) {
        api('/chat/cancel', { method: 'POST', body: { thread_id: threadId } }).catch(() => {})
      }
      abortRef.current?.abort()
      abortRef.current = null
      set({ isLoading: false })
    },

    retryLastMessage: async () => {
      const last = [...get().chat.messages].reverse().find(m => m.role === 'user')
      if (!last?.content) return
      // 移除该用户消息及其后的全部消息
      set(s => {
        const idx = s.chat.messages.findIndex(m => m.id === last.id)
        return { chat: { ...s.chat, messages: idx >= 0 ? s.chat.messages.slice(0, idx) : s.chat.messages } }
      })
      await get().sendMessage(last.content)
    },

    loadSessions: async () => {
      set({ sessionsLoading: true })
      try {
        const data = await api<SessionInfo[]>('/chat/sessions')
        set({ sessions: data })
      } catch {
        set({ sessions: [] })
      } finally {
        set({ sessionsLoading: false })
      }
    },

    loadSession: async (threadId) => {
      set({ isLoading: true })
      try {
        const data = await api<{ nodes: { index: number; title: string; question: string }[]; messages: any[] }>(
          `/chat/sessions/${encodeURIComponent(threadId)}`,
        )
        set(s => ({
          chat: { ...initialChatState(), threadId },
          turns: (data.nodes || []).map(n => ({ index: n.index, title: n.title || `第${n.index + 1}轮`, question: n.question || '' })),
          currentTurnIndex: Math.max(0, (data.nodes || []).length - 1),
        }))
        // 历史消息(后端投影)映射为领域 Msg
        const mapped: Msg[] = (data.messages || []).map((m: any) => ({
          id: `h_${Math.random().toString(36).slice(2, 9)}`,
          role: m.role === 'user' ? 'user' : 'assistant',
          kind: (m.type === 'sql' || m.type === 'result' || m.type === 'chart' || m.type === 'error' ? m.type : 'text') as Msg['kind'],
          content: m.content,
          sql: m.sql,
          data: m.data,
          columns: m.columns,
          chartConfig: m.chartConfig,
        }))
        set(s => ({ chat: { ...s.chat, messages: mapped } }))
      } catch (e) {
        console.error('[chat] 加载历史会话失败:', e)
      } finally {
        set({ isLoading: false })
      }
    },

    deleteSession: async (threadId) => {
      await api(`/chat/sessions/${encodeURIComponent(threadId)}`, { method: 'DELETE' }).catch(() => {})
      set(s => ({ sessions: s.sessions.filter(x => x.thread_id !== threadId) }))
      if (get().chat.threadId === threadId) get().newSession()
    },

    editSessionTitle: async (threadId, title) => {
      await api(`/chat/sessions/${encodeURIComponent(threadId)}`, { method: 'PATCH', body: { title } }).catch(() => {})
      set(s => ({ sessions: s.sessions.map(x => (x.thread_id === threadId ? { ...x, title } : x)) }))
    },

    setMode: m => set({ mode: m }),
    setWebSearch: v => set({ webSearch: v }),
    setFeedback: (msgId, value) =>
      set(s => {
        const next = { ...s.feedbacks }
        if (value === 'default') delete next[msgId]
        else next[msgId] = value
        return { feedbacks: next }
      }),
    setModel: m => {
      localStorage.setItem(STORAGE_MODEL_KEY, m)
      set({ model: m })
    },

    resolveApprovalMsg: async (msgId, state, comment) => {
      const msg = get().chat.messages.find(m => m.id === msgId)
      if (!msg?.approval) return
      try {
        await api('/chat/approve', {
          method: 'POST',
          body: { task_id: msg.approval.threadId, action: state === 'approved' ? 'approve' : 'reject', comment },
        })
        set(s => ({ chat: resolveApproval(s.chat, msgId, state, comment) }))
      } catch (e) {
        // 审批失败(如非管理员/权限不足)必须让用户知道,不能静默
        console.error('[chat] 审批提交失败:', e)
        throw e
      }
    },

    exportData: async (data, columns, format) => {
      const ts = new Date().toISOString().slice(0, 19).replace(/:/g, '-')
      await apiDownload(`/export/${format}`, { data, columns, format, filename: `data-export-${ts}` }, `data-export-${ts}.${format === 'excel' ? 'xlsx' : 'csv'}`)
    },

    loadSuggestions: async (force = false) => {
      if (get().suggestionsLoading) return
      set({ suggestionsLoading: true })
      try {
        const qs = new URLSearchParams()
        if (force) qs.set('force_refresh', 'true')
        if (get().model) qs.set('model', get().model)
        const data = await api<{ questions: string[] }>(`/chat/suggestions${qs.toString() ? `?${qs}` : ''}`, { timeoutMs: 8000 })
        if (data.questions?.length) set({ suggestions: data.questions })
      } catch {
        set({ suggestions: ['统计各表的数据量', '查看数据库中所有的表', '帮我分析数据库整体概况'] })
      } finally {
        set({ suggestionsLoading: false })
      }
    },

    clearMessages: () => {
      abortRef.current?.abort()
      abortRef.current = null
      set({ chat: initialChatState(), isLoading: false, pendingQueue: [], turns: [], currentTurnIndex: 0, feedbacks: {} })
    },

    newSession: () => get().clearMessages(),
  }
})
