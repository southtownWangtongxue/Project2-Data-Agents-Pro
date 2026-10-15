/**
 * blocks.test.ts —— 渲染块编排(TDD RED)
 * 核心语义:同一 stepId 的消息全局聚合为一个 StepChain(并行节点消息交错也不拆分),
 * 平铺消息保持原序;步骤块按「步骤首次出现」的位置输出。
 */
import { describe, it, expect } from 'vitest'
import { buildBlocks } from './blocks'
import type { Msg, Step } from './protocol'

const msg = (id: string, stepId: number, kind: Msg['kind'] = 'text'): Msg => ({ id, role: 'assistant', kind, stepId })
const step = (id: number, status: Step['status'] = 'completed'): Step => ({ id, agent: `a${id}`, label: `步骤${id}`, status })

describe('buildBlocks', () => {
  it('同一 stepId 的消息聚合为一个块(并行 7/8 交错不拆分)', () => {
    const messages = [
      msg('u1', 0, 'text'),           // 用户消息(无 step)
      { ...msg('t1', 1, 'thinking') },
      msg('a1', 7),                   // analyst 第一批
      msg('r1', 8),                   // reporter 第一批(并行交错)
      msg('a2', 7),                   // analyst 第二批
      msg('r2', 8),                   // reporter 第二批
    ]
    messages[0].role = 'user'
    const steps = new Map([[1, step(1)], [7, step(7)], [8, step(8)]])
    const blocks = buildBlocks(messages, steps)

    const stepBlocks = blocks.filter(b => b.kind === 'step')
    expect(stepBlocks.map(b => (b as { step: Step }).step.id)).toEqual([1, 7, 8])
    // 步骤 7 的两条消息在同一块内
    const s7 = stepBlocks.find(b => (b as { step: Step }).step.id === 7) as { messages: Msg[] }
    expect(s7.messages.map(m => m.id)).toEqual(['a1', 'a2'])
    const s8 = stepBlocks.find(b => (b as { step: Step }).step.id === 8) as { messages: Msg[] }
    expect(s8.messages.map(m => m.id)).toEqual(['r1', 'r2'])
  })

  it('平铺消息(无 stepId/无 Step 元数据)保持原序输出', () => {
    const messages = [
      { ...msg('p1', 0, 'plan') },
      msg('t1', 1, 'thinking'),
      { ...msg('p2', 0, 'plan') },
    ]
    const steps = new Map([[1, step(1)]])
    const blocks = buildBlocks(messages, steps)
    expect(blocks.map(b => b.kind)).toEqual(['msg', 'step', 'msg'])
    expect((blocks[2] as { msg: Msg }).msg.id).toBe('p2')
  })

  it('步骤块按步骤首次出现的位置插入序列', () => {
    const messages = [
      msg('a1', 7),
      { ...msg('p1', 0, 'plan') },     // plan 平铺,夹在中间
      msg('a2', 7),
    ]
    const steps = new Map([[7, step(7)]])
    const blocks = buildBlocks(messages, steps)
    expect(blocks.map(b => b.kind)).toEqual(['step', 'msg'])
    expect((blocks[0] as { messages: Msg[] }).messages.map(m => m.id)).toEqual(['a1', 'a2'])
  })
})

describe('buildBlocks: pending 步骤可见性(todo 骨架,Harness Phase 1)', () => {
  const harnessStep = (id: number, label: string, status: Step['status']): Step =>
    ({ id, agent: 'harness', label, status })

  it('尚无消息的 pending 步骤也输出空内容步骤块', () => {
    const steps = new Map([
      [1, harnessStep(1, '查各表数据量', 'running')],
      [2, harnessStep(2, '生成图表', 'pending')],
    ])
    const messages = [msg('a1', 1)]
    const blocks = buildBlocks(messages, steps)
    const stepBlocks = blocks.filter(b => b.kind === 'step')
    expect(stepBlocks).toHaveLength(2)
    const second = stepBlocks[1] as { step: Step; messages: Msg[] }
    expect(second.step.status).toBe('pending')
    expect(second.messages).toHaveLength(0)
  })

  it('pending 步骤按 id 顺序插在已有步骤之后', () => {
    const steps = new Map([
      [1, harnessStep(1, 'A', 'completed')],
      [2, harnessStep(2, 'B', 'pending')],
    ])
    const blocks = buildBlocks([msg('a1', 1)], steps)
    expect(blocks.map(b => b.kind === 'step' ? b.step.id : 'msg')).toEqual([1, 2])
  })
})


