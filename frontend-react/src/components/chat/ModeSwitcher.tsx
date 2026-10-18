/**
 * ModeSwitcher.tsx —— 多模式切换下拉面板(Sender.Header 内)
 *
 * 2026-10 重做:替代原 Segmented 分段器。后端 mode 是请求级参数
 * (data/report/doc → LangGraph 工作流;task → DeepAgent 调度),并非真实
 * 多智能体,故用「模式卡片面板」承载图标+名称+说明+路由提示,信息量与
 * 扩展性优于分段器,也不误导为多 Agent 选择。
 * 2026-10-18 图标统一:lucide → iconfont(需求 4)。
 *
 * 交互约定(沿用 e2e 已修约定):点击展开 / 点击外部关闭 / Esc 关闭。
 */
import { useEffect, useRef, useState } from 'react'
import { Tooltip } from 'antd'
import Icon, { type IconName } from '@/components/bits/Icon'
import { useChatStore } from '@/stores/chat'

interface ModeDef {
  value: string
  label: string
  description: string
  route: string
  icon: IconName
}

const MODES: ModeDef[] = [
  {
    value: 'data',
    label: '数据分析',
    description: '自然语言查数:统计、对比、趋势与异常分析',
    route: 'LangGraph 工作流',
    icon: 'chart',
  },
  {
    value: 'report',
    label: '研究报告',
    description: '多轮检索知识库,输出结构化研究报告',
    route: 'LangGraph 工作流',
    icon: 'fileText',
  },
  {
    value: 'doc',
    label: '文档智读',
    description: '在已上传文档范围内检索并作答',
    route: 'LangGraph 工作流',
    icon: 'bookMarked',
  },
  {
    value: 'task',
    label: '通用任务',
    description: '复杂任务自动拆解与工具编排',
    route: 'DeepAgent 调度',
    icon: 'listCheck',
  },
]

export default function ModeSwitcher() {
  const store = useChatStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const current = MODES.find(m => m.value === store.mode) || MODES[0]

  /* 点击外部 / Esc 关闭 */
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('click', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      {/* 触发器:模式图标 + 名称 + chevron */}
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex items-center gap-1.5 h-8 px-2.5 text-[12px] rounded-md border cursor-pointer transition-colors"
        style={{
          borderColor: open ? 'rgba(112,86,248,0.45)' : 'var(--border)',
          background: open ? 'rgba(112,86,248,0.10)' : 'transparent',
          color: 'var(--text-1)',
        }}
      >
        <Icon name={current.icon} size={15} color="var(--brand-light)" />
        <span>{current.label}</span>
        <Icon name="arrowDown" size={12} className="text-[var(--text-3)] transition-transform" style={{ transform: open ? 'rotate(180deg)' : undefined }} />
      </button>

      {/* 下拉面板:模式卡片 */}
      {open && (
        <div
          role="listbox"
          className="absolute bottom-[calc(100%+8px)] left-0 w-[300px] z-50 rounded-xl border border-[var(--border)] bg-[var(--cockpit-800)] shadow-2xl p-1.5"
        >
          <div className="px-2.5 py-1.5 text-[10px] font-semibold text-[var(--text-3)] tracking-wider uppercase">
            选择模式
          </div>
          {MODES.map(m => {
            const active = m.value === current.value
            return (
              <button
                key={m.value}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => { store.setMode(m.value); setOpen(false) }}
                className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg border cursor-pointer text-left transition-colors"
                style={{
                  borderColor: active ? 'rgba(112,86,248,0.5)' : 'transparent',
                  background: active ? 'rgba(112,86,248,0.10)' : 'transparent',
                }}
                onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--cockpit-700)' }}
                onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
              >
                <span className="flex-shrink-0 mt-0.5" style={{ color: active ? 'var(--brand-light)' : 'var(--text-3)' }}>
                  <Icon name={m.icon} size={15} />
                </span>
                <span className="flex-1 min-w-0">
                  <span className="flex items-center gap-1.5">
                    <span className="text-[13px] font-medium text-[var(--text-1)]">{m.label}</span>
                    <span className="mono text-[9px] px-1.5 py-0.5 rounded text-[var(--text-3)]" style={{ background: 'var(--cockpit-700)' }}>
                      {m.route}
                    </span>
                  </span>
                  <span className="block text-[11px] text-[var(--text-3)] mt-0.5 leading-snug">{m.description}</span>
                </span>
                {active && <Icon name="check" size={14} className="flex-shrink-0 mt-1" color="var(--brand-light)" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** 供 SenderInput 复用:当前模式的 Tooltip 说明 */
export function ModeTooltip({ children }: { children: React.ReactNode }) {
  const store = useChatStore()
  const current = MODES.find(m => m.value === store.mode) || MODES[0]
  return <Tooltip title={`${current.label}:${current.description}(${current.route})`}>{children}</Tooltip>
}
