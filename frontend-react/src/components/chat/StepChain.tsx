/**
 * StepChain.tsx —— 步骤分组链(antdx ThoughtChain,受控折叠)
 *
 * 语义(已确认,不可回退):运行中展开 → 完成 2s 后自动折叠 → 用户点击优先。
 * 组件层级对齐官方独立式样板间:步骤头用 ThoughtChain.Item 的状态点 + 标题 + 描述,
 * 内容区承载该步骤的全部消息(组内固定类型序)。
 */
import { useEffect, useRef, useState } from 'react'
import { ThoughtChain } from '@ant-design/x'
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
  const running = step.status === 'running'

  useEffect(() => {
    if (running) return
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setAutoCollapsed(true), 2000)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [running])

  /* 运行中强制展开;完成后按「用户意图 > 自动折叠」取值 */
  const expanded = running ? true : userExpanded !== null ? userExpanded : !autoCollapsed

  const sorted = [...messages].sort((a, b) => (RANK[a.kind] ?? 2) - (RANK[b.kind] ?? 2))

  return (
    <div className="w-full">
      <ThoughtChain
        line={false}
        expandedKeys={expanded ? [String(step.id)] : []}
        onExpand={keys => setUserExpanded(keys.includes(String(step.id)))}
        items={[
          {
            key: String(step.id),
            description: (
              <span className="mono text-[11px] text-[var(--text-3)]">
                步骤 {step.id} · {step.agent}
                {step.synthesized ? ' · 工具序列重建' : ''}
              </span>
            ),
            status: running ? 'loading'
              : step.status === 'pending' ? 'abort'   /* todo 未开始:官方 abort 空心态 */
              : 'success',
            /* 兜底链(模型未建 todo,按工具序列事后重建):标题前加 ↺ 前缀并在描述里
               注明"工具序列重建",让用户看得出这是重建过程而非模型自己规划的步骤 */
            title: (step.synthesized ? '↺ ' : '') + (step.label || step.agent),
            blink: running,
            collapsible: true,
            content: (
              <div className="space-y-2 pt-1">
                {sorted.map(m => (
                  <MessageItem key={m.id} msg={m} />
                ))}
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}