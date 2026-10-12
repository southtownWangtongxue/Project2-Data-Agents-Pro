/**
 * ChatSidebar.tsx —— 会话侧栏(会话增删/重命名/长期目标)
 * 偏差说明:未用 antdx Conversations——需要 goal 编辑/标题重命名/跳轮次等
 * 业务扩展,其菜单 API 不足;视觉对齐 antdx Conversations 列表语言。
 */
import { useState } from 'react'
import { Modal, Input, message as antdMsg } from 'antd'
import { useChatStore } from '@/stores/chat'
import { api } from '@/api/client'

export default function ChatSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const store = useChatStore()
  const [goalOpen, setGoalOpen] = useState(false)
  const [goalText, setGoalText] = useState('')

  const openGoal = async () => {
    if (!store.chat.threadId) {
      antdMsg.info('新会话暂无目标,先发起一轮对话')
      return
    }
    try {
      const data = await api<{ goal: string }>(`/chat/sessions/${encodeURIComponent(store.chat.threadId)}/goal`)
      setGoalText(data.goal || '')
    } catch {
      setGoalText('')
    }
    setGoalOpen(true)
  }

  const saveGoal = async () => {
    try {
      await api(`/chat/sessions/${encodeURIComponent(store.chat.threadId)}/goal`, {
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

  if (collapsed) {
    return (
      <aside className="w-12 flex-shrink-0 border-r border-[var(--border)] flex flex-col items-center py-3 gap-3">
        <button type="button" onClick={onToggle} title="展开侧栏"
          className="w-8 h-8 rounded-md border border-[var(--border)] bg-transparent text-[var(--text-2)] cursor-pointer hover:text-[var(--text-1)]">
          →
        </button>
        <button type="button" onClick={() => store.newSession()} title="新建会话"
          className="w-8 h-8 rounded-md border border-brand/30 bg-brand/10 text-brand-light cursor-pointer">+</button>
      </aside>
    )
  }

  return (
    <aside className="w-64 flex-shrink-0 border-r border-[var(--border)] flex flex-col bg-[rgba(20,20,22,0.6)]">
      {/* 头部 */}
      <div className="flex items-center gap-2 px-3 h-12 border-b border-[var(--border)]">
        <span className="font-semibold text-[13px] text-[var(--text-1)]">会话</span>
        <div className="ml-auto flex gap-1">
          <button type="button" onClick={openGoal} title="会话长期目标"
            className="px-2 py-1 text-[11px] text-[var(--text-3)] bg-transparent border border-[var(--border)] rounded cursor-pointer hover:text-[var(--text-1)]">
            🎯 目标
          </button>
          <button type="button" onClick={() => store.newSession()} title="新建会话"
            className="px-2 py-1 text-[11px] text-brand-light bg-brand/10 border border-brand/25 rounded cursor-pointer hover:bg-brand/20">
            + 新建
          </button>
          <button type="button" onClick={onToggle} title="折叠侧栏"
            className="px-1.5 py-1 text-[11px] text-[var(--text-3)] bg-transparent border border-[var(--border)] rounded cursor-pointer">←</button>
        </div>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto py-2">
        {store.sessionsLoading && (
          <div className="px-3 py-2 text-[11px] text-[var(--text-3)]">加载中…</div>
        )}
        {!store.sessionsLoading && store.sessions.length === 0 && (
          <div className="px-3 py-6 text-center text-[11px] text-[var(--text-3)]">暂无会话,发起第一轮对话吧</div>
        )}
        {store.sessions.map(s => {
          const active = s.thread_id === store.chat.threadId
          return (
            <div
              key={s.thread_id}
              className={`group mx-2 mb-0.5 px-2.5 py-2 rounded-lg cursor-pointer transition-colors ${
                active ? 'bg-brand/10 border border-brand/25' : 'border border-transparent hover:bg-[var(--cockpit-800)]'
              }`}
              onClick={() => store.loadSession(s.thread_id)}
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[12px] text-[var(--text-1)] truncate flex-1">{s.title || '未命名会话'}</span>
                <span className="hidden group-hover:flex gap-1 flex-shrink-0">
                  <button type="button" title="重命名"
                    onClick={e => { e.stopPropagation(); rename(s.thread_id, s.title) }}
                    className="text-[10px] text-[var(--text-3)] hover:text-[var(--text-1)] bg-transparent border-none cursor-pointer">✎</button>
                  <button type="button" title="删除"
                    onClick={e => {
                      e.stopPropagation()
                      Modal.confirm({
                        title: '删除会话',
                        content: `确认删除「${s.title || '未命名会话'}」?该操作不可恢复。`,
                        okText: '删除',
                        okButtonProps: { danger: true },
                        cancelText: '取消',
                        onOk: () => store.deleteSession(s.thread_id),
                      })
                    }}
                    className="text-[10px] text-[var(--text-3)] hover:text-[#f87171] bg-transparent border-none cursor-pointer">✕</button>
                </span>
              </div>
              {s.question && (
                <div className="text-[10px] text-[var(--text-3)] truncate mt-0.5">{s.question}</div>
              )}
            </div>
          )
        })}
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
