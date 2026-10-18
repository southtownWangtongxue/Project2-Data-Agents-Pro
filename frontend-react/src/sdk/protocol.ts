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
  /* usage：流末下发（done 之前），Token 用量 + 上下文三段构成（读数条三弹窗数据源）。
     计量数据非消息，store 层消费（与 title 同类），不进 reducer */
  USAGE: 'usage',
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
  /* plan 事件可选:Harness todo 驱动步骤链(缺省走 legacy steps 语义) */
  todos?: { id: string; title: string; status: 'pending' | 'in_progress' | 'completed' }[]
  /* usage 事件附带(扁平结构,与后端 build_usage_event 对齐):Token 用量 +
     上下文构成（context 三段为服务端估算，estimated 标记） */
  input_tokens?: number
  output_tokens?: number
  cached_tokens?: number
  uncached_input_tokens?: number
  total_tokens?: number
  cache_hit_ratio?: number
  estimated?: boolean
  context?: {
    system_prompt: number
    tool_defs: number
    messages: number
    window: number
    used_pct: number
  }
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
    state: 'pending' | 'approved' | 'rejected' | 'edited'
    comment?: string
    /** edit 决策:审批人修改后实际执行的 SQL(原 sql 保留供对照) */
    editedSql?: string
  }
  /* 折叠态(thinking/tool 卡片) */
  collapsed?: boolean
  /* 步骤分组(阶段二 2.2 语义) */
  stepId?: number
  /** 所属轮次(多轮对话节点切换用;历史投影携带,实时消息无值) */
  turnIndex?: number
}

export interface Step {
  id: number
  agent: string
  label: string
  /* pending:todo 未开始(Harness 三态);running/completed 兼容 legacy */
  status: 'pending' | 'running' | 'completed'
  /* synthesized:true = 由工具序列事后重建的步骤(模型未建 todo 时的兜底)。
     UI 可据此弱化样式,区分"事后重建的过程"与"模型自己规划的过程"。 */
  synthesized?: boolean
}
