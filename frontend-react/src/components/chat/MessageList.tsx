/**
 * MessageList.tsx —— 消息列表(Bubble.List 容器 + 渲染块编排)
 *
 * 编排规则(与 Vue R1 同构):
 * - user 消息 → 用户气泡块
 * - 有 stepId 且存在 Step 元数据的连续区段 → StepChain(组内固定类型序)
 * - 其余(旧会话回放/系统级事件)→ 平铺消息
 * Bubble 用 borderless 变体:视觉由 MessageItem/StepChain 自管,List 负责间距与自动滚动。
 */
import { useMemo } from 'react'
import { Bubble } from '@ant-design/x'
import { useChatStore } from '@/stores/chat'
import { buildBlocks } from '@/sdk/blocks'
import MessageItem from './MessageItem'
import StepChain from './StepChain'

const roleConfig = {
  ai: { variant: 'borderless' as const, placement: 'start' as const },
  user: { variant: 'borderless' as const, placement: 'end' as const },
}

export default function MessageList() {
  const store = useChatStore()
  const { messages, steps } = store.chat

  /* 渲染块编排:同 stepId 全局聚合(并行节点交错不拆步骤头),见 sdk/blocks.ts 单测 */
  const blocks = useMemo(() => buildBlocks(messages, steps), [messages, steps])

  const items = blocks.map(b =>
    b.kind === 'step'
      ? { key: b.key, role: b.role, content: <StepChain step={b.step} messages={b.messages} /> }
      : { key: b.key, role: b.role, content: <MessageItem msg={b.msg} /> },
  )

  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <div className="max-w-3xl mx-auto">
        <Bubble.List items={items} role={roleConfig} autoScroll />
      </div>
    </div>
  )
}
