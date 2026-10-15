/**
 * blocks.ts —— 渲染块编排(纯函数,可单测)
 *
 * 规则:
 * - user 消息 / 无 stepId 或无 Step 元数据的消息 → 平铺块(保持原序)
 * - 同一 stepId 的消息**全局聚合**为一个 StepChain 块——并行节点
 *   (analyst/reporter)消息交错到达也不拆成多个步骤头
 * - 步骤块按「步骤首次出现」的位置插入序列
 */
import type { Msg, Step } from './protocol'

export type Block =
  | { kind: 'msg'; key: string; role: 'user' | 'ai'; msg: Msg }
  | { kind: 'step'; key: string; role: 'ai'; step: Step; messages: Msg[] }

/** 合成步骤的参数摘要长度(与 reducer 里 toolMeta.args 的 300 一致量级) */
const SYNTH_ARGS_MAX = 80

/**
 * 工具序列兜底步骤链(b 方案)。
 *
 * 背景:模型不总是建 todo(实测 11 次采样 0 次),此时若只认 todo 骨架,
 * 有工具调用的运行也长不出步骤链——过程完全不可见。
 *
 * 三条硬约束(与产品决策一致,勿破坏):
 * 1. 真 plan 优先:仅当 steps 为空(即全程无 todo)才合成,绝不与 todo 骨架并存;
 * 2. 合成节点显式标注 synthesized,语义为「事后重建的已完成」,UI 可弱化样式
 *    区分"事后重建"与"模型自己规划"——前端可以组织事实,但不能制造事实;
 * 3. 入参可得时摘要带参数片段(如 run_sql: SELECT COUNT(*) ...),
 *    缺失时退化为纯工具名,不报错。
 */
function synthStepsFromTools(messages: Msg[]): Step[] {
  const tools = messages.filter(m => m.kind === 'tool' && m.toolName)
  return tools.map((m, idx) => {
    const name = m.toolName!
    const rawArgs = m.toolMeta?.args
    const args = (typeof rawArgs === 'string' ? rawArgs : rawArgs ? JSON.stringify(rawArgs) : '')
      .replace(/\s+/g, ' ').trim()
    const label = args
      ? `${name}: ${args.length > SYNTH_ARGS_MAX ? args.slice(0, SYNTH_ARGS_MAX) + '…' : args}`
      : name
    return { id: idx + 1, agent: name, label, status: 'completed', synthesized: true }
  })
}

export function buildBlocks(messages: Msg[], steps: Map<number, Step>): Block[] {
  /* 兜底:全程无 todo 步骤时,用工具序列合成一条"事后重建"步骤链 */
  const synthSteps = steps.size === 0 ? synthStepsFromTools(messages) : []
  const synthByMsgId = new Map<string, number>()
  if (synthSteps.length > 0) {
    let i = 0
    for (const m of messages) {
      if (m.kind === 'tool' && m.toolName) synthByMsgId.set(m.id, ++i)
    }
  }

  /* 第一遍:按 stepId 聚合(保序) */
  const stepOrder: number[] = []
  const stepMsgs = new Map<number, Msg[]>()
  for (const m of messages) {
    const sid = m.stepId || 0
    const step = sid ? steps.get(sid) : undefined
    if (!step) continue
    if (!stepMsgs.has(sid)) {
      stepMsgs.set(sid, [])
      stepOrder.push(sid)
    }
    stepMsgs.get(sid)!.push(m)
  }
  if (synthSteps.length > 0) {
    for (const s of synthSteps) stepMsgs.set(s.id, [])
  }

  /* 全部已知步骤按 id 排序(含尚无消息的 pending 步骤——todo 骨架需要它们可见) */
  const allStepIds = [...steps.keys()].sort((a, b) => a - b)
  const emitted = new Set<number>()
  const out: Block[] = []
  const emitStep = (sid: number) => {
    if (emitted.has(sid)) return
    const step = steps.get(sid) ?? synthSteps.find(s => s.id === sid)
    if (!step) return
    emitted.add(sid)
    out.push({ kind: 'step', key: `step-${sid}`, role: 'ai', step, messages: stepMsgs.get(sid) || [] })
  }

  /* 第二遍:按原消息顺序输出;步骤首条消息处输出聚合块,其余同 step 消息跳过 */
  for (const m of messages) {
    const sid = m.stepId || 0
    const step = sid ? steps.get(sid) : undefined
    /* 兜底链:工具消息归入它自己的合成步骤(而非平铺) */
    const synthId = synthByMsgId.get(m.id)
    if (synthId !== undefined) {
      emitStep(synthId)
      continue
    }
    if (m.role === 'user' || !step) {
      out.push({ kind: 'msg', key: m.id, role: m.role === 'user' ? 'user' : 'ai', msg: m })
      continue
    }
    /* 先补发更早且尚未出现的步骤(pending 空块),保持 todo 顺序 */
    for (const id of allStepIds) {
      if (id >= sid) break
      emitStep(id)
    }
    if (emitted.has(sid)) continue
    emitStep(sid)
  }
  /* 收尾:补发剩余没有任何消息的步骤(如全部 pending 的后续 todo) */
  for (const id of allStepIds) emitStep(id)
  return out
}
