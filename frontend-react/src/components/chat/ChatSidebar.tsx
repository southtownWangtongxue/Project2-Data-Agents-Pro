/**
 * ChatSidebar.tsx —— 会话侧栏(antdx Conversations + 账户菜单)
 *
 * 2026-10-18 定版(按验收反馈):
 * - **取消归档**:移除归档分组、单条归档菜单、批量归档(后端接口保留,前端不再使用)
 * - **会话管理重做**:内嵌批量操作条(按钮挤压换行、易误点)改为独立的
 *   「选择对话」弹窗(SessionPickerModal),支持全选/分组/删除
 * - 保留:分组计数 + 组折叠(localStorage 记忆)、滚动触底分页、重命名、长期目标、删除
 */
import { useMemo, useState } from 'react'
import { Modal, Input, message as antdMsg, Tooltip } from 'antd'
import { Conversations } from '@ant-design/x'
import Icon from '@/components/bits/Icon'
import { useChatStore, type SessionInfo } from '@/stores/chat'
import { api } from '@/api/client'
import AccountMenu from './AccountMenu'
import SessionPickerModal from './SessionPickerModal'
import ShinyText from '@/components/bits/reactbits/ShinyText'

const GROUP_TODAY = '今天'
const GROUP_YESTERDAY = '昨天'
const GROUP_WEEK = '7天内'
const GROUP_MONTH = '30天内'
const GROUP_EARLIER = '更早'
const GROUP_ORDER = [GROUP_TODAY, GROUP_YESTERDAY, GROUP_WEEK, GROUP_MONTH, GROUP_EARLIER]
const COLLAPSE_STORAGE_KEY = 'sidebarCollapsedGroups'
/** 滚动触底加载的预触发距离(px) */
const SCROLL_PREFETCH = 80

/** 分组对齐 dsh:今天 / 昨天 / 7天内 / 30天内 / 更早 */
function groupOf(s: SessionInfo): string {
  if (!s.created_at) return GROUP_EARLIER
  const ts = new Date(s.created_at).getTime()
  const now = Date.now()
  const startOfToday = new Date(now)
  startOfToday.setHours(0, 0, 0, 0)
  if (ts >= startOfToday.getTime()) return GROUP_TODAY
  if (ts >= startOfToday.getTime() - 86400_000) return GROUP_YESTERDAY
  if (ts >= now - 7 * 86400_000) return GROUP_WEEK
  if (ts >= now - 30 * 86400_000) return GROUP_MONTH
  return GROUP_EARLIER
}

function loadCollapsedGroups(): string[] {
  try {
    const raw = localStorage.getItem(COLLAPSE_STORAGE_KEY)
    if (raw) return JSON.parse(raw) as string[]
  } catch { /* 损坏的本地存储回退默认 */ }
  return [GROUP_EARLIER] // 更早默认折叠
}