describe('buildBlocks: 工具序列兜底步骤链(b 方案)', () => {
  const toolMsg = (id: string, name: string, args?: string, stepId = 0): Msg => ({
    id, role: 'system', kind: 'tool', toolName: name, toolPhase: 'call',
    toolMeta: args ? { args } : undefined, stepId,
  })

  // 约束 1:只有 tool_call → 合成链
  it('只有工具调用(无 todo)时合成步骤链', () => {
    const messages = [
      { ...msg('u1', 0, 'text'), role: 'user' as const },
      toolMsg('t1', 'get_table_schema', 'keywords=订单'),
      toolMsg('t2', 'run_sql', 'SELECT COUNT(*) FROM orders'),
    ]
    const blocks = buildBlocks(messages, new Map())
    const stepBlocks = blocks.filter(b => b.kind === 'step')
    expect(stepBlocks).toHaveLength(2)
    expect((stepBlocks[0] as { step: Step }).step.label).toContain('get_table_schema')
    expect((stepBlocks[1] as { step: Step }).step.label).toContain('SELECT COUNT(*)')
  })

  // 约束 1:只有 todo → 走原逻辑,不合成
  it('已有 todo 步骤时不做兜底(真 plan 优先)', () => {
    const steps = new Map([[1, { id: 1, agent: 'harness', label: '查订单', status: 'running' as const }]])
    const blocks = buildBlocks([msg('a1', 1), toolMsg('t1', 'run_sql', 'SELECT 1', 0)], steps)
    const stepBlocks = blocks.filter(b => b.kind === 'step')
    // 只应有 todo 那一块;工具消息不额外生成合成步骤
    expect(stepBlocks).toHaveLength(1)
    expect((stepBlocks[0] as { step: Step }).step.label).toBe('查订单')
  })

  // 约束 1:两者都有 → todo 赢,合成链不渲染
  it('todo 与工具调用并存时只渲染 todo 骨架(不出现双步骤来源)', () => {
    const steps = new Map([
      [1, { id: 1, agent: 'harness', label: '查订单', status: 'running' as const }],
      [2, { id: 2, agent: 'harness', label: '出图表', status: 'pending' as const }],
    ])
    const messages = [msg('a1', 1), toolMsg('t1', 'run_sql', 'SELECT 1', 0), toolMsg('t2', 'make_chart', '', 0)]
    const blocks = buildBlocks(messages, steps)
    const stepBlocks = blocks.filter(b => b.kind === 'step') as { step: Step }[]
    expect(stepBlocks).toHaveLength(2)
    expect(stepBlocks.every(s => !s.step.synthesized)).toBe(true)
    expect(stepBlocks.map(s => s.step.label)).toEqual(['查订单', '出图表'])
  })

  // 约束 2:合成节点必须标注来源,且语义为"事后重建的已完成"
  it('合成步骤带 synthesized 标记且状态为 completed', () => {
    const blocks = buildBlocks([toolMsg('t1', 'run_sql', 'SELECT 1', 0)], new Map())
    const step = (blocks.find(b => b.kind === 'step') as { step: Step }).step
    expect(step.synthesized).toBe(true)
    expect(step.status).toBe('completed')
  })

  // 约束 2:UI 可据此弱化样式(信息不失真)
  it('真实 todo 步骤不带 synthesized 标记', () => {
    const steps = new Map([[1, { id: 1, agent: 'h', label: 'A', status: 'running' as const }]])
    const blocks = buildBlocks([msg('a1', 1)], steps)
    const step = (blocks.find(b => b.kind === 'step') as { step: Step }).step
    expect(step.synthesized).toBeUndefined()
  })

  // 约束 3:入参可得时摘要带 SQL 片段(过程感不退化)
  it('合成步骤摘要在入参可得时包含参数片段', () => {
    const blocks = buildBlocks([toolMsg('t1', 'run_sql', 'SELECT COUNT(*) FROM orders WHERE status=1', 0)], new Map())
    const step = (blocks.find(b => b.kind === 'step') as { step: Step }).step
    expect(step.label).toContain('run_sql')
    expect(step.label).toContain('SELECT COUNT(*)')
  })

  it('入参缺失时退化为仅工具名(不报错)', () => {
    const blocks = buildBlocks([toolMsg('t1', 'web_search_tool', '', 0)], new Map())
    const step = (blocks.find(b => b.kind === 'step') as { step: Step }).step
    expect(step.label).toBe('web_search_tool')
  })

  // 非工具类消息不参与兜底(闲聊不该凭空长出步骤链)
  it('没有工具调用时不合成任何步骤', () => {
    const blocks = buildBlocks([{ ...msg('a1', 0, 'text'), role: 'assistant' as const }], new Map())
    expect(blocks.filter(b => b.kind === 'step')).toHaveLength(0)
  })
})
