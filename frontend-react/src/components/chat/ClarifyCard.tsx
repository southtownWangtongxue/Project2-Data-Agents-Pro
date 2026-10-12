/**
 * ClarifyCard.tsx —— 意图追问卡(选项点击即发送)
 */
import type { Msg } from '@/sdk/protocol'
import { useChatStore } from '@/stores/chat'

export default function ClarifyCard({ msg }: { msg: Msg }) {
  const store = useChatStore()
  return (
    <div className="max-w-[82%] rounded-lg border border-brand/30 bg-brand/[0.04] p-3">
      <div className="text-[13px] text-[var(--text-1)] mb-2">{msg.content}</div>
      <div className="flex flex-wrap gap-2">
        {(msg.clarifyOptions || []).map(opt => (
          <button
            key={opt}
            type="button"
            onClick={() => store.sendMessage(opt)}
            className="px-3 py-1.5 text-[12px] text-brand-light bg-brand/10 border border-brand/25 rounded-full cursor-pointer hover:bg-brand/20 transition-colors"
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  )
}
