/**
 * MessageItem.tsx —— 单条领域消息分发(14 类 kind)
 * 富渲染子组件各自独立文件;本文件只做路由与通用外壳。
 */
import { useChatStore } from '@/stores/chat'
import type { Msg } from '@/sdk/protocol'
import SQLCard from './SQLCard'
import ResultTable from './ResultTable'
import ChartView from './ChartView'
import ToolCard from './ToolCard'
import ReasoningCard from './ReasoningCard'
import ApprovalCard from './ApprovalCard'
import ClarifyCard from './ClarifyCard'
import PlanCard from './PlanCard'
import SubagentNode from './SubagentNode'
import ErrorCard from './ErrorCard'
import { XMarkdown } from '@ant-design/x-markdown'

export default function MessageItem({ msg }: { msg: Msg }) {
  const store = useChatStore()

  switch (msg.kind) {
    case 'text':
      if (msg.role === 'user') {
        return (
          <div className="flex justify-end">
            <div className="max-w-[72%] px-4 py-2.5 rounded-2xl rounded-br-sm text-white text-[15px] leading-relaxed whitespace-pre-wrap shadow-lg"
              style={{ background: 'linear-gradient(135deg,#7056F8,#818CF8)' }}>
              {msg.content}
            </div>
          </div>
        )
      }
      return (
        <div className="flex justify-start">
          <div
            className={`max-w-[72%] px-4 py-3 rounded-2xl rounded-bl-sm bg-[var(--cockpit-800)] border border-[var(--border)] text-[15px] ${
              store.isLoading && msg.id === store.chat.lastAssistantMsgId ? 'is-streaming' : ''
            }`}
          >
            <XMarkdown content={msg.content || ''} />
          </div>
        </div>
      )

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
      return (
        <div className="max-w-[82%] bg-[var(--cockpit-800)] border border-[var(--border)] border-l-2 border-l-brand rounded-r-md px-3 py-2 text-xs text-[var(--text-2)] cursor-pointer"
          onClick={() => { msg.collapsed = !msg.collapsed }}>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-[var(--text-1)]">{msg.agent}</span>
            <span className="text-[var(--text-3)]">{msg.phase}</span>
          </div>
          {!msg.collapsed && msg.content && (
            <div className="mt-1.5 whitespace-pre-wrap leading-relaxed">{msg.content}</div>
          )}
        </div>
      )

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
