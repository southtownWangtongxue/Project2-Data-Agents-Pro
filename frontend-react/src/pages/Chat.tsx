/**
 * pages/Chat.tsx —— 对话页(dataflow 阶段最小闭环版)
 * 目的:驱动真实 SSE 数据流(chat-core 阶段替换为 Bubble.List + 步骤链完整 UI)
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input } from 'antd'
import { getToken } from '@/api/client'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'

export default function Chat() {
  const navigate = useNavigate()
  const store = useChatStore()
  const auth = useAuthStore()
  const [text, setText] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!getToken()) navigate('/login', { replace: true })
    auth.restore()
    store.loadSessions()
    store.loadSuggestions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [store.chat.messages.length, store.isLoading])

  const send = () => {
    if (!text.trim()) return
    store.sendMessage(text.trim())
    setText('')
  }

  /* 按步骤分组的简版渲染(验证 step_id 分组与并行槽位) */
  const groups: { stepId: number; label: string; status: string; msgs: typeof store.chat.messages }[] = []
  for (const m of store.chat.messages) {
    const sid = m.stepId || 0
    const step = sid ? store.chat.steps.get(sid) : undefined
    if (step) {
      let g = groups.find(x => x.stepId === sid)
      if (!g) {
        g = { stepId: sid, label: `步骤 ${sid} · ${step.label}`, status: step.status, msgs: [] }
        groups.push(g)
      }
      g.msgs.push(m)
      g.status = step.status
    } else {
      groups.push({ stepId: 0, label: '', status: '', msgs: [m] })
    }
  }

  return (
    <div className="h-full flex flex-col bg-[var(--cockpit-900)]">
      {/* 顶栏 */}
      <header className="h-12 flex items-center px-4 border-b border-[var(--border)] gap-3">
        <span className="font-semibold">DataAgent Pro</span>
        <span className="text-xs text-[var(--text-3)] mono">dataflow · 最小闭环</span>
        <span className="ml-auto text-xs text-[var(--text-3)] mono">
          {store.chat.threadId ? store.chat.threadId.slice(0, 24) : '新会话'}
        </span>
      </header>

      {/* 消息区 */}
      <main className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-3xl mx-auto space-y-3">
          {groups.map((g, gi) => (
            <div key={gi}>
              {g.label && (
                <div className="text-xs text-[var(--text-3)] mono mb-1 flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${g.status === 'running' ? 'bg-brand brand-pulse' : 'bg-[var(--success)]'}`} />
                  {g.label}
                  <span className="text-[10px]">{g.status === 'running' ? '运行中' : '已完成'}</span>
                </div>
              )}
              {g.msgs.map(m => (
                <div key={m.id} className="mb-2">
                  {m.kind === 'text' && m.role === 'user' && (
                    <div className="inline-block px-4 py-2 rounded-2xl rounded-br-sm text-white" style={{ background: 'linear-gradient(135deg,#7056F8,#8B6FFF)' }}>
                      {m.content}
                    </div>
                  )}
                  {m.kind === 'text' && m.role === 'assistant' && (
                    <div className="inline-block px-4 py-2 rounded-2xl rounded-bl-sm bg-[var(--cockpit-800)] border border-[var(--border)] whitespace-pre-wrap">
                      {m.content}
                    </div>
                  )}
                  {m.kind === 'sql' && (
                    <pre className="inline-block px-4 py-2 rounded-lg bg-[#0d0d0f] border border-[var(--border)] mono text-[13px] text-[#e2e8f0]">{m.sql}</pre>
                  )}
                  {m.kind === 'error' && (
                    <div className="text-[#f87171] text-sm">⚠ {m.content} {m.errorCode && <span className="mono text-xs">[{m.errorCode}]</span>}</div>
                  )}
                  {m.kind === 'tool' && (
                    <div className="text-xs text-[var(--text-2)]">🔧 {m.toolName} · {m.toolPhase === 'done' ? '完成' : '调用中'}</div>
                  )}
                  {m.kind === 'reasoning' && store.thinkingModeEnabled && (
                    <div className="text-xs text-[var(--text-3)] whitespace-pre-wrap border-l-2 border-[var(--brand)] pl-2">💭 {m.content}</div>
                  )}
                  {m.kind === 'status' && <div className="text-xs text-[var(--text-2)]">{m.content}</div>}
                </div>
              ))}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </main>

      {/* 输入区 */}
      <footer className="border-t border-[var(--border)] p-3">
        <div className="max-w-3xl mx-auto flex gap-2">
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
      </footer>
    </div>
  )
}