export default function ChatSidebar() {
  const store = useChatStore()
  const [goalOpen, setGoalOpen] = useState(false)
  const [goalText, setGoalText] = useState('')
  const [goalThread, setGoalThread] = useState<string>('')
  /* 「选择对话」批量删除弹窗 */
  const [pickerOpen, setPickerOpen] = useState(false)
  /* 组折叠态(受控:展开键取反,localStorage 记忆) */
  const [collapsedGroups, setCollapsedGroups] = useState<string[]>(loadCollapsedGroups)

  /** 按「今天/昨天/更早」分组,组内保持接口返回的倒序 */
  const grouped = useMemo(() => {
    const map = new Map<string, { key: string; label: string; group: string }[]>()
    for (const s of store.sessions) {
      const g = groupOf(s)
      if (!map.has(g)) map.set(g, [])
      map.get(g)!.push({ key: s.thread_id, label: s.title || '未命名会话', group: g })
    }
    return map
  }, [store.sessions])

  const items = useMemo(() => {
    const out: { key: string; label: string; group: string }[] = []
    for (const g of GROUP_ORDER) {
      for (const it of grouped.get(g) || []) {
        out.push({ key: it.key, group: g, label: it.label })
      }
    }
    return out
  }, [grouped])

  /** groupable:组标题带计数;折叠态受控并持久化 */
  const groupable = useMemo(() => {
    const presentGroups = [...grouped.keys()]
    return {
      label: (group: string, info: { groupInfo: { data: unknown[] } }) => (
        <span className="flex items-center gap-1.5">
          <span className="text-[12.5px] text-[var(--text-2)]">{group}</span>
          <span className="mono text-[11.5px] text-[var(--text-3)]">{info.groupInfo.data.length}</span>
        </span>
      ),
      collapsible: true,
      expandedKeys: presentGroups.filter(g => !collapsedGroups.includes(g)),
      onExpand: (keys: string[]) => {
        const next = presentGroups.filter(g => !keys.includes(g))
        setCollapsedGroups(next)
        try { localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(next)) } catch { /* 忽略存储失败 */ }
      },
    }
  }, [grouped, collapsedGroups])

  /** 滚动触底 → 加载下一页 */
  const onListScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - SCROLL_PREFETCH) {
      store.loadMoreSessions()
    }
  }

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
      onOk: async () => {
        try {
          await store.deleteSession(threadId)
          antdMsg.success(`已删除「${title || '未命名会话'}」`)
        } catch (e) {
          /* 删除失败必须可见:失败被吞会让人误以为已删、刷新又出现 */
          antdMsg.error(`删除失败: ${(e as Error).message || '未知错误'}`)
          throw e
        }
      },
    })
  }

  const emptyList = items.length === 0 && !store.sessionsLoading

  return (
    <aside
      className="h-full w-[280px] flex-shrink-0 flex flex-col px-3 box-border"
      style={{ background: 'var(--panel)' }}
    >
      {/* 🌟 logo 区 + 会话管理入口 */}
      <div className="flex items-center gap-2 py-6 px-6 box-border">
        <img src="/logo.png" alt="" className="w-6 h-6 rounded-md flex-shrink-0" />
        <ShinyText
          text="DataAgent Pro"
          color="#ECECF1"
          shineColor="#C4B5FD"
          speed={3.2}
          delay={1.5}
          shineWidth={26}
          softness={0.9}
          glow={0.3}
          trigger="view"
          className="font-bold text-[16px] truncate"
        />
        {!emptyList && (
          <Tooltip title="选择对话（批量删除）" placement="bottom">
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              title="选择对话"
              className="ml-auto w-7 h-7 rounded-lg bg-transparent border-none cursor-pointer text-[var(--text-3)] hover:text-[var(--text-1)] hover:bg-white/[0.06] transition-colors flex items-center justify-center"
            >
              <Icon name="listCheck" size={16} />
            </button>
          </Tooltip>
        )}
      </div>

      {/* 🌟 会话列表 */}
      {emptyList ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-1 text-center">
          <span className="text-[13px] text-[var(--text-2)]">暂无会话</span>
          <span className="text-[12px] text-[var(--text-3)]">在输入框提问即可开始第一个对话</span>
        </div>
      ) : (
        /* 滚动容器:触底预加载下一页 */
        <div className="flex-1 min-h-0 overflow-y-auto mt-1" onScroll={onListScroll}>
          <Conversations
            style={{ padding: 0 }}
            activeKey={store.chat.threadId || undefined}
            onActiveChange={key => {
              if (!key) return
              store.loadSession(String(key))
            }}
            groupable={groupable}
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
                  icon: <Icon name="edit" size={16} />,
                  onClick: () => rename(String(conversation.key), labelText(conversation.label)),
                },
                {
                  key: 'goal',
                  label: '长期目标',
                  icon: <Icon name="target" size={16} />,
                  onClick: () => openGoal(String(conversation.key)),
                },
                {
                  key: 'delete',
                  label: '删除',
                  icon: <Icon name="trash" size={16} />,
                  danger: true,
                  onClick: () => remove(String(conversation.key), labelText(conversation.label)),
                },
              ],
            })}
          />
          {/* 滚动加载指示 */}
          {store.sessionsLoadingMore && (
            <div className="flex justify-center py-3 text-[12px] text-[var(--text-3)]">加载中…</div>
          )}
          {!store.sessionsHasMore && store.sessions.length > 0 && (
            <div className="flex justify-center py-3 text-[12px] text-[var(--text-3)]">已加载全部会话</div>
          )}
        </div>
      )}

      {/* 🌟 侧栏底部:账户菜单(只保留深色,无分隔线) */}
      <div className="flex items-center gap-1 mt-2 pb-3">
        <AccountMenu />
      </div>

      {/* 选择对话(批量删除) */}
      <SessionPickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} />

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
        <div className="text-[12px] text-[var(--text-3)] mt-1">目标将在下一轮对话时注入系统提示词</div>
      </Modal>
    </aside>
  )
}
