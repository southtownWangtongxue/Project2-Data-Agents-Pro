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
import { mapProjectedMessages } from '@/sdk/history'
import { streamChat } from '@/sdk/DataAgentProvider'
import { E, type Msg, type SSEEvent } from '@/sdk/protocol'

/* ── 会话摘要 ── */
export interface SessionInfo {
  thread_id: string
  title: string
  question: string
  created_at: string
  message_count: number
  /* 归档标记（后端 chat_sessions.archived，2026-10 会话管理） */
  archived?: boolean
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

/* ── Token 用量与上下文构成（usage SSE 事件，读数条三弹窗数据源）── */
export interface UsageInfo {
  inputTokens: number
  outputTokens: number
  cachedTokens: number
  uncachedInputTokens: number
  totalTokens: number
  cacheHitRatio: number
  estimated: boolean
  context: { systemPrompt: number; toolDefs: number; messages: number; window: number; usedPct: number }
}

/* ── 会话级统计（读数条「会话统计」弹窗：轮次/步数/耗时/TTFT/TPS）── */
export interface SessionStats {
  turns: number
  steps: number
  totalMs: number
  llmMs: number
  toolMs: number
  /* TTFT/TPS 采样（每轮流结束累加一次，弹窗取均值） */
  ttftSumMs: number
  ttftCount: number
  tpsSum: number
  tpsCount: number
}

const initialSessionStats = (): SessionStats => ({
  turns: 0,
  steps: 0,
  totalMs: 0,
  llmMs: 0,
  toolMs: 0,
  ttftSumMs: 0,
  ttftCount: 0,
  tpsSum: 0,
  tpsCount: 0,
})

interface ChatStore {
  /* 领域状态 */
  chat: ChatState
  isLoading: boolean
  /* 是否正在流式生成(与 isLoading 区分:后者也用于历史加载,不能当作"思考中") */
  isGenerating: boolean
  sessions: SessionInfo[]
  sessionsLoading: boolean
  /* 会话列表分页(滚动加载) */
  sessionsHasMore: boolean
  sessionsLoadingMore: boolean
  turns: { index: number; title: string; question: string }[]
  currentTurnIndex: number
  lastPerf: PerfInfo | null
  contextUsage: { estimatedTokens: number; window: number }
  /* Token 用量(usage SSE 事件，读数条「Token 用量」「上下文已用」弹窗) */
  usage: UsageInfo | null
  /* 会话级统计(读数条「会话统计」弹窗，逐轮累加) */
  sessionStats: SessionStats
  suggestions: string[]
  suggestionsLoading: boolean
  /* 输入区状态 */
  mode: string
  webSearch: boolean
  model: string
  /* thinking:用户思考模式偏好(默认关,localStorage 持久化)——
     关=隐藏思考/推理展示且请求尽力禁用模型推理;开=展示并允许推理 */
  thinking: boolean
  /* thinkingCapable:当前模型是否具备思考能力(provider 配置派生,
     不支持时前端开关禁用);与用户偏好 thinking 解耦 */
  thinkingCapable: boolean
  /* 消息反馈(like/dislike);后端暂无上报端点,仅本地会话内生效 */
  feedbacks: Record<string, 'like' | 'dislike'>
  /* 排队(运行中再发送则入队) */
  pendingQueue: { text: string; mode: string; webSearch: boolean }[]

  /* actions */
  sendMessage: (text: string, mode?: string, webSearch?: boolean, model?: string) => Promise<void>
  cancelGeneration: () => void
  retryLastMessage: () => Promise<void>
  loadSessions: () => Promise<void>
  loadMoreSessions: () => Promise<void>
  loadSession: (threadId: string) => Promise<void>
  deleteSession: (threadId: string) => Promise<void>
  editSessionTitle: (threadId: string, title: string) => Promise<void>
  batchDeleteSessions: (threadIds: string[]) => Promise<{ deleted: number; failed: number; error?: string }>
  /** 设置上下文窗口(读数条「上下文已用」分母;模型选择器/配置中心联动) */
  setContextWindow: (window: number) => void
  /** 切换查看的轮次(多轮对话节点切换) */
  setTurnIndex: (index: number) => void
  setMode: (m: string) => void
  setWebSearch: (v: boolean) => void
  setModel: (m: string) => void
  setThinking: (v: boolean) => void
  setFeedback: (msgId: string, value: 'like' | 'dislike' | 'default') => void
  resolveApprovalMsg: (msgId: string, state: 'approved' | 'rejected' | 'edited', comment: string, editedSql?: string) => Promise<void>
  exportData: (data: any[], columns: string[], format: 'csv' | 'excel') => Promise<void>
  loadSuggestions: (force?: boolean) => Promise<void>
  clearMessages: () => void
  newSession: () => void
}

const STORAGE_MODEL_KEY = 'selectedModelId'
const STORAGE_THINKING_KEY = 'thinkingMode'
/** 会话列表分页每页条数（与后端 list_sessions limit 上限对齐） */
const SESSIONS_PAGE_SIZE = 30
const abortRef: { current: AbortController | null } = { current: null }

export const useChatStore = create<ChatStore>((set, get) => {
  /** 拉取一轮 SSE 并在事件流上驱动 reducer */
  const runStream = async (question: string, mode: string, webSearch: boolean, model: string | undefined, threadId: string, thinking: boolean = get().thinking) => {
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
      const llmMs = Math.max(generateMs - toolMsAccum, 0)
      set({
        lastPerf: {
          durationMs,
          firstTokenMs,
          tokens: tokenCount,
          tokPerSec,
          llmMs,
          toolMs: toolMsAccum,
          inputTokens: history.reduce((sum, m) => sum + Math.ceil((m.content || '').length / 3), 0),
        },
      })
      set(s => ({ contextUsage: { ...s.contextUsage, estimatedTokens: s.contextUsage.estimatedTokens + Math.ceil(estimatedChars / 3) } }))
      /* 会话级统计累加（「会话统计」弹窗取均值展示） */
      set(s => ({
        sessionStats: {
          ...s.sessionStats,
          totalMs: s.sessionStats.totalMs + durationMs,
          llmMs: s.sessionStats.llmMs + llmMs,
          toolMs: s.sessionStats.toolMs + toolMsAccum,
          ttftSumMs: s.sessionStats.ttftSumMs + firstTokenMs,
          ttftCount: s.sessionStats.ttftCount + 1,
          tpsSum: tokPerSec !== null ? s.sessionStats.tpsSum + tokPerSec : s.sessionStats.tpsSum,
          tpsCount: tokPerSec !== null ? s.sessionStats.tpsCount + 1 : s.sessionStats.tpsCount,
        },
      }))
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
      /* usage：计量数据非消息，store 层消费（reducer 不感知），done 前到达。
         后端事件为扁平结构（type + input_tokens/... + context），协议只增不改 */
      if (ev.type === E.USAGE && typeof ev.total_tokens === 'number') {
        const u = ev
        set(st => ({
          usage: {
            inputTokens: u.input_tokens || 0,
            outputTokens: u.output_tokens || 0,
            cachedTokens: u.cached_tokens || 0,
            uncachedInputTokens: u.uncached_input_tokens || 0,
            totalTokens: u.total_tokens || 0,
            cacheHitRatio: u.cache_hit_ratio || 0,
            estimated: u.estimated ?? true,
            context: {
              systemPrompt: u.context?.system_prompt || 0,
              toolDefs: u.context?.tool_defs || 0,
              messages: u.context?.messages || 0,
              window: u.context?.window || 0,
              usedPct: u.context?.used_pct || 0,
            },
          },
          /* turns 为会话累计（后端 node_index+1），steps 为本轮步数（累加） */
          sessionStats: {
            ...st.sessionStats,
            turns: Math.max(st.sessionStats.turns, (u as { turns?: number }).turns || 0),
            steps: st.sessionStats.steps + ((u as { steps?: number }).steps || 0),
          },
          /* 上下文占用口径升级：服务端三段估算取代前端 chars/3 */
          contextUsage: {
            estimatedTokens:
              (u.context?.system_prompt || 0) + (u.context?.tool_defs || 0) + (u.context?.messages || 0),
            window: u.context?.window || st.contextUsage.window,
          },
        }))
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
        set({ isLoading: false, isGenerating: false })
        get().loadSessions()
      }
    }

    set({ isLoading: true, isGenerating: true })
    await streamChat(
      {
        messages: [...history, { role: 'user', content: question }],
        stream: true,
        mode,
        web_search: webSearch,
        thinking,
        model,
        thread_id: threadId || undefined,
      },
      { onEvent, onError: msg => {
        set(st => ({ chat: applyEvent(st.chat, { type: E.ERROR, error: msg, recoverable: true }) }))
        set({ isLoading: false, isGenerating: false })
        finalizePerf()
      } },
      abortRef.current?.signal,
    )
    // 流自然结束(异常路径)兜底解锁
    if (get().isLoading) {
      set({ isLoading: false, isGenerating: false })
      finalizePerf()
    }
  }

  return {
    chat: initialChatState(),
    isLoading: false,
    isGenerating: false,
    sessions: [],
    sessionsLoading: false,
    sessionsHasMore: false,
    sessionsLoadingMore: false,
    turns: [],
    currentTurnIndex: 0,
    lastPerf: null,
    contextUsage: { estimatedTokens: 0, window: 192000 },
    usage: null,
    sessionStats: initialSessionStats(),
    suggestions: [],
    suggestionsLoading: false,
    mode: 'data',
    webSearch: false,
    model: localStorage.getItem(STORAGE_MODEL_KEY) || '',
    /* 思考模式:用户偏好,默认关(需求:设计为开关而不是默认开启) */
    thinking: localStorage.getItem(STORAGE_THINKING_KEY) === 'true',
    thinkingCapable: true,
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
      await runStream(text.trim(), mode, webSearch, model || undefined, threadId, get().thinking)
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
      set({ isLoading: false, isGenerating: false })
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
        const data = await api<SessionInfo[]>(`/chat/sessions?limit=${SESSIONS_PAGE_SIZE}&offset=0`)
        set({
          sessions: data,
          sessionsHasMore: data.length >= SESSIONS_PAGE_SIZE,
        })
      } catch {
        /* 已知瞬态:页面重载时请求可能被 abort 导致空列表——首屏失败自动重试一次 */
        if (get().sessions.length === 0) {
          await new Promise(r => setTimeout(r, 800))
          try {
            const retry = await api<SessionInfo[]>(`/chat/sessions?limit=${SESSIONS_PAGE_SIZE}&offset=0`)
            set({
              sessions: retry,
              sessionsHasMore: retry.length >= SESSIONS_PAGE_SIZE,
            })
          } catch {
            set({ sessions: [], sessionsHasMore: false })
          }
        } else {
          set({ sessionsHasMore: false })
        }
      } finally {
        set({ sessionsLoading: false })
      }
    },

