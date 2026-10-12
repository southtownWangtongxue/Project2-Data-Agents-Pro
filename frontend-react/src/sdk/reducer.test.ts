/**
 * reducer.test.ts —— SSE 事件分发语义(TDD RED 先行)
 * 保真清单:并行 token 分槽 / 步骤分组 / channel=sql 流式卡片 / reasoning 跨步骤换卡 /
 *          thinking·tool 只关当前步骤槽 / done·error 收尾 / 无 step_id 平铺
 */
import { describe, it, expect } from 'vitest'
import { applyEvent, initialChatState, type ChatState } from './reducer'
import { E } from './protocol'

const stepStarted = (id: number, agent: string, label = agent) => ({
  type: E.NODE_STARTED,
  agent,
  label,
  step_id: id,
})

describe('reducer: 步骤与 node_started', () => {
  it('node_started 创建 running 步骤,同 step_id 事件归入该步骤', () => {
    let s = applyEvent(initialChatState(), stepStarted(1, 'clarify_plan', '意图分析'))
    s = applyEvent(s, { type: E.THINKING, agent: 'clarify_plan', phase: 'planning', content: '分析意图并生成执行计划', step_id: 1 })
    expect(s.steps.get(1)).toMatchObject({ id: 1, agent: 'clarify_plan', status: 'running' })
    expect(s.messages).toHaveLength(1)
    expect(s.messages[0].stepId).toBe(1)
    expect(s.messages[0].kind).toBe('thinking')
  })
})

describe('reducer: token 按 stepId 分槽(并行节点不串写)', () => {
  it('同一步骤的 token 追加同一条正文消息', () => {
    let s = applyEvent(initialChatState(), stepStarted(2, 'analyst'))
    s = applyEvent(s, { type: E.TOKEN, content: '你好', channel: 'answer', step_id: 2 })
    s = applyEvent(s, { type: E.TOKEN, content: '世界', channel: 'answer', step_id: 2 })
    expect(s.messages).toHaveLength(1)
    expect(s.messages[0].content).toBe('你好世界')
  })

  it('并行步骤 7/8 的 token 交错到达时写入各自气泡,不串写', () => {
    let s = applyEvent(initialChatState(), stepStarted(7, 'analyst'))
    s = applyEvent(s, stepStarted(8, 'reporter'))
    s = applyEvent(s, { type: E.TOKEN, content: 'A1', channel: 'answer', step_id: 7 })
    s = applyEvent(s, { type: E.TOKEN, content: 'B1', channel: 'answer', step_id: 8 })
    s = applyEvent(s, { type: E.TOKEN, content: 'A2', channel: 'answer', step_id: 7 })
    s = applyEvent(s, { type: E.TOKEN, content: 'B2', channel: 'answer', step_id: 8 })
    expect(s.messages).toHaveLength(2)
    expect(s.messages[0].content).toBe('A1A2')
    expect(s.messages[1].content).toBe('B1B2')
  })

  it('thinking 事件只关闭当前步骤的正文槽,不截断并行步骤', () => {
    let s = applyEvent(initialChatState(), stepStarted(7, 'analyst'))
    s = applyEvent(s, stepStarted(8, 'reporter'))
    s = applyEvent(s, { type: E.TOKEN, content: 'A1', channel: 'answer', step_id: 7 })
    s = applyEvent(s, { type: E.TOKEN, content: 'B1', channel: 'answer', step_id: 8 })
    // 步骤 7 完成的 thinking 到达(并行中)
    s = applyEvent(s, { type: E.THINKING, agent: 'analyst', phase: 'done', content: '分析完成', step_id: 7 })
    // 步骤 8 的 token 继续 → 必须仍写原气泡,而非新气泡
    s = applyEvent(s, { type: E.TOKEN, content: 'B2', channel: 'answer', step_id: 8 })
    expect(s.messages.filter(m => m.kind === 'text')).toHaveLength(2)
    const texts = s.messages.filter(m => m.kind === 'text')
    expect(texts[0].content).toBe('A1')
    expect(texts[1].content).toBe('B1B2')
  })

  it('tool_call 关闭当前步骤的正文槽', () => {
    let s = applyEvent(initialChatState(), stepStarted(2, 'misc_agent'))
    s = applyEvent(s, { type: E.TOKEN, content: '回答', channel: 'answer', step_id: 2 })
    s = applyEvent(s, { type: E.TOOL_CALL, tool_name: 'misc_agent', args: 'q', step_id: 2 })
    s = applyEvent(s, { type: E.TOKEN, content: '续写', channel: 'answer', step_id: 2 })
    const texts = s.messages.filter(m => m.kind === 'text')
    expect(texts).toHaveLength(2) // tool_call 后新开气泡
    expect(texts[1].content).toBe('续写')
  })
})

