/**
 * ModelSelector.tsx —— 模型选择器(胶囊触发器 + 运行时参数内联配置)
 *
 * 2026-10-18 增强(参考 dsh 模型菜单):
 * - 每个模型行提供「参数」按钮,内联展开两项配置:
 *   · 上下文长度(192K / 300K / 600K / 1M,或自定义)—— 同时是
 *     读数条「上下文已用」的分母(与配置中心 /admin/llm 双向同步)
 *   · 思考强度(默认 / low / high / max)—— 写入 provider.params.reasoning_effort
 * - 保存走 PATCH /config/llm/{id}/runtime(只改这两项,不回传 api_key)
 */
import { useEffect, useRef, useState } from 'react'
import Icon from '@/components/bits/Icon'
import { useConfigStore, type LlmProvider } from '@/stores/config'
import { useChatStore } from '@/stores/chat'

/** 常用上下文长度预设 */
const WINDOW_PRESETS = [
  { label: '192K', value: 192_000 },
  { label: '300K', value: 300_000 },
  { label: '600K', value: 600_000 },
  { label: '1M', value: 1_000_000 },
]

/** 思考强度预设(空 = 跟随模型默认) */
const EFFORT_PRESETS = [
  { label: '默认', value: '' },
  { label: 'Low', value: 'low' },
  { label: 'High', value: 'high' },
  { label: 'Max', value: 'max' },
]

