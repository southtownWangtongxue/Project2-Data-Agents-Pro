/**
 * sdk/protocol.ts —— 前端 SSE 协议类型(与后端 stream_protocol.py / chat.py 对齐)
 * 只增不改:事件类型常量集中定义,新增字段仅追加。
 */

/* SSE 事件类型(后端 SSEEventType) */
export const E = {
  THREAD_ID: 'thread_id',
  STATUS: 'status',
  THINKING: 'thinking',
  REASONING: 'reasoning',
  TOKEN: 'token',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  SQL: 'sql',
  RESULT: 'result',
  CHART: 'chart',
  PLAN: 'plan',
  CLARIFICATION: 'clarification',
  ERROR: 'error',
  TITLE: 'title',
  DONE: 'done',
  APPROVAL_REQUIRED: 'approval_required',
  QUALITY_FEEDBACK: 'quality_feedback',
  NODE_STARTED: 'node_started',
} as const

/** 后端推送的单条 SSE 事件(已 JSON 解析) */
export interface SSEEvent {
  type: string
  content?: string
  channel?: string
  step_id?: number
  agent?: string
  phase?: string
  label?: string
  sql?: string
  data?: any[]
  columns?: string[]
  config?: Record<string, unknown>
  text?: string
  options?: string[]
  intent?: string
  intent_label?: string
  steps?: string[]
  chart_suitable?: boolean
  name?: string
  args?: string
  status?: string
  result?: string
  tool_name?: string
  error?: string
  code?: string
  recoverable?: boolean
  thread_id?: string
  question?: string
  reason?: string
  node_index?: number
  feedback?: string
  /* status 事件附带:审批被拒/超时后打戳前端审批卡(协议只增) */
  approval_state?: string
}

/* 领域消息类型(store 中的消息,stepId 为分组键) */
export type MsgKind =
  | 'text'
  | 'sql'
  | 'result'
  | 'chart'
  | 'error'
  | 'reasoning'
  | 'thinking'
  | 'tool'
  | 'clarification'
  | 'plan'
  | 'approval'
  | 'status'

export interface Msg {
  id: string
  role: 'user' | 'assistant' | 'system'
  kind: MsgKind
  content?: string
  sql?: string
  data?: any[]
  columns?: string[]
  chartConfig?: Record<string, unknown>
  /* thinking */
  agent?: string
  phase?: string
  /* tool */
  toolName?: string
  toolPhase?: 'call' | 'done'
  toolMeta?: Record<string, unknown>
  /* error */
  errorCode?: string
  recoverable?: boolean
  /* clarification */
  clarifyOptions?: string[]
  /* plan */
  planIntent?: string
  planIntentLabel?: string
  planSteps?: string[]
  planChartSuitable?: boolean
  /* approval(HITL) */
  approval?: {
    threadId: string
    question: string
    sql: string
    reason: string
    state: 'pending' | 'approved' | 'rejected'
    comment?: string
  }
  /* 折叠态(thinking/tool 卡片) */
  collapsed?: boolean
  /* 步骤分组(阶段二 2.2 语义) */
  stepId?: number
}

export interface Step {
  id: number
  agent: string
  label: string
  status: 'running' | 'completed'
}
