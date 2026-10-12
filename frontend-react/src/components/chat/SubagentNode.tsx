/**
 * SubagentNode.tsx —— 子代理执行节点(task 模式委派)
 */
import type { Msg } from '@/sdk/protocol'

export default function SubagentNode({ msg }: { msg: Msg }) {
  const done = msg.toolPhase === 'done' || msg.toolMeta?.status === 'done'
  return (
    <div className="max-w-[82%] flex items-center gap-2 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--cockpit-800)] text-[12px]">
      <span className={`w-2 h-2 rounded-full ${done ? 'bg-[var(--success)]' : 'bg-brand brand-pulse'}`} />
      <span className="text-[var(--text-2)]">子代理执行</span>
      <span className="text-[var(--text-3)] mono ml-auto">{done ? '已完成' : '执行中…'}</span>
    </div>
  )
}
