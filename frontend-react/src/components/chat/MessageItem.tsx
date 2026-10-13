/**
 * MessageItem.tsx —— 单条领域消息分发(14 类 kind)
 *
 * 气泡语言统一交给 Ant Design X:
 * - 文本走 Bubble(filled / corner),正文用 x-markdown 流式渲染,底部挂 Actions
 * - SQL / 结果 / 图表 / 工具 / 审批等富卡片保持 borderless 自绘,只借用间距节奏
 */
import { useState } from 'react'
import { Bubble, Think } from '@ant-design/x'
import { XMarkdown } from '@ant-design/x-markdown'
import { useChatStore } from '@/stores/chat'
import type { Msg } from '@/sdk/protocol'
import MessageActions from './MessageActions'
import SQLCard from './SQLCard'
import ResultTable from './ResultTable'
import ChartView from './ChartView'
import ToolCard from './ToolCard'
import ReasoningCard from './ReasoningCard'
import ApprovalCard from './ApprovalCard'
import ClarifyCard from './ClarifyCard'
import PlanCard from './PlanCard'
import ErrorCard from './ErrorCard'

/** 节点思考块(antdx Think):默认折叠,点击标题展开 */
function ThinkingBlock({ msg }: { msg: Msg }) {
  const [expanded, setExpanded] = useState(false)
  const running = msg.phase !== 'done'
  return (
    <Think
      title={`${msg.agent || '节点'} · ${msg.phase || ''}`}
      loading={running}
      expanded={expanded}
      onExpand={setExpanded}
      blink={running}
    >
      {msg.content}
    </Think>
  )
}

export default function MessageItem({ msg }: { msg: Msg }) {
  const store = useChatStore()

  switch (msg.kind) {
    case 'text': {
      /* 用户消息(兜底:正常路径由 MessageList 的 filled 气泡渲染) */
      if (msg.role === 'user') {
        return (
          <Bubble
            placement="end"
            shape="corner"
            variant="filled"
            content={msg.content || ''}
            styles={{ content: { whiteSpace: 'pre-wrap' } }}
          />
        )
      }
      const streaming = store.isLoading && msg.id === store.chat.lastAssistantMsgId
      const content = msg.content || ''
      return (
        <Bubble
          placement="start"
          variant="filled"
          streaming={streaming}
          content={content}
          contentRender={text => (
            <XMarkdown
              className="x-markdown"
              content={String(text)}
              streaming={{
                hasNextChunk: streaming,
                enableAnimation: true,
                tail: streaming,
              }}
            />
          )}
          footer={streaming ? undefined : () => <MessageActions msg={msg} content={content} />}
          styles={{ footer: { marginTop: 6 } }}
        />
      )
    }

    case 'sql':
      return <SQLCard msg={msg} />

    case 'result':
      return <ResultTable msg={msg} />

    case 'chart':
      return <ChartView msg={msg} />

    case 'tool':
      /* misc 工具卡与正文去重:结果即正文的 misc_agent 工具卡降级为状态点 */
      if (msg.toolName === 'misc_agent') {
        return (
          <div className="text-[11px] text-[var(--text-3)] mono px-1">
            {msg.toolPhase === 'done' ? '✓ 已回答' : '… 生成回答中'}
          </div>
        )
      }
      return <ToolCard msg={msg} />

    case 'reasoning':
      /* thinking_mode 关闭时仅隐藏(消息仍在 store,切回可见) */
      if (!store.thinkingModeEnabled) return null
      return <ReasoningCard msg={msg} />

    case 'thinking':
      return <ThinkingBlock msg={msg} />

    case 'approval':
      return <ApprovalCard msg={msg} />

    case 'clarification':
      return <ClarifyCard msg={msg} />

    case 'plan':
      /* 空步骤不渲染计划卡(修复"无执行步骤"空卡) */
      if (!msg.planSteps || msg.planSteps.length === 0) return null
      return <PlanCard msg={msg} />

    case 'error':
      return <ErrorCard msg={msg} />

    case 'status':
      return (
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-[13px] text-brand-light"
          style={{ background: 'rgba(112,86,248,0.1)', border: '1px solid rgba(112,86,248,0.2)' }}>
          <span className="w-2 h-2 rounded-full bg-brand brand-pulse" />
          {msg.content}
        </div>
      )

    default:
      return null
  }
}