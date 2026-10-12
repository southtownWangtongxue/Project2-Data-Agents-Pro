/**
 * ErrorCard.tsx —— 错误卡(错误码 + 重试按钮,UX 正确路径)
 */
import type { Msg } from '@/sdk/protocol'
import { useChatStore } from '@/stores/chat'

export default function ErrorCard({ msg }: { msg: Msg }) {
  const store = useChatStore()
  return (
    <div className="flex flex-col items-center gap-2.5 w-full py-2">
      <div className="inline-flex items-center gap-3 px-4 py-3 rounded-lg text-sm text-[#f87171] max-w-[82%] leading-relaxed"
        style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)' }}>
        <span>⚠</span>
        {msg.content}
        {msg.errorCode && <span className="mono text-[11px] text-[#fca5a5]">[{msg.errorCode}]</span>}
      </div>
      {msg.recoverable !== false && (
        <button
          type="button"
          disabled={store.isLoading}
          onClick={() => store.retryLastMessage()}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-[13px] text-brand-light disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          style={{ background: 'rgba(112,86,248,0.15)', border: '1px solid rgba(112,86,248,0.3)' }}
        >
          ↻ 重试
        </button>
      )}
    </div>
  )
}
