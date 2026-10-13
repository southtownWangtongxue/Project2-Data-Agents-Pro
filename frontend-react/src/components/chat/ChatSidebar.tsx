/**
 * ChatSidebar.tsx —— 会话侧栏(antdx Conversations + 侧栏底部账户区)
 *
 * 结构对齐官方独立式样板间 side:logo 区 → Conversations(flex-1) → sideFooter。
 * 业务扩展:会话长期目标(goal)以菜单项形式挂在会话上。
 */
import { useMemo, useState } from 'react'
import { Modal, Input, message as antdMsg, Tooltip } from 'antd'
import { Conversations } from '@ant-design/x'
import { Pencil, Target, Trash2 } from 'lucide-react'
import { useChatStore, type SessionInfo } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { api } from '@/api/client'

const GROUP_TODAY = '今天'
const GROUP_YESTERDAY = '昨天'
const GROUP_EARLIER = '更早'

function groupOf(s: SessionInfo): string {
  if (!s.created_at) return GROUP_EARLIER
  const d = new Date(s.created_at)
  const today = new Date()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  const ts = d.getTime()
  if (ts >= startOfToday) return GROUP_TODAY
  if (ts >= startOfToday - 24 * 3600 * 1000) return GROUP_YESTERDAY
  return GROUP_EARLIER
}