    loadMoreSessions: async () => {
      const { sessionsLoadingMore, sessionsHasMore, sessions } = get()
      if (sessionsLoadingMore || !sessionsHasMore) return
      set({ sessionsLoadingMore: true })
      try {
        const data = await api<SessionInfo[]>(
          `/chat/sessions?limit=${SESSIONS_PAGE_SIZE}&offset=${sessions.length}`,
        )
        set(s => ({
          sessions: [...s.sessions, ...data],
          sessionsHasMore: data.length >= SESSIONS_PAGE_SIZE,
        }))
      } catch {
        /* 加载更多失败静默(保留已加载列表),下次滚动触底重试 */
      } finally {
        set({ sessionsLoadingMore: false })
      }
    },


    loadSession: async (threadId) => {
      set({ isLoading: true })
      try {
        const data = await api<{
          nodes: { index: number; title: string; question: string }[]
          messages: any[]
          usage?: {
            input_tokens?: number
            output_tokens?: number
            cached_tokens?: number
            uncached_input_tokens?: number
            total_tokens?: number
            cache_hit_ratio?: number
            estimated?: boolean
            context?: { system_prompt: number; tool_defs: number; messages: number; window: number; used_pct: number }
          } | null
        }>(`/chat/sessions/${encodeURIComponent(threadId)}`)
        const turns = (data.nodes || []).map(n => ({
          index: n.index,
          title: n.title || `第${n.index + 1}轮`,
          question: n.question || '',
        }))
        /* 历史会话的用量/上下文(2026-10-18):后端按投影消息 + provider 窗口
           现场估算并返回 usage —— 否则切换会话时三弹窗全部变成"—" */
        const u = data.usage
        set(s => ({
          chat: { ...initialChatState(), threadId },
          turns,
          currentTurnIndex: Math.max(0, turns.length - 1),
          usage: u && typeof u.total_tokens === 'number'
            ? {
                inputTokens: u.input_tokens || 0,
                outputTokens: u.output_tokens || 0,
                cachedTokens: u.cached_tokens || 0,
                uncachedInputTokens: u.uncached_input_tokens || 0,
                totalTokens: u.total_tokens || 0,
                cacheHitRatio: u.cache_hit_ratio || 0,
                estimated: u.estimated ?? true,
                context: {
                  systemPrompt: u.context?.system_prompt || 0,
                  toolDefs: u.context?.tool_defs || 0,
                  messages: u.context?.messages || 0,
                  window: u.context?.window || s.contextUsage.window,
                  usedPct: u.context?.used_pct || 0,
                },
              }
            : null,
          sessionStats: {
            ...initialSessionStats(),
            turns: turns.length,
            steps: (data.messages || []).filter((m: any) => m?.type === 'tool_chain' || m?.type === 'tool').length,
          },
          contextUsage: u?.context
            ? {
                estimatedTokens:
                  (u.context.system_prompt || 0) + (u.context.tool_defs || 0) + (u.context.messages || 0),
                window: u.context.window || s.contextUsage.window,
              }
            : s.contextUsage,
        }))
        /* 历史消息(后端投影)映射为领域 Msg:tool_chain→工具卡、thinking/reasoning→
           思考卡(2026-10 修复:此前未映射导致重启后工具步骤丢失/思考内容不存在) */
        const mapped: Msg[] = mapProjectedMessages(data.messages)
        set(s => ({ chat: { ...s.chat, messages: mapped } }))
      } catch (e) {
        console.error('[chat] 加载历史会话失败:', e)
      } finally {
        set({ isLoading: false })
      }
    },

