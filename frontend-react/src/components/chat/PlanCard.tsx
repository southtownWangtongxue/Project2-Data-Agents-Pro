/**
 * PlanCard.tsx —— 执行计划卡(空步骤不渲染,由 MessageItem 过滤)
 */
import type { Msg } from '@/sdk/protocol'

export default function PlanCard({ msg }: { msg: Msg }) {
  return (
    <div className="max-w-[82%] rounded-lg border border-[var(--border)] bg-[var(--cockpit-800)] p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[13px] font-semibold text-[var(--text-1)]">执行计划</span>
        {msg.planIntentLabel && (
          <span className="px-2 py-0.5 rounded-full text-[11px] text-brand-light mono"
            style={{ background: 'rgba(112,86,248,0.1)' }}>
            {msg.planIntentLabel}
          </span>
        )}
      </div>
      <ol className="m-0 pl-5 space-y-1">
        {(msg.planSteps || []).map((s, i) => (
          <li key={i} className="text-[13px] text-[var(--text-2)]">{s}</li>
        ))}
      </ol>
    </div>
  )
}
