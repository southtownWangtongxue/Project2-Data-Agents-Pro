/**
 * SQLCard.tsx —— SQL 代码卡(等宽字体读数 + 复制)
 */
import { useState } from 'react'
import type { Msg } from '@/sdk/protocol'

export default function SQLCard({ msg }: { msg: Msg }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(msg.sql || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* 剪贴板不可用时静默 */
    }
  }

  return (
    <div className="max-w-[88%] rounded-lg overflow-hidden border border-[var(--border)] bg-[#0d0d0f] shadow-md">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border)]"
        style={{ background: 'rgba(112,86,248,0.05)' }}>
        <span className="text-[11px] font-medium tracking-wider text-brand-light uppercase mono">SQL 查询</span>
        <button type="button" onClick={copy}
          className="flex items-center gap-1 px-2 py-1 text-[11px] text-[var(--text-3)] bg-transparent border border-[var(--border)] rounded cursor-pointer hover:text-[var(--text-2)] hover:border-[var(--border-light,var(--border))] transition-colors">
          {copied ? '✓ 已复制' : '⧉ 复制'}
        </button>
      </div>
      <pre className="m-0 px-4 py-3.5 mono text-[13px] leading-relaxed text-[#e2e8f0] whitespace-pre-wrap break-all overflow-x-auto">{msg.sql}</pre>
    </div>
  )
}
