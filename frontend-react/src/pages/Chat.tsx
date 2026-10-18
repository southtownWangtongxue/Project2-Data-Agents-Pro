/**
 * pages/Chat.tsx —— 对话工作台
 *
 * 布局对齐 Ant Design X 官方「独立式」样板间:
 *   layout(100vh flex) → side(280px) → chat(flex column, justify-between)
 *   chat = chatList(flex-1, overflow-y auto, 居中 max-w) + chatSender(底部固定)
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getToken } from '@/api/client'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useConfigStore } from '@/stores/config'
import ChatSidebar from '@/components/chat/ChatSidebar'
import MessageList from '@/components/chat/MessageList'
import SenderInput from '@/components/chat/SenderInput'
import WelcomePanel from '@/components/chat/WelcomePanel'
import TurnNavigator from '@/components/chat/TurnNavigator'
import StatBar from '@/components/chat/StatBar'

export default function Chat() {
  const navigate = useNavigate()
  const store = useChatStore()
  const auth = useAuthStore()
  const config = useConfigStore()
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
    <div className="h-screen w-full flex overflow-hidden bg-[var(--cockpit-800)]">
      <ChatSidebar />

      <div className="flex-1 min-w-0 h-full flex flex-col justify-between bg-[var(--cockpit-900)]">
        {/* 🌟 chatList —— 消息区 / 空态 */}
        <main className="flex-1 min-h-0 w-full flex flex-col items-center overflow-hidden">
          {empty ? (
            <WelcomePanel />
          ) : (
            <>
              {/* 多轮对话节点切换(仅历史会话且多轮时出现) */}
              <TurnNavigator />
              <MessageList />
            </>
          )}
        </main>

        {/* 🌟 chatSender —— 输入区 + 读数条(三统计弹窗) */}
        <div className="w-full flex-shrink-0">
          <SenderInput />
          <StatBar />
        </div>
      </div>
    </div>
  )
}