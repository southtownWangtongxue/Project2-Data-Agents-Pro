/**
 * reducer.ts —— SSE 事件 → 对话状态(纯函数,可单测)
 *
 * 保真移植 Vue chat.ts 的已修复语义:
 * - 按 stepId 分槽的流式正文(并行 analyst/reporter 不串写、不被 thinking/tool 截断)
 * - node_started 创建步骤;done 标记全部完成并清槽
 * - channel=sql → SQL 卡片流式追加(sql 事件覆盖为清洗后 SQL)
 * - reasoning 同步骤追加、跨步骤换卡
 * - tool_result 与最近同名 tool_call 合并
 * - 无 step_id 事件平铺(旧会话回放降级)
 */
import { E, type Msg, type SSEEvent, type Step } from './protocol'

export interface ChatState {
  messages: Msg[]
  steps: Map<number, Step>
  currentStepId: number
  threadId: string
  lastAssistantMsgId: string
  /* 流式槽位:stepKey → 消息 id */
  activeTextMsgByStep: Map<number, string>
  activeReasoningMsgId: string | null
  activeReasoningStepId: number
  activeSqlMsgId: string | null
}

let _seq = 0
function msgId(): string {
  _seq += 1
  return `m_${Date.now().toString(36)}_${_seq}`
}

export function initialChatState(): ChatState {
  return {
    messages: [],
    steps: new Map(),
    currentStepId: 0,
    threadId: '',
    lastAssistantMsgId: '',
    activeTextMsgByStep: new Map(),
    activeReasoningMsgId: null,
    activeReasoningStepId: 0,
    activeSqlMsgId: null,
  }
}

/** 深拷贝 Map(React/zustand 需要不可变更新) */
function cloneState(s: ChatState): ChatState {
  return {
    ...s,
    steps: new Map(s.steps),
    activeTextMsgByStep: new Map(s.activeTextMsgByStep),
  }
}