describe('reducer: SQL 流式卡片(channel=sql)', () => {
  it('首个 sql token 创建 SQL 卡片,后续追加,sql 事件覆盖为最终 SQL', () => {
    let s = applyEvent(initialChatState(), stepStarted(3, 'sql_coder'))
    s = applyEvent(s, { type: E.TOKEN, content: 'SELECT ', channel: 'sql', step_id: 3 })
    s = applyEvent(s, { type: E.TOKEN, content: '1;', channel: 'sql', step_id: 3 })
    s = applyEvent(s, { type: E.SQL, content: 'SELECT 1;', step_id: 3 })
    expect(s.messages).toHaveLength(1)
    expect(s.messages[0].kind).toBe('sql')
    expect(s.messages[0].sql).toBe('SELECT 1;')
    // sql token 绝不进正文
    expect(s.messages.filter(m => m.kind === 'text')).toHaveLength(0)
  })
})

describe('reducer: reasoning 卡片', () => {
  it('同步骤多条 reasoning 追加同一张卡;跨步骤开新卡', () => {
    let s = applyEvent(initialChatState(), stepStarted(1, 'clarify_plan'))
    s = applyEvent(s, { type: E.REASONING, content: '思考A', step_id: 1 })
    s = applyEvent(s, { type: E.REASONING, content: '思考B', step_id: 1 })
    s = applyEvent(s, stepStarted(2, 'misc_agent'))
    s = applyEvent(s, { type: E.REASONING, content: '思考C', step_id: 2 })
    const cards = s.messages.filter(m => m.kind === 'reasoning')
    expect(cards).toHaveLength(2)
    expect(cards[0].content).toBe('思考A思考B')
    expect(cards[1].content).toBe('思考C')
  })
})

describe('reducer: 工具卡片合并', () => {
  it('tool_result 与最近的同名 tool_call 合并为完成态', () => {
    let s = applyEvent(initialChatState(), stepStarted(5, 'execute_sql'))
    s = applyEvent(s, { type: E.TOOL_CALL, tool_name: 'execute_sql', step_id: 5 })
    s = applyEvent(s, { type: E.TOOL_RESULT, tool_name: 'execute_sql', result: '返回 12 条记录', step_id: 5 })
    const tools = s.messages.filter(m => m.kind === 'tool')
    expect(tools).toHaveLength(1)
    expect(tools[0].toolPhase).toBe('done')
    expect(tools[0].toolMeta?.result).toBe('返回 12 条记录')
  })
})

describe('reducer: 审批卡片(HITL)', () => {
  it('approval_required 生成 pending 审批消息并盖章 step_id', () => {
    let s = applyEvent(initialChatState(), stepStarted(4, 'security'))
    s = applyEvent(s, {
      type: E.APPROVAL_REQUIRED,
      thread_id: 'admin:1',
      question: '删除订单',
      sql: 'DELETE FROM orders',
      reason: '写操作',
      step_id: 4,
    })
    const approvals = s.messages.filter(m => m.kind === 'approval')
    expect(approvals).toHaveLength(1)
    expect(approvals[0].approval?.state).toBe('pending')
    expect(approvals[0].stepId).toBe(4)
  })
})

describe('reducer: 收尾与平铺', () => {
  it('done 标记全部步骤完成并清空槽位', () => {
    let s = applyEvent(initialChatState(), stepStarted(1, 'clarify_plan'))
    s = applyEvent(s, stepStarted(2, 'misc_agent'))
    s = applyEvent(s, { type: E.TOKEN, content: 'hi', channel: 'answer', step_id: 2 })
    s = applyEvent(s, { type: E.DONE })
    expect([...s.steps.values()].every(st => st.status === 'completed')).toBe(true)
    expect(s.activeTextMsgByStep.size).toBe(0)
  })

  it('无 step_id 的事件(thread_id/status/plan)平铺且不盖章', () => {
    let s = applyEvent(initialChatState(), { type: E.THREAD_ID, thread_id: 'admin:1' })
    s = applyEvent(s, { type: E.PLAN, intent: 'other_questions', steps: [], chart_suitable: false })
    expect(s.threadId).toBe('admin:1')
    const plan = s.messages.find(m => m.kind === 'plan')
    expect(plan?.stepId).toBeUndefined()
  })

  it('error 事件生成错误消息', () => {
    const s = applyEvent(initialChatState(), { type: E.ERROR, error: 'LLM 超时', code: 'LLM_TIMEOUT', recoverable: true })
    expect(s.messages[0].kind).toBe('error')
    expect(s.messages[0].errorCode).toBe('LLM_TIMEOUT')
  })
})

describe('reducer: 审批状态推进', () => {
  it('resolveApproval 将指定审批置为 approved/rejected', () => {
    let s = applyEvent(initialChatState(), stepStarted(4, 'security'))
    s = applyEvent(s, { type: E.APPROVAL_REQUIRED, thread_id: 't1', question: 'q', sql: 's', reason: 'r', step_id: 4 })
    const id = s.messages[0].id
    s = resolveApprovalIn(s, id, 'approved', '同意执行')
    expect(s.messages[0].approval?.state).toBe('approved')
    expect(s.messages[0].approval?.comment).toBe('同意执行')
  })
})

/* 辅助:审批状态推进(store action 的纯函数部分) */
function resolveApprovalIn(s: ChatState, msgId: string, state: 'approved' | 'rejected', comment: string): ChatState {
  return {
    ...s,
    messages: s.messages.map(m =>
      m.id === msgId && m.approval ? { ...m, approval: { ...m.approval, state, comment } } : m,
    ),
  }
}
