/**
 * ReasoningCard.tsx —— 思考内容折叠卡(antdx Think,与官方思考态视觉语言一致)
 * thinking_mode 关闭时由 MessageItem 隐藏(消息仍在 store,切回可见)。
 */
import { useState } from 'react'
import { Think } from '@ant-design/x'
import { Brain } from 'lucide-react'
import type { Msg } from '@/sdk/protocol'

export default function ReasoningCard({ msg }: { msg: Msg }) {
  const [expanded, setExpanded] = useState(false)
  const length = (msg.content || '').length

  return (
    <Think
      title={`思考过程 · ${length} 字`}
      icon={<Brain size={13} />}
      expanded={expanded}
      onExpand={setExpanded}
      styles={{ content: { fontSize: 12, color: 'var(--text-2)', whiteSpace: 'pre-wrap' } }}
    >
      {msg.content}
    </Think>
  )
}