export function applyEvent(prev: ChatState, ev: SSEEvent): ChatState {
  const s = cloneState(prev)

  switch (ev.type) {
    case E.THREAD_ID:
      s.threadId = ev.thread_id || s.threadId
      return s

    case E.NODE_STARTED: {
      const id = ev.step_id || 0
      if (!s.steps.has(id)) {
        s.steps.set(id, {
          id,
          agent: ev.agent || '',
          label: ev.label || ev.agent || '',
          status: 'running',
        })
      }
      s.currentStepId = id
      return s
    }

    case E.STATUS: {
      s.messages.push({ id: msgId(), role: 'system', kind: 'status', content: ev.content || '' })
      return s
    }

    case E.THINKING: {
      s.messages.push({
        id: msgId(),
        role: 'system',
        kind: 'thinking',
        agent: ev.agent,
        phase: ev.phase,
        content: ev.content,
        collapsed: false,
        stepId: ev.step_id,
      })
      return s
    }

    case E.REASONING: {
      if (!ev.content) return s
      const sid = ev.step_id || 0
      if (s.activeReasoningMsgId && s.activeReasoningStepId === sid) {
        s.messages = s.messages.map(m =>
          m.id === s.activeReasoningMsgId ? { ...m, content: (m.content || '') + ev.content } : m,
        )
      } else {
        const id = msgId()
        s.activeReasoningMsgId = id
        s.activeReasoningStepId = sid
        s.messages.push({
          id,
          role: 'assistant',
          kind: 'reasoning',
          content: ev.content,
          collapsed: true,
          stepId: ev.step_id,
        })
      }
      return s
    }

    case E.TOKEN: {
      const stepKey = ev.step_id || 0
      if (ev.channel === 'sql') {
        // SQL 流式卡片:绝不以裸文本进正文
        if (s.activeSqlMsgId) {
          s.messages = s.messages.map(m =>
            m.id === s.activeSqlMsgId ? { ...m, sql: (m.sql || '') + (ev.content || '') } : m,
          )
        } else {
          const id = msgId()
          s.activeSqlMsgId = id
          s.messages.push({
            id,
            role: 'assistant',
            kind: 'sql',
            sql: ev.content || '',
            stepId: ev.step_id,
          })
        }
        return s
      }
      // 正文:按 stepId 分槽(并行节点互不串写)
      const activeId = s.activeTextMsgByStep.get(stepKey)
      const activeMsg = activeId ? s.messages.find(m => m.id === activeId) : undefined
      if (activeMsg) {
        s.messages = s.messages.map(m =>
          m.id === activeId ? { ...m, content: (m.content || '') + (ev.content || '') } : m,
        )
      } else {
        const id = msgId()
        s.activeTextMsgByStep.set(stepKey, id)
        s.lastAssistantMsgId = id
        s.messages.push({
          id,
          role: 'assistant',
          kind: 'text',
          content: ev.content || '',
          stepId: ev.step_id,
        })
      }
      return s
    }

    case E.SQL: {
      // 用清洗后的完整 SQL 覆盖流式卡片
      if (s.activeSqlMsgId) {
        s.messages = s.messages.map(m =>
          m.id === s.activeSqlMsgId ? { ...m, sql: ev.content || '' } : m,
        )
        s.activeSqlMsgId = null
      } else {
        s.messages.push({
          id: msgId(),
          role: 'assistant',
          kind: 'sql',
          sql: ev.content || '',
          stepId: ev.step_id,
        })
      }
      return s
    }

    case E.TOOL_CALL: {
      // 当前步骤的正文槽关闭(该步骤流式回答已交付给工具)
      s.activeTextMsgByStep.delete(ev.step_id || 0)
      s.messages.push({
        id: msgId(),
        role: 'system',
        kind: 'tool',
        toolName: ev.tool_name || ev.name,
        toolPhase: 'call',
        toolMeta: ev.args ? { args: String(ev.args).slice(0, 300) } : undefined,
        collapsed: true,
        stepId: ev.step_id,
      })
      return s
    }

    case E.TOOL_RESULT: {
      // 与最近的同名未合并 tool_call 合并为完成态
      const name = ev.tool_name || ev.name
      const resultText = ev.content || ev.result || ''
      const meta: Record<string, unknown> = {}
      if (resultText) meta.result = String(resultText).slice(0, 400)
      if (ev.status) meta.status = ev.status
      const idx = [...s.messages]
        .reverse()
        .findIndex(m => m.kind === 'tool' && m.toolName === name && m.toolPhase === 'call')
      if (idx >= 0) {
        const realIdx = s.messages.length - 1 - idx
        s.messages = s.messages.map((m, i) =>
          i === realIdx ? { ...m, toolPhase: 'done' as const, toolMeta: meta, collapsed: true } : m,
        )
      } else {
        s.messages.push({
          id: msgId(),
          role: 'system',
          kind: 'tool',
          toolName: name,
          toolPhase: 'done',
          toolMeta: meta,
          collapsed: true,
          stepId: ev.step_id,
        })
      }
      return s
    }

    case E.RESULT: {
      s.messages.push({
        id: msgId(),
        role: 'assistant',
        kind: 'result',
        data: ev.data || [],
        columns: ev.columns || [],
        stepId: ev.step_id,
      })
      return s
    }

    case E.CHART: {
      s.messages.push({
        id: msgId(),
        role: 'assistant',
        kind: 'chart',
        chartConfig: ev.config,
        stepId: ev.step_id,
      })
      return s
    }

    case E.PLAN: {
      s.messages.push({
        id: msgId(),
        role: 'system',
        kind: 'plan',
        planIntent: ev.intent,
        planIntentLabel: ev.intent_label,
        planSteps: ev.steps,
        planChartSuitable: ev.chart_suitable,
      })
      return s
    }

    case E.CLARIFICATION: {
      s.messages.push({
        id: msgId(),
        role: 'system',
        kind: 'clarification',
        content: ev.text || ev.content,
        clarifyOptions: ev.options,
      })
      return s
    }

    case E.QUALITY_FEEDBACK: {
      s.messages.push({ id: msgId(), role: 'system', kind: 'status', content: ev.feedback || ev.content || '' })
      return s
    }

    case E.APPROVAL_REQUIRED: {
      s.messages.push({
        id: msgId(),
        role: 'system',
        kind: 'approval',
        approval: {
          threadId: ev.thread_id || s.threadId,
          question: ev.question || '',
          sql: ev.sql || '',
          reason: ev.reason || '',
          state: 'pending',
        },
        stepId: ev.step_id,
      })
      return s
    }

    case E.ERROR: {
      s.messages.push({
        id: msgId(),
        role: 'assistant',
        kind: 'error',
        content: ev.error || ev.content || '未知错误',
        errorCode: ev.code,
        recoverable: ev.recoverable ?? false,
      })
      return s
    }

    case E.DONE: {
      s.steps.forEach(st => { st.status = 'completed' })
      s.activeTextMsgByStep.clear()
      s.activeSqlMsgId = null
      return s
    }

    case E.TITLE:
      // 标题由 store 层处理(更新会话列表),不产生消息
      return s

    default:
      // 未知类型:保持兼容,静默忽略(与前端 useSSE 的告警降级不同,此处不污染 store)
      return s
  }
}

/** 审批状态推进(ApprovalCard 通过/拒绝后) */
export function resolveApproval(s: ChatState, msgIdToResolve: string, state: 'approved' | 'rejected', comment: string): ChatState {
  return {
    ...s,
    messages: s.messages.map(m =>
      m.id === msgIdToResolve && m.approval
        ? { ...m, approval: { ...m.approval, state, comment } }
        : m,
    ),
  }
}