    deleteSession: async (threadId) => {
      /* 失败必须可见(向上抛给 UI 汇报):此前 .catch 吞错导致「界面消失、刷新复现」 */
      await api(`/chat/sessions/${encodeURIComponent(threadId)}`, { method: 'DELETE' })
      set(s => ({ sessions: s.sessions.filter(x => x.thread_id !== threadId) }))
      if (get().chat.threadId === threadId) get().newSession()
    },

    batchDeleteSessions: async (threadIds) => {
      if (threadIds.length === 0) return { deleted: 0, failed: 0 }
      /* 并行删除(典型量级 <100):部分失败不静默,收集后由 UI 汇报 */
      const results = await Promise.allSettled(
        threadIds.map(id => api(`/chat/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })),
      )
      const okIds = threadIds.filter((_, i) => results[i].status === 'fulfilled')
      const failed = threadIds.length - okIds.length
      const firstError = results.find(r => r.status === 'rejected') as PromiseRejectedResult | undefined
      const error = firstError ? String((firstError.reason as Error)?.message || firstError.reason) : undefined
      if (okIds.length > 0) {
        set(s => ({ sessions: s.sessions.filter(x => !okIds.includes(x.thread_id)) }))
        /* 当前会话被批量删除 → 回到新会话 */
        if (okIds.includes(get().chat.threadId)) get().newSession()
      }
      if (failed > 0) console.error('[chat] 批量删除部分失败:', failed, '个会话', error)
      return { deleted: okIds.length, failed, error }
    },

    editSessionTitle: async (threadId, title) => {
      await api(`/chat/sessions/${encodeURIComponent(threadId)}`, { method: 'PATCH', body: { title } }).catch(() => {})
      set(s => ({ sessions: s.sessions.map(x => (x.thread_id === threadId ? { ...x, title } : x)) }))
    },

    setContextWindow: window => set(s => {
      /* 分母实时联动:同步重算 usage.context(分子不变,占比随窗口变化) */
      const ctx = s.usage?.context
      if (!ctx) return { contextUsage: { ...s.contextUsage, window } }
      const used = ctx.systemPrompt + ctx.toolDefs + ctx.messages
      return {
        contextUsage: { ...s.contextUsage, window },
        usage: {
          ...s.usage!,
          context: {
            ...ctx,
            window,
            usedPct: Math.min(100, Math.round((used / Math.max(1, window)) * 100)),
          },
        },
      }
    }),

    setTurnIndex: index => set({ currentTurnIndex: index }),

    setMode: m => set({ mode: m }),
    setWebSearch: v => set({ webSearch: v }),
    setThinking: v => {
      localStorage.setItem(STORAGE_THINKING_KEY, String(v))
      set({ thinking: v })
    },
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

    resolveApprovalMsg: async (msgId, state, comment, editedSql) => {
      const msg = get().chat.messages.find(m => m.id === msgId)
      if (!msg?.approval) return
      try {
        await api('/chat/approve', {
          method: 'POST',
          body: {
            task_id: msg.approval.threadId,
            action: state === 'approved' ? 'approve' : state === 'rejected' ? 'reject' : 'edit',
            comment,
            // edit 专用:approve/reject 通道不带该字段(后端 schema 层禁止夹带)
            ...(state === 'edited' && editedSql ? { edited_sql: editedSql } : {}),
          },
        })
        set(s => ({ chat: resolveApproval(s.chat, msgId, state, comment, editedSql) }))
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
      set({
        chat: initialChatState(),
        isLoading: false,
        isGenerating: false,
        pendingQueue: [],
        turns: [],
        currentTurnIndex: 0,
        feedbacks: {},
        usage: null,
        sessionStats: initialSessionStats(),
      })
    },

    newSession: () => get().clearMessages(),
  }
})

/* E2E 调试句柄(只读用途):浏览器控制台/自动化测试可直接检查 store 状态 */
if (typeof window !== 'undefined') {
  (window as unknown as { __CHAT_STORE__?: unknown }).__CHAT_STORE__ = useChatStore
}
