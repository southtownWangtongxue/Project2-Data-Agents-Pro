/**
 * WelcomePanel.tsx —— 空态欢迎页(打字机标题 + 极光背景 + 建议 prompts)
 */
import TypeText from '@/components/bits/TypeText'
import ClickSpark from '@/components/bits/ClickSpark'
import Aurora from '@/components/bits/Aurora'
import { useChatStore } from '@/stores/chat'

const TITLE = '你好,我是 DataAgent'
const SUBTITLE = '自然语言 → SQL → 图表 → 洞察,一句话完成业务数据探索'

export default function WelcomePanel() {
  const store = useChatStore()

  const prompts = store.suggestions.length
    ? store.suggestions
    : ['统计各表的数据量', '查看数据库中所有的表', '帮我分析数据库整体概况']

  return (
    <div className="h-full relative flex items-center justify-center px-6 overflow-hidden">
      <Aurora />
      <div className="relative text-center max-w-xl rise-in">
        <div
          className="text-4xl font-semibold mb-3 min-h-[48px] bg-clip-text text-transparent"
          style={{ backgroundImage: 'linear-gradient(135deg,#8B6FFF,#7056F8)' }}
        >
          <TypeText text={TITLE} speed={85} />
        </div>
        <div className="text-sm text-[var(--text-3)] mb-2 min-h-[22px]">
          <TypeText text={SUBTITLE} speed={32} cursorClassName="opacity-0" />
        </div>
        <div className="text-[11px] text-[var(--text-3)] mb-8 mono tracking-wider">
          NATURAL LANGUAGE → DATA → INSIGHT
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {prompts.slice(0, 3).map(p => (
            <ClickSpark key={p}>
              <button
                type="button"
                onClick={() => store.sendMessage(p)}
                className="w-full px-4 py-3 text-[12px] text-[var(--text-2)] text-left rounded-xl border border-[var(--border)] bg-[var(--cockpit-800)]/80 backdrop-blur cursor-pointer hover:border-brand/40 hover:text-[var(--text-1)] transition-colors"
              >
                {p}
              </button>
            </ClickSpark>
          ))}
        </div>
      </div>
    </div>
  )
}