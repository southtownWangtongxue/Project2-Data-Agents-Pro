/**
 * ModelSelector.tsx —— 模型选择器(等宽读数,驾驶舱风格)
 */
import { useEffect, useRef, useState } from 'react'
import { useConfigStore } from '@/stores/config'
import { useChatStore } from '@/stores/chat'

export default function ModelSelector() {
  const config = useConfigStore()
  const chat = useChatStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!config.loaded) config.loadProviders()
  }, [config.loaded])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  const enabled = config.providers.filter(p => p.enabled)
  const current = enabled.find(p => p.id === chat.model) || enabled[0]
  const display = current ? `${current.name}${current.thinking_mode ? ' · 思考' : ''}` : '选择模型'

  const select = (id: string) => {
    chat.setModel(id)
    config.syncThinkingMode(id)
    setOpen(false)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className={`flex items-center gap-1.5 h-8 px-3 text-[12px] rounded-md border cursor-pointer transition-colors ${
          open ? 'bg-[var(--cockpit-700)] border-[var(--border-light)]' : 'bg-transparent border-[var(--border)] hover:bg-[var(--cockpit-800)]'
        }`}
      >
        <span className="mono max-w-[160px] truncate text-[var(--text-1)]">{display}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`text-[var(--text-3)] transition-transform ${open ? 'rotate-180' : ''}`}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-[calc(100%+6px)] left-0 min-w-[280px] z-50 rounded-lg border border-[var(--border)] bg-[var(--cockpit-800)] shadow-2xl py-1">
          <div className="px-3 py-1.5 text-[10px] font-semibold text-[var(--text-3)] tracking-wider uppercase">模型({enabled.length})</div>
          {enabled.map(p => (
            <button
              key={p.id}
              type="button"
              onClick={() => select(p.id)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-left cursor-pointer border-none bg-transparent hover:bg-[var(--cockpit-700)] transition-colors ${
                current?.id === p.id ? 'bg-brand/10' : ''
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="text-[12px] text-[var(--text-1)] font-medium truncate">{p.name}</div>
                <div className="text-[10px] text-[var(--text-3)] mono truncate">{p.model}</div>
              </div>
              {p.thinking_mode && <span className="text-[9px] px-1.5 py-0.5 rounded bg-brand/15 text-brand-light mono">思考</span>}
              {current?.id === p.id && <span className="text-brand-light text-[11px]">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
