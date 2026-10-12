/**
 * pages/Chat.tsx —— 对话主区(chat-core)
 * 顶栏(模型/模式/轨迹入口) + 消息列表(Bubble.List) + 输入区。
 * 输入区完整形态(Sender/chips/Welcome)在 input-sessions 阶段替换。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input } from 'antd'
import { getToken } from '@/api/client'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import MessageList from '@/components/chat/MessageList'

const MODES = [
  { key: 'data', label: '数据分析' },
  { key: 'report', label: '研究报告' },
  { key: 'doc', label: '文档智读' },
  { key: 'task', label: '通用任务' },
]

export default function Chat() {
  const navigate = useNavigate()
  const store = useChatStore()
  const auth = useAuthStore()
  const [text, setText] = useState('')

  useEffect(() => {
    if (!getToken()) {
      navigate('/login', { replace: true })
      return
    }
    auth.restore()
    store.loadSessions()
    store.loadSuggestions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const send = () => {
    if (!text.trim()) return
    store.sendMessage(text.trim())
    setText('')
  }

  const empty = store.chat.messages.length === 0

  return (
    <div className="h-full flex flex-col bg-[var(--cockpit-900)]">
      {/* 顶栏 */}
      <header className="h-12 flex items-center gap-3 px-4 border-b border-[var(--border)] flex-shrink-0">
        <span className="font-semibold text-[var(--text-1)]">DataAgent Pro</span>
        <span className="text-[11px] text-[var(--text-3)] mono truncate max-w-[240px]">
          {store.chat.threadId || '新会话'}
        </span>
        {/* 模式 chips */}
        <div className="flex items-center gap-1 ml-auto">
          {MODES.map(m => (
            <button
              key={m.key}
              type="button"
              onClick={() => store.setMode(m.key)}
              className={`px-2.5 py-1 text-[11px] rounded-md border cursor-pointer transition-colors ${
                store.mode === m.key
                  ? 'text-brand-light border-brand/40 bg-brand/10'
                  : 'text-[var(--text-3)] border-[var(--border)] bg-transparent hover:text-[var(--text-2)]'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </header>

      {/* 消息区 / 空态 */}
      {empty ? (
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center rise-in">
            <div className="text-3xl font-semibold mb-3 bg-clip-text text-transparent"
              style={{ backgroundImage: 'linear-gradient(135deg,#7056F8,#8B6FFF)' }}>
              你好,我是 DataAgent
            </div>
            <div className="text-sm text-[var(--text-3)] mb-6">用自然语言查询、分析、可视化你的业务数据</div>
            <div className="flex flex-wrap justify-center gap-2">
              {(store.suggestions.length ? store.suggestions : ['统计各表的数据量', '查看数据库中所有的表', '帮我分析数据库整体概况']).slice(0, 3).map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => store.sendMessage(s)}
                  className="px-3 py-1.5 text-[12px] text-brand-light bg-brand/[0.06] border border-brand/15 rounded-full cursor-pointer hover:bg-brand/15 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </main>
      ) : (
        <main className="flex-1 min-h-0">
          <MessageList />
        </main>
      )}

      {/* 输入区 */}
      <footer className="border-t border-[var(--border)] p-3 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex gap-2 items-end">
          <Input.TextArea
            value={text}
            onChange={e => setText(e.target.value)}
            onPressEnter={e => {
              if (!e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            placeholder="输入问题,Enter 发送 / Shift+Enter 换行"
            autoSize={{ minRows: 1, maxRows: 4 }}
          />
          {store.isLoading ? (
            <Button danger onClick={() => store.cancelGeneration()}>停止</Button>
          ) : (
            <Button type="primary" onClick={send} disabled={!text.trim()}>发送</Button>
          )}
        </div>
        {store.lastPerf && (
          <div className="max-w-3xl mx-auto mt-1.5 text-[10px] text-[var(--text-3)] mono">
            首token {(store.lastPerf.firstTokenMs / 1000).toFixed(1)}s · 总用时 {(store.lastPerf.durationMs / 1000).toFixed(1)}s ·{' '}
            {store.lastPerf.tokens} tok{store.lastPerf.tokPerSec !== null ? ` · ${store.lastPerf.tokPerSec} tok/s` : ''}
          </div>
        )}
      </footer>
    </div>
  )
}
