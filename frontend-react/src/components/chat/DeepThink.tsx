/**
 * DeepThink.tsx —— 「深度思考」多轮思考区(2026-10-18)
 *
 * 参考 React Bits `micro/thought-line`:
 * - 呼吸光点 + 标题微光扫过 + 实时计时(thinking 状态可见)
 * - 展开为**多轮思考列表**:每轮一行,进行中显示脉冲点,完成显示勾
 * - 边框用 StarBorder(星轨描边)
 * 交互对齐 antdx Think 的状态语义:流式中展开并加载、结束后自动折叠、点击优先。
 */
import { useEffect, useRef, useState } from 'react'
import Icon from '@/components/bits/Icon'
import Markdown from '@/components/bits/Markdown'
import StarBorder from '@/components/bits/reactbits/StarBorder'

/** 单轮思考行:进行中脉冲 / 完成勾 + 文本 */
function RoundRow({ text, working, index }: { text: string; working: boolean; index: number }) {
  return (
    <div
      className="dt-step flex items-start gap-2.5 py-1.5"
      style={{ animationDelay: `${Math.min(index, 6) * 40}ms` }}
    >
      <span className="flex-shrink-0 mt-[7px] w-[9px] flex items-center justify-center">
        {working ? (
          <i className="dt-pulse" />
        ) : (
          <Icon name="check" size={11} color="var(--success)" />
        )}
      </span>
      <div className="flex-1 min-w-0 text-[13px] leading-relaxed text-[var(--text-2)]">
        <Markdown content={text} />
      </div>
    </div>
  )
}

export interface DeepThinkProps {
  /** 该回复的全部思考段落(每轮一次完整思考,流式时最后一段仍在增长) */
  rounds: string[]
  /** 是否正在生成(决定展开/计时/脉冲) */
  working: boolean
}

export default function DeepThink({ rounds, working }: DeepThinkProps) {
  const [userSet, setUserSet] = useState<boolean | null>(null)
  const [autoCollapsed, setAutoCollapsed] = useState(false)
  /** 思考耗时(仅在 working 期间累计展示) */
  const [elapsed, setElapsed] = useState(0)
  const startedRef = useRef<number | null>(null)

  const total = rounds.reduce((sum, r) => sum + (r || '').length, 0)

  useEffect(() => {
    if (working) {
      setAutoCollapsed(false)
      if (startedRef.current === null) startedRef.current = performance.now()
      const timer = window.setInterval(() => {
        if (startedRef.current !== null) {
          setElapsed(Math.floor((performance.now() - startedRef.current) / 1000))
        }
      }, 500)
      return () => window.clearInterval(timer)
    }
    startedRef.current = null
    const timer = window.setTimeout(() => setAutoCollapsed(true), 600)
    return () => window.clearTimeout(timer)
  }, [working])

  const expanded = userSet !== null ? userSet : (working || !autoCollapsed)
  const title = working ? '深度思考中…' : '深度思考'

  return (
    <StarBorder
      className="my-2 overflow-hidden"
      radius={10}
      duration={working ? 3.2 : 6}
      thickness={1}
      color={working ? '#8b7bff' : 'rgba(139,123,255,0.55)'}
      surface="var(--cockpit-700)"
      glow={working}
    >
      {/* 头行:呼吸图标 + 标题(工作中微光) + 计时/字数 + 展开箭头 */}
      <button
        type="button"
        onClick={() => setUserSet(v => !(v ?? expanded))}
        className="w-full flex items-center gap-2 px-3 py-2 bg-transparent border-none cursor-pointer text-left"
      >
        <span className={`dt-glyph--${working ? 'working' : 'idle'} flex-shrink-0 flex items-center justify-center`}>
          <Icon name="magic" size={14} color="var(--brand-light)" />
        </span>
        <span className={`text-[13px] font-medium ${working ? 'dt-shimmer' : 'text-[var(--text-1)]'}`}>
          {title}
        </span>
        <span className="text-[11.5px] text-[var(--text-3)] tabular-nums">
          {working ? `${elapsed}s` : `${total} 字`}
          {rounds.length > 1 && !working ? ` · ${rounds.length} 轮` : ''}
        </span>
        <Icon
          name="arrowDown"
          size={12}
          className={`ml-auto flex-shrink-0 text-[var(--text-3)] transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {/* 多轮思考列表 */}
      {expanded && (
        <div className="dt-trace px-3 pb-2.5 max-h-[320px] overflow-y-auto">
          {rounds.map((r, i) => (
            <RoundRow
              key={i}
              index={i}
              text={r}
              working={working && i === rounds.length - 1}
            />
          ))}
        </div>
      )}
    </StarBorder>
  )
}
