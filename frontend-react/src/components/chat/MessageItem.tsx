/**
 * MessageItem.tsx —— 单条领域消息分发(14 类 kind)
 *
 * 气泡语言统一交给 Ant Design X:
 * - 文本走 Bubble(filled / corner),正文用 x-markdown 流式渲染,底部挂 Actions
 * - SQL / 结果 / 图表 / 工具 / 审批等富卡片保持 borderless 自绘,只借用间距节奏
 */
import { useState } from 'react'
import { Bubble, Think } from '@ant-design/x'
import Icon from '@/components/bits/Icon'
import { useChatStore } from '@/stores/chat'
import type { Msg } from '@/sdk/protocol'
import Markdown from '@/components/bits/Markdown'
import MessageActions from './MessageActions'
import SQLCard from './SQLCard'
import ResultTable from './ResultTable'
import ChartView from './ChartView'
import ToolCard from './ToolCard'
import DeepThink from './DeepThink'
import ApprovalCard from './ApprovalCard'
import ClarifyCard from './ClarifyCard'
import PlanCard from './PlanCard'
import ErrorCard from './ErrorCard'

/**
 * 收集该 reasoning 消息所属「一次回复」的全部思考段落(多轮列表)。
 * 只由该回复的**第一条** reasoning 渲染 DeepThink,其余返回 null 避免重复;
 * 分界:最近一条 user 消息之后。
 */
function collectRounds(messages: Msg[], msg: Msg, turnIndex: number): string[] | null {
  const idx = messages.findIndex(m => m.id === msg.id)
  if (idx < 0) return null
  let start = 0
  for (let i = idx; i >= 0; i--) {
    if (messages[i].role === 'user') { start = i + 1; break }
  }
  /* 多轮切换:只聚合当前轮次的思考(旧数据无 turnIndex 则不限) */
  const hasTurnInfo = messages.some(m => typeof m.turnIndex === 'number')
  const inTurn = (m: Msg) => !hasTurnInfo || m.turnIndex === undefined || m.turnIndex === turnIndex
  const rounds: string[] = []
  let firstId: string | null = null
  for (let i = start; i < messages.length; i++) {
    const m = messages[i]
    if (m.kind !== 'reasoning' || !inTurn(m)) continue
    if (!firstId) firstId = m.id
    if ((m.content || '').trim()) rounds.push(m.content || '')
  }
  if (firstId !== msg.id) return null
  return rounds
}

/** 节点思考块(antdx Think):运行中自动展开(实时可见),完成后可折叠 */
function ThinkingBlock({ msg }: { msg: Msg }) {
  const running = msg.phase !== 'done'
  const [userSet, setUserSet] = useState<boolean | null>(null)
  const expanded = userSet !== null ? userSet : running
  return (
    <Think
      icon={<Icon name="brain" size={13} />}
      title={`节点思考 · ${msg.agent || 'agent'}${msg.phase ? ` · ${msg.phase}` : ''}`}
      loading={running}
      expanded={expanded}
      onExpand={setUserSet}
      blink={running}
    >
      <Markdown content={msg.content || ''} />
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
            <Markdown
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
            <span className="inline-flex items-center gap-1">
              <Icon name={msg.toolPhase === 'done' ? 'check' : 'loader'} size={10} className={msg.toolPhase === 'done' ? '' : 'animate-spin'} />
              {msg.toolPhase === 'done' ? '已回答' : '生成回答中'}
            </span>
          </div>
        )
      }
      return <ToolCard msg={msg} />

    case 'reasoning': {
      /* 思考模式开关(默认关):关闭时仅隐藏,消息仍在 store,切回可见 */
      if (!store.thinking) return null
      /* 2026-10-18:一次回复的全部思考段落聚合成一个「深度思考」多轮列表 */
      const rounds = collectRounds(store.chat.messages, msg, store.currentTurnIndex)
      if (!rounds || rounds.length === 0) return null
      return <DeepThink rounds={rounds} working={store.isGenerating} />
    }

    case 'thinking':
      /* 与 reasoning 同受思考开关控制(历史恢复的思考块一并隐藏/展示) */
      if (!store.thinking) return null
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