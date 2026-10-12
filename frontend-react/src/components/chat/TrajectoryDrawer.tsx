/**
 * TrajectoryDrawer.tsx —— 会话轨迹抽屉(事件溯源时间线)
 */
import { useEffect, useState } from 'react'
import { Drawer, Spin, Empty } from 'antd'
import { api } from '@/api/client'
import { useChatStore } from '@/stores/chat'

interface TrajEvent {
  id: number
  event_type: string
  role: string | null
  content: string
  node_index: number
  created_at: string | null
}

const TYPE_DOT: Record<string, string> = {
  user_message: '#7056F8',
  plan: '#8B6FFF',
  sql: '#F59E0B',
  result: '#10B981',
  analysis: '#10B981',
  chart: '#10B981',
  tool_chain: '#71717A',
  error: '#EF4444',
  turn_start: '#3f3f46',
  turn_end: '#3f3f46',
  clarification: '#8B6FFF',
}

export default function TrajectoryDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const store = useChatStore()
  const [events, setEvents] = useState<TrajEvent[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !store.chat.threadId) return
    setLoading(true)
    api<TrajEvent[]>(`/chat/sessions/${encodeURIComponent(store.chat.threadId)}/trajectory`)
      .then(setEvents)
      .catch(() => setEvents([]))
      .finally(() => setLoading(false))
  }, [open, store.chat.threadId])

  return (
    <Drawer
      title="会话轨迹(事件溯源)"
      open={open}
      onClose={onClose}
      size={420}
      styles={{ body: { background: 'var(--cockpit-900)' } }}
    >
      {loading ? (
        <div className="flex justify-center py-10"><Spin /></div>
      ) : events.length === 0 ? (
        <Empty description="暂无轨迹事件" />
      ) : (
        <ol className="relative m-0 p-0 list-none">
          {/* 竖轨 */}
          <span className="absolute left-[5px] top-2 bottom-2 w-px bg-[var(--border)]" />
          {events.map(ev => (
            <li key={ev.id} className="relative pl-6 pb-4 last:pb-0">
              <span
                className="absolute left-0 top-1.5 w-[11px] h-[11px] rounded-full border-2 border-[var(--cockpit-900)]"
                style={{ background: TYPE_DOT[ev.event_type] || '#71717A' }}
              />
              <div className="flex items-baseline gap-2">
                <span className="mono text-[11px] text-brand-light">{ev.event_type}</span>
                <span className="text-[10px] text-[var(--text-3)] mono">turn {ev.node_index}</span>
                {ev.created_at && (
                  <span className="text-[10px] text-[var(--text-3)] mono ml-auto">
                    {new Date(ev.created_at).toLocaleTimeString('zh-CN', { hour12: false })}
                  </span>
                )}
              </div>
              {ev.content && (
                <div className="text-[12px] text-[var(--text-2)] mt-0.5 line-clamp-2">{ev.content}</div>
              )}
            </li>
          ))}
        </ol>
      )}
    </Drawer>
  )
}