function fmtWindow(v?: number): string {
  const n = v || 0
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0)}M`
  return `${Math.round(n / 1000)}K`
}

/** 单模型的运行时参数面板(上下文长度 + 思考强度) */
function RuntimePanel({ provider, isCurrent }: { provider: LlmProvider; isCurrent: boolean }) {
  const config = useConfigStore()
  const chat = useChatStore()
  const [custom, setCustom] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const window = provider.context_window || 192_000
  const effort = provider.params?.reasoning_effort || ''

  const save = async (patch: { context_window?: number; reasoning_effort?: string }) => {
    setSaving(true)
    setErr('')
    try {
      await config.updateProviderRuntime(provider.id, patch)
      /* 当前模型的上下文窗口变化 → 读数条分母联动(即时反馈) */
      if (patch.context_window && isCurrent) {
        chat.setContextWindow(patch.context_window)
      }
    } catch (e) {
      setErr((e as Error).message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="mx-2 mb-1.5 px-3 py-2.5 rounded-lg space-y-2.5"
      style={{ background: 'rgba(255,255,255,0.035)', border: '1px solid var(--border)' }}
      onClick={e => e.stopPropagation()}
    >
      {/* 上下文长度 */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[12px] text-[var(--text-3)]">上下文长度</span>
          <span className="text-[12px] mono text-[var(--text-2)]">{fmtWindow(window)}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {WINDOW_PRESETS.map(p => {
            const active = window === p.value
            return (
              <button
                key={p.value}
                type="button"
                disabled={saving}
                onClick={() => save({ context_window: p.value })}
                className="px-2 py-1 rounded-md text-[12px] mono cursor-pointer border-none transition-colors disabled:opacity-50"
                style={{
                  background: active ? 'rgba(109,94,246,0.22)' : 'rgba(255,255,255,0.05)',
                  color: active ? 'var(--brand-light)' : 'var(--text-2)',
                }}
              >
                {p.label}
              </button>
            )
          })}
          <span className="flex items-center gap-1">
            <input
              value={custom}
              onChange={e => setCustom(e.target.value.replace(/[^\d]/g, ''))}
              placeholder="自定义"
              className="w-[68px] px-1.5 py-1 rounded-md text-[12px] mono bg-transparent outline-none"
              style={{ border: '1px solid var(--border)', color: 'var(--text-1)' }}
            />
            <button
              type="button"
              disabled={saving || !custom}
              onClick={() => save({ context_window: Number(custom) })}
              className="px-1.5 py-1 rounded-md text-[12px] bg-transparent cursor-pointer disabled:opacity-40"
              style={{ border: '1px solid var(--border)', color: 'var(--text-2)' }}
            >
              设置
            </button>
          </span>
        </div>
      </div>

      {/* 思考强度 */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[12px] text-[var(--text-3)]">思考强度</span>
          <span className="text-[12px] mono text-[var(--text-2)]">{effort || '默认'}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {EFFORT_PRESETS.map(p => {
            const active = effort === p.value
            return (
              <button
                key={p.value || 'default'}
                type="button"
                disabled={saving}
                onClick={() => save({ reasoning_effort: p.value })}
                className="px-2 py-1 rounded-md text-[12px] cursor-pointer border-none transition-colors disabled:opacity-50"
                style={{
                  background: active ? 'rgba(109,94,246,0.22)' : 'rgba(255,255,255,0.05)',
                  color: active ? 'var(--brand-light)' : 'var(--text-2)',
                }}
              >
                {p.label}
              </button>
            )
          })}
        </div>
      </div>

      {err && <div className="text-[11.5px]" style={{ color: 'var(--danger)' }}>{err}</div>}
      {saving && <div className="text-[11.5px] text-[var(--text-3)]">保存中…</div>}
    </div>
  )
}

export default function ModelSelector() {
  const config = useConfigStore()
  const chat = useChatStore()
  const [open, setOpen] = useState(false)
  /** 展开参数面板的模型 id(同一时刻只展开一个) */
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!config.loaded) config.loadProviders()
  }, [config.loaded])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setExpandedId(null)
      }
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
    const p = enabled.find(x => x.id === id)
    if (p?.context_window) chat.setContextWindow(p.context_window)
    setOpen(false)
    setExpandedId(null)
  }

  return (
    <div className="relative" ref={ref}>
      {/* dsh 参考:胶囊触发器,无边框,hover 仅背景变化 */}
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className={`flex items-center gap-1.5 h-8 px-3 text-[13.5px] rounded-full border-none cursor-pointer transition-colors ${
          open
            ? 'bg-white/[0.08] text-[var(--text-1)]'
            : 'bg-transparent text-[var(--text-2)] hover:bg-white/[0.05] hover:text-[var(--text-1)]'
        }`}
      >
        <span className="mono max-w-[170px] truncate">{display}</span>
        <Icon name="arrowDown" size={13} className={`text-[var(--text-3)] transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div
          className="absolute bottom-[calc(100%+8px)] left-0 w-[340px] z-50 rounded-xl p-1.5 shadow-2xl max-h-[70vh] overflow-y-auto"
          style={{ background: 'var(--cockpit-700)', border: '1px solid var(--border)' }}
        >
          <div className="px-3 py-1.5 text-[12px] font-semibold text-[var(--text-3)] tracking-wider uppercase">模型({enabled.length})</div>
          {enabled.map(p => {
            /* 悬浮即展开参数面板(2026-10-18:去掉齿轮按钮,鼠标移入模型行显示) */
            const expanded = expandedId === p.id
            return (
              <div
                key={p.id}
                onMouseEnter={() => setExpandedId(p.id)}
                onMouseLeave={() => setExpandedId(prev => (prev === p.id ? null : prev))}
              >
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => select(p.id)}
                  onKeyDown={e => { if (e.key === 'Enter') select(p.id) }}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left cursor-pointer transition-colors ${
                    current?.id === p.id ? 'bg-white/[0.07]' : 'hover:bg-white/[0.05]'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-[14px] text-[var(--text-1)] font-medium truncate">{p.name}</div>
                    <div className="text-[12px] text-[var(--text-3)] mono truncate">
                      {p.model} · {fmtWindow(p.context_window)}
                    </div>
                  </div>
                  {p.thinking_mode && <span className="text-[12px] px-1.5 py-0.5 rounded bg-brand/15 text-brand-light mono">思考</span>}
                  {current?.id === p.id && <Icon name="check" size={15} color="var(--brand-light)" />}
                </div>
                {expanded && <RuntimePanel provider={p} isCurrent={current?.id === p.id} />}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