export default function ChatSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const store = useChatStore()
  const auth = useAuthStore()
  const theme = useThemeStore()
  const [goalOpen, setGoalOpen] = useState(false)
  const [goalText, setGoalText] = useState('')
  const [goalThread, setGoalThread] = useState<string>('')

  /** 按「今天/昨天/更早」分组,组内保持接口返回的倒序 */
  const items = useMemo(() => {
    const grouped = new Map<string, { key: string; label: string; group: string }[]>()
    for (const s of store.sessions) {
      const g = groupOf(s)
      if (!grouped.has(g)) grouped.set(g, [])
      grouped.get(g)!.push({ key: s.thread_id, label: s.title || '未命名会话', group: g })
    }
    return [...grouped.entries()].flatMap(([, list]) => list)
  }, [store.sessions])

  const openGoal = async (threadId: string) => {
    if (!threadId) {
      antdMsg.info('新会话暂无目标,先发起一轮对话')
      return
    }
    try {
      const data = await api<{ goal: string }>(`/chat/sessions/${encodeURIComponent(threadId)}/goal`)
      setGoalText(data.goal || '')
    } catch {
      setGoalText('')
    }
    setGoalThread(threadId)
    setGoalOpen(true)
  }

  const saveGoal = async () => {
    try {
      await api(`/chat/sessions/${encodeURIComponent(goalThread)}/goal`, {
        method: 'PUT',
        body: { goal: goalText },
      })
      antdMsg.success('目标已保存')
      setGoalOpen(false)
    } catch {
      antdMsg.error('保存失败')
    }
  }

  const rename = async (threadId: string, old: string) => {
    const title = window.prompt('修改会话标题', old)
    if (!title || title === old) return
    await store.editSessionTitle(threadId, title)
  }

  const labelText = (label?: React.ReactNode) =>
    typeof label === 'string' ? label : '未命名会话'

  const remove = (threadId: string, title: string) => {
    Modal.confirm({
      title: '删除会话',
      content: `确认删除「${title || '未命名会话'}」?该操作不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => store.deleteSession(threadId),
    })
  }

  /* 折叠态:仅保留图标条 */
  if (collapsed) {
    return (
      <aside
        className="h-full w-12 flex-shrink-0 flex flex-col items-center gap-3 py-4 border-r"
        style={{ borderColor: 'var(--border)', background: 'var(--panel)' }}
      >
        <span className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-[13px] font-bold"
          style={{ background: 'linear-gradient(135deg,#7056F8,#8B6FFF)' }}>D</span>
        <Tooltip title="展开侧栏" placement="right">
          <button type="button" onClick={onToggle}
            className="w-8 h-8 rounded-md border bg-transparent cursor-pointer text-[var(--text-2)] hover:text-[var(--text-1)] transition-colors"
            style={{ borderColor: 'var(--border)' }}>→</button>
        </Tooltip>
        <Tooltip title="新建会话" placement="right">
          <button type="button" onClick={() => store.newSession()} title="新建会话"
            className="w-8 h-8 rounded-md border cursor-pointer text-[var(--brand-light)] transition-colors"
            style={{ borderColor: 'rgba(112,86,248,0.35)', background: 'rgba(112,86,248,0.12)' }}>+</button>
        </Tooltip>
      </aside>
    )
  }

  return (
    <aside
      className="h-full w-[280px] flex-shrink-0 flex flex-col px-3 box-border"
      style={{ background: 'var(--panel)' }}
    >
      {/* 🌟 logo 区 */}
      <div className="flex items-center gap-2 py-6 px-6 box-border">
        <span className="w-6 h-6 rounded-md flex items-center justify-center text-white text-[13px] font-bold flex-shrink-0"
          style={{ background: 'linear-gradient(135deg,#7056F8,#8B6FFF)' }}>D</span>
        <span className="font-bold text-[16px] text-[var(--text-1)] truncate">DataAgent Pro</span>
        <Tooltip title="折叠侧栏" placement="right">
          <button type="button" onClick={onToggle} title="折叠侧栏"
            className="ml-auto w-6 h-6 rounded border bg-transparent cursor-pointer text-[var(--text-3)] hover:text-[var(--text-1)] transition-colors"
            style={{ borderColor: 'var(--border)' }}>←</button>
        </Tooltip>
      </div>

      {/* 🌟 会话管理 */}
      {items.length === 0 && !store.sessionsLoading ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-1 text-center">
          <span className="text-[12px] text-[var(--text-3)]">暂无会话</span>
          <span className="text-[11px] text-[var(--text-3)] opacity-70">发起第一轮对话后自动归档</span>
        </div>
      ) : (
        <Conversations
          className="flex-1 min-h-0 overflow-y-auto mt-3"
          style={{ padding: 0 }}
          activeKey={store.chat.threadId || undefined}
          onActiveChange={key => key && store.loadSession(String(key))}
          groupable
          creation={{
            onClick: () => {
              if (store.chat.messages.length === 0 && store.sessions.length === 0) {
                antdMsg.info('已经是新会话,直接提问即可')
                return
              }
              store.newSession()
            },
          }}
          items={items}
          styles={{ item: { padding: '0 8px' } }}
          menu={conversation => ({
            items: [
              {
                key: 'rename',
                label: '重命名',
                icon: <Pencil size={14} />,
                onClick: () => rename(String(conversation.key), labelText(conversation.label)),
              },
              {
                key: 'goal',
                label: '长期目标',
                icon: <Target size={14} />,
                onClick: () => openGoal(String(conversation.key)),
              },
              {
                key: 'delete',
                label: '删除',
                icon: <Trash2 size={14} />,
                danger: true,
                onClick: () => remove(String(conversation.key), labelText(conversation.label)),
              },
            ],
          })}
        />
      )}

      {/* 🌟 侧栏底部:账户 / 主题 / 目标 */}
      <div
        className="h-10 flex items-center justify-between border-t mt-3 pt-3 pb-3"
        style={{ borderColor: 'var(--border)' }}
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className="w-6 h-6 rounded-full flex items-center justify-center text-[11px] text-white flex-shrink-0"
            style={{ background: 'linear-gradient(135deg,#3f3f46,#52525b)' }}>
            {(auth.user?.nick_name || auth.user?.user_name || 'U').slice(0, 1).toUpperCase()}
          </span>
          <span className="text-[12px] text-[var(--text-2)] truncate">
            {auth.user?.nick_name || auth.user?.user_name || '未登录'}
          </span>
        </span>
        <span className="flex items-center gap-1">
          <Tooltip title="切换主题">
            <button type="button" onClick={theme.toggle} title="切换明暗主题"
              className="w-7 h-7 rounded-md border bg-transparent cursor-pointer text-[var(--text-2)] hover:text-[var(--text-1)] transition-colors"
              style={{ borderColor: 'var(--border)' }}>
              {theme.mode === 'dark' ? '☾' : '☀'}
            </button>
          </Tooltip>
        </span>
      </div>

      {/* 长期目标编辑 */}
      <Modal
        title="会话长期目标"
        open={goalOpen}
        onOk={saveGoal}
        onCancel={() => setGoalOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Input.TextArea
          rows={4}
          value={goalText}
          onChange={e => setGoalText(e.target.value)}
          placeholder="例如:围绕月度经营分析,所有回答都聚焦华东区数据"
          maxLength={2000}
        />
        <div className="text-[11px] text-[var(--text-3)] mt-1">目标将在下一轮对话时注入系统提示词</div>
      </Modal>
    </aside>
  )
}