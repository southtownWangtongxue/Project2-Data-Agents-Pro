/**
 * TurnNavigator.tsx —— 多轮对话节点切换(2026-10-18)
 *
 * 历史会话按轮次（node_index）切换查看：‹ 第 2/3 轮 › + 轮次下拉。
 * MessageList 依据 currentTurnIndex 过滤消息（带 turn_index 的历史消息）；
 * 旧会话没有 turn_index 时导航条不出现、消息平铺（向后兼容）。
 */
import { Dropdown } from 'antd'
import Icon from '@/components/bits/Icon'
import { useChatStore } from '@/stores/chat'

export default function TurnNavigator() {
  const store = useChatStore()
  const { turns, currentTurnIndex } = store
  const { messages } = store.chat

  /** 只有历史投影带 turn_index 时才启用轮次切换（实时会话/旧数据不外显） */
  const hasTurnInfo = messages.some(m => typeof m.turnIndex === 'number')
  if (!hasTurnInfo || turns.length <= 1) return null

  const total = turns.length
  const idx = Math.min(Math.max(currentTurnIndex, 0), total - 1)
  const current = turns.find(t => t.index === idx) || turns[idx]
  const go = (next: number) => {
    if (next < 0 || next >= total) return
    store.setTurnIndex(next)
  }

  const menuItems = turns.map((t, i) => ({
    key: String(t.index),
    label: (
      <span className="flex items-center gap-2 text-[13px]">
        <span className="mono text-[11.5px] text-[var(--text-3)]">{i + 1}</span>
        <span className="truncate max-w-[320px] text-[var(--text-1)]">{t.title || t.question || `第 ${i + 1} 轮`}</span>
      </span>
    ),
  }))

  return (
    <div className="w-full max-w-[840px] mx-auto px-4 pt-3 flex-shrink-0">
      <div
        className="flex items-center gap-1.5 h-9 px-2 rounded-lg w-fit"
        style={{ background: 'var(--cockpit-800)', border: '1px solid var(--border)' }}
      >
        <button
          type="button"
          onClick={() => go(idx - 1)}
          disabled={idx <= 0}
          title="上一轮"
          className="w-6 h-6 rounded-md bg-transparent border-none cursor-pointer flex items-center justify-center text-[var(--text-3)] hover:text-[var(--text-1)] hover:bg-white/[0.06] transition-colors disabled:opacity-35 disabled:cursor-not-allowed"
        >
          <Icon name="arrowLeft" size={14} />
        </button>
        <Dropdown
          trigger={['click']}
          menu={{ items: menuItems, onClick: ({ key }) => go(Number(key)) }}
          placement="bottom"
        >
          <button
            type="button"
            className="flex items-center gap-1.5 px-2 h-6 rounded-md bg-transparent border-none cursor-pointer text-[var(--text-2)] hover:text-[var(--text-1)] hover:bg-white/[0.06] transition-colors max-w-[420px]"
          >
            <span className="mono text-[11.5px] text-[var(--text-3)] flex-shrink-0">第 {idx + 1}/{total} 轮</span>
            <span className="text-[13px] truncate">{current?.title || current?.question || '当前轮次'}</span>
            <Icon name="arrowDown" size={12} className="flex-shrink-0 text-[var(--text-3)]" />
          </button>
        </Dropdown>
        <button
          type="button"
          onClick={() => go(idx + 1)}
          disabled={idx >= total - 1}
          title="下一轮"
          className="w-6 h-6 rounded-md bg-transparent border-none cursor-pointer flex items-center justify-center text-[var(--text-3)] hover:text-[var(--text-1)] hover:bg-white/[0.06] transition-colors disabled:opacity-35 disabled:cursor-not-allowed"
        >
          <Icon name="arrowRight" size={14} />
        </button>
      </div>
    </div>
  )
}
