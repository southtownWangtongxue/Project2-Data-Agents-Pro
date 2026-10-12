/**
 * ReasoningCard.tsx —— 思考内容折叠卡(Phase 4 类型化隔离,thinking_mode 开关控制显隐)
 */
import type { Msg } from '@/sdk/protocol'

export default function ReasoningCard({ msg }: { msg: Msg }) {
  return (
    <div className="max-w-[82%]">
      <button
        type="button"
        onClick={() => { msg.collapsed = !msg.collapsed }}
        className="flex items-center gap-2 text-[11px] text-[var(--text-3)] hover:text-brand-light transition-colors bg-transparent border-none cursor-pointer px-1 py-1"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-brand/60" />
        <span className="mono">思考过程 · {(msg.content || '').length} 字</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`transition-transform ${msg.collapsed ? '' : 'rotate-180'}`}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {!msg.collapsed && msg.content && (
        <div className="mt-1 px-3 py-2 text-[12px] leading-relaxed text-[var(--text-2)] whitespace-pre-wrap border-l-2 border-brand/40 bg-brand/[0.03] rounded-r">
          {msg.content}
        </div>
      )}
    </div>
  )
}
