/**
 * StatBar.tsx —— 会话状态条(性能读数 + 上下文占用 + 用户)
 * 等宽字体,驾驶舱仪表语言。
 */
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'

export default function StatBar({ onTrajectory }: { onTrajectory: () => void }) {
  const store = useChatStore()
  const auth = useAuthStore()
  const p = store.lastPerf
  const ctxPct = Math.min(100, Math.round((store.contextUsage.estimatedTokens / store.contextUsage.window) * 100))

  return (
    <div className="h-8 flex items-center gap-3 px-4 border-t border-[var(--border)] text-[10px] text-[var(--text-3)] mono flex-shrink-0">
      {p && (
        <>
          <span title="本次回答总用时">用时 {(p.durationMs / 1000).toFixed(1)}s</span>
          <span title="首 token 延迟">首token {(p.firstTokenMs / 1000).toFixed(1)}s</span>
          <span title="生成速率">{p.tokPerSec !== null ? `${p.tokPerSec} tok/s` : '— tok/s'}</span>
          <span title="LLM 生成耗时">LLM {(p.llmMs / 1000).toFixed(1)}s</span>
          <span title="工具执行累计">工具 {(p.toolMs / 1000).toFixed(1)}s</span>
        </>
      )}
      <span title="上下文窗口占用估算">上下文 {ctxPct}% ({store.contextUsage.estimatedTokens.toLocaleString()} tok)</span>
      <span className="ml-auto flex items-center gap-3">
        <button type="button" onClick={onTrajectory}
          className="text-[var(--text-3)] hover:text-brand-light bg-transparent border-none cursor-pointer transition-colors">
          ⧉ 轨迹
        </button>
        {auth.user && <span className="text-[var(--text-2)]">{auth.user.nick_name || auth.user.user_name}</span>}
      </span>
    </div>
  )
}
