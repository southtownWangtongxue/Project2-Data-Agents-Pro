/**
 * SQLCard.tsx —— SQL 代码卡(等宽字体读数 + 复制)
 */
import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
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
    <div className="max-w-[88%] rounded-lg overflow-hidden border" style={{ borderColor: 'var(--border)' }}>
      <div
        className="flex items-center justify-between px-4 py-2 border-b"
        style={{ background: 'rgba(112,86,248,0.06)', borderColor: 'var(--border)' }}
      >
        <span className="text-[11px] font-medium tracking-wider uppercase mono" style={{ color: 'var(--brand-light)' }}>
          SQL 查询
        </span>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1 px-2 py-1 text-[11px] rounded cursor-pointer transition-colors"
          style={{ color: 'var(--text-3)', border: '1px solid var(--border)', background: 'transparent' }}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre
        className="m-0 px-4 py-3.5 mono text-[13px] leading-relaxed whitespace-pre-wrap break-all overflow-x-auto"
        style={{ background: 'var(--code-bg)', color: 'var(--text-1)' }}
      >
        {msg.sql}
      </pre>
    </div>
  )
}