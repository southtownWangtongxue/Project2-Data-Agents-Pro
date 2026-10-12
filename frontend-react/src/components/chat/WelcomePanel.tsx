/**
 * WelcomePanel.tsx —— 空态欢迎页(打字机标题 + 建议 prompts)
 * 动效在 visual-polish 阶段升级为 ReactBits TypeText/Aurora。
 */
import { useEffect, useState } from 'react'
import { useChatStore } from '@/stores/chat'

const TITLE = '你好,我是 DataAgent'

export default function WelcomePanel() {
  const store = useChatStore()
  const [typed, setTyped] = useState('')

  /* 打字机标题(碳黑驾驶舱的入场时刻) */
  useEffect(() => {
    let i = 0
    const timer = setInterval(() => {
      i += 1
      setTyped(TITLE.slice(0, i))
      if (i >= TITLE.length) clearInterval(timer)
    }, 90)
    return () => clearInterval(timer)
  }, [])

  const prompts = store.suggestions.length
    ? store.suggestions
    : ['统计各表的数据量', '查看数据库中所有的表', '帮我分析数据库整体概况']

  return (
    <div className="h-full flex items-center justify-center px-6">
      <div className="text-center max-w-xl rise-in">
        <div
          className="text-4xl font-semibold mb-3 min-h-[48px] bg-clip-text text-transparent"
          style={{ backgroundImage: 'linear-gradient(135deg,#8B6FFF,#7056F8)' }}
        >
          {typed}
          <span className="inline-block w-[2px] h-[36px] align-middle bg-brand ml-0.5 brand-pulse" />
        </div>
        <div className="text-sm text-[var(--text-3)] mb-8">
          用自然语言查询、分析、可视化你的业务数据 · 读数据随意,改数据必批
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {prompts.slice(0, 3).map(p => (
            <button
              key={p}
              type="button"
              onClick={() => store.sendMessage(p)}
              className="px-4 py-3 text-[12px] text-[var(--text-2)] text-left rounded-xl border border-[var(--border)] bg-[var(--cockpit-800)] cursor-pointer hover:border-brand/40 hover:text-[var(--text-1)] transition-colors"
            >
              {p}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
