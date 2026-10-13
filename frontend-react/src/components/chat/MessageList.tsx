/**
 * MessageList.tsx —— 消息列表(antdx Bubble.List)
 *
 * 对齐官方独立式样板间:
 * - 容器 max-width 940 居中,间距交给 Bubble.List,内容超长自动滚动
 * - role 配置:user = placement end / filled / corner;ai = placement start
 * - 领域块(步骤链、SQL 卡、结果表、图表、审批卡…)以 borderless item 承载,
 *   视觉完全由各卡片自管,List 只负责节奏
 */
import { useMemo } from 'react'
import { Bubble, type BubbleItemType, type BubbleListProps } from '@ant-design/x'
import { useChatStore } from '@/stores/chat'
import { buildBlocks } from '@/sdk/blocks'
import MessageItem from './MessageItem'
import StepChain from './StepChain'

const roleConfig: BubbleListProps['role'] = {
  user: { placement: 'end', variant: 'filled', shape: 'corner' },
  ai: { placement: 'start', variant: 'borderless' },
}

export default function MessageList() {
  const store = useChatStore()
  const { messages, steps } = store.chat

  /* 渲染块编排:同 stepId 全局聚合(并行节点交错不拆步骤头),见 sdk/blocks.ts 单测 */
  const blocks = useMemo(() => buildBlocks(messages, steps), [messages, steps])

  const items: BubbleItemType[] = blocks.map(b => {
    /* 用户消息:直接交给 Bubble 的 filled 气泡渲染 */
    if (b.kind === 'msg' && b.role === 'user') {
      return { key: b.key, role: 'user', content: b.msg.content || '' }
    }
    if (b.kind === 'msg') {
      return { key: b.key, role: 'ai', variant: 'borderless', content: <MessageItem msg={b.msg} /> }
    }
    return {
      key: b.key,
      role: 'ai',
      variant: 'borderless',
      content: <StepChain step={b.step} messages={b.messages} />,
    }
  })

  return (
    <div className="w-full h-full overflow-y-auto px-4 py-4">
      <div className="mx-auto w-full" style={{ maxWidth: 940 }}>
        <Bubble.List items={items} role={roleConfig} autoScroll />
      </div>
    </div>
  )
}