/**
 * StepChain.tsx —— 步骤分组链(受控折叠)
 * 语义(已确认):运行中展开 → 完成 2s 后自动折叠 → 用户点击头部优先。
 * 视觉对齐 antdx ThoughtChain:左轨状态点 + 步骤头 + 内容区。
 */
import { useEffect, useRef, useState } from 'react'
import type { Msg, Step } from '@/sdk/protocol'
import MessageItem from './MessageItem'

interface Props {
  step: Step
  messages: Msg[]
}

/** 组内固定类型序:思考 → 工具 → 正文/SQL/结果/图表 */
const RANK: Record<string, number> = { reasoning: 0, thinking: 0, tool: 1 }

export default function StepChain({ step, messages }: Props) {
  const [autoCollapsed, setAutoCollapsed] = useState(false)
  const [userExpanded, setUserExpanded] = useState<boolean | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (step.status === 'completed' && !autoCollapsed) {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setAutoCollapsed(true), 2000)
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [step.status, autoCollapsed])

  const expanded =
    step.status === 'running' ? true : userExpanded !== null ? userExpanded : !autoCollapsed

  const sorted = [...messages].sort(
    (a, b) => (RANK[a.kind] ?? 2) - (RANK[b.kind] ?? 2),
  )

  return (
    <section className="mb-3 rounded-xl border border-[var(--border)] overflow-hidden bg-white/[0.02] data-[running=true]:border-brand/35">
      <button
        type="button"
        onClick={() => setUserExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[13px] cursor-pointer bg-transparent border-none text-left hover:bg-brand/5 transition-colors"
      >
        <span
          className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
            step.status === 'running' ? 'bg-brand brand-pulse' : 'bg-[var(--success)]'
          }`}
        />
        <span className="font-semibold text-brand-light mono">步骤 {step.id}</span>
        <span className="text-[var(--text-1)] font-medium">{step.label}</span>
        <span
          className={`ml-auto text-[11px] px-2 py-0.5 rounded-full ${
            step.status === 'running'
              ? 'text-[var(--warning)] bg-[var(--warning)]/10'
              : 'text-[var(--success)] bg-[var(--success)]/10'
          }`}
        >
          {step.status === 'running' ? '运行中' : '已完成'}
        </span>
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`flex-shrink-0 text-[var(--text-3)] transition-transform ${expanded ? 'rotate-180' : ''}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {expanded && (
        <div className="px-3 py-2 border-t border-[var(--border)] bg-black/15 space-y-2">
          {sorted.map(m => (
            <MessageItem key={m.id} msg={m} />
          ))}
        </div>
      )}
    </section>
  )
}
