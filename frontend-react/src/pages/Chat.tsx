/**
 * pages/Chat.tsx —— 对话主区(三栏驾驶舱)
 * 左:会话侧栏(可折叠) | 中:消息区/空态 + 输入区 | 底:状态条
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getToken } from '@/api/client'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useConfigStore } from '@/stores/config'
import ChatSidebar from '@/components/chat/ChatSidebar'
import MessageList from '@/components/chat/MessageList'
import SenderInput from '@/components/chat/SenderInput'
import WelcomePanel from '@/components/chat/WelcomePanel'
import StatBar from '@/components/chat/StatBar'
import TrajectoryDrawer from '@/components/chat/TrajectoryDrawer'

export default function Chat() {
  const navigate = useNavigate()
  const store = useChatStore()
  const auth = useAuthStore()
  const config = useConfigStore()
  const [collapsed, setCollapsed] = useState(false)
  const [trajOpen, setTrajOpen] = useState(false)
  /* 渲染级守卫:无 token 时不渲染组件树(否则 ModelSelector 等子组件会在
   * 重定向前就发请求,产生 401 噪声;StrictMode 下还会双发) */
  const authed = Boolean(getToken())

  useEffect(() => {
    if (!authed) {
      navigate('/login', { replace: true })
      return
    }
    auth.restore()
    store.loadSessions()
    store.loadSuggestions()
    config.loadProviders().then(() => {
      if (store.model) config.syncThinkingMode(store.model)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authed])

  const empty = store.chat.messages.length === 0

  if (!authed) return null

  return (
    <div className="h-full flex bg-[var(--cockpit-900)]">
      <ChatSidebar collapsed={collapsed} onToggle={() => setCollapsed(v => !v)} />

      <div className="flex-1 flex flex-col min-w-0">
        {empty ? <WelcomePanel /> : (
          <main className="flex-1 min-h-0">
            <MessageList />
          </main>
        )}
        <div className="flex-shrink-0 px-4 pb-3">
          <SenderInput />
        </div>
        <StatBar onTrajectory={() => setTrajOpen(true)} />
      </div>

      <TrajectoryDrawer open={trajOpen} onClose={() => setTrajOpen(false)} />
    </div>
  )
}
