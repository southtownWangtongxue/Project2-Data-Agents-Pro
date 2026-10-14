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

export function buildBlocks(messages: Msg[], steps: Map<number, Step>): Block[] {
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

  /* 全部已知步骤按 id 排序(含尚无消息的 pending 步骤——todo 骨架需要它们可见) */
  const allStepIds = [...steps.keys()].sort((a, b) => a - b)
  const emitted = new Set<number>()
  const out: Block[] = []
  const emitStep = (sid: number) => {
    if (emitted.has(sid)) return
    const step = steps.get(sid)
    if (!step) return
    emitted.add(sid)
    out.push({ kind: 'step', key: `step-${sid}`, role: 'ai', step, messages: stepMsgs.get(sid) || [] })
  }

  /* 第二遍:按原消息顺序输出;步骤首条消息处输出聚合块,其余同 step 消息跳过 */
  for (const m of messages) {
    const sid = m.stepId || 0
    const step = sid ? steps.get(sid) : undefined
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
