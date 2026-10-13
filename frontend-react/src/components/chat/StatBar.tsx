/**
 * StatBar.tsx —— 会话读数条(性能 / 上下文占用 / 轨迹入口)
 * 等宽字体 + 极细分隔线,置于输入区下方(官方布局中不设顶栏,读数就近展示)。
 */
import { useNavigate } from 'react-router-dom'
import { Activity, Settings2 } from 'lucide-react'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'

export default function StatBar({ onTrajectory }: { onTrajectory: () => void }) {
  const store = useChatStore()
  const auth = useAuthStore()
  const navigate = useNavigate()
  const p = store.lastPerf
  const ctxPct = Math.min(
    100,
    Math.round((store.contextUsage.estimatedTokens / store.contextUsage.window) * 100),
  )

  return (
    <div className="w-full px-4 pb-2">
      <div
        className="mx-auto flex items-center gap-4 text-[10px] mono text-[var(--text-3)]"
        style={{ maxWidth: 840, borderTop: '1px solid var(--border)', paddingTop: 6 }}
      >
        {p ? (
          <>
            <span title="本次回答总用时">用时 {(p.durationMs / 1000).toFixed(1)}s</span>
            <span title="首 token 延迟">首token {(p.firstTokenMs / 1000).toFixed(1)}s</span>
            <span title="生成速率">{p.tokPerSec !== null ? `${p.tokPerSec} tok/s` : '— tok/s'}</span>
            <span title="LLM 生成耗时">LLM {(p.llmMs / 1000).toFixed(1)}s</span>
            <span title="工具执行累计">工具 {(p.toolMs / 1000).toFixed(1)}s</span>
          </>
        ) : (
          <span>就绪</span>
        )}
        <span title="上下文窗口占用估算">
          上下文 {ctxPct}% ({store.contextUsage.estimatedTokens.toLocaleString()} tok)
        </span>

        <span className="ml-auto flex items-center gap-3">
          <button
            type="button"
            onClick={onTrajectory}
            className="flex items-center gap-1 text-[var(--text-3)] hover:text-[var(--brand-light)] bg-transparent border-none cursor-pointer transition-colors"
          >
            <Activity size={12} />
            轨迹
          </button>
          {auth.user?.user_type === 'admin' && (
            <button
              type="button"
              onClick={() => navigate('/admin/llm')}
              className="flex items-center gap-1 text-[var(--text-3)] hover:text-[var(--brand-light)] bg-transparent border-none cursor-pointer transition-colors"
            >
              <Settings2 size={12} />
              配置中心
            </button>
          )}
          <span className="text-[var(--text-2)]">
            {auth.user?.nick_name || auth.user?.user_name}
          </span>
        </span>
      </div>
    </div>
  )
}