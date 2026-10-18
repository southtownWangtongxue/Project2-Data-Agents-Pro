/**
 * ToolCard.tsx —— 工具调用卡(2026-10 重做,需求 6:原单行折叠+元数据平铺不可用)
 *
 * 三段式结构:
 * 1. 头部:工具图标 + 工具名 + 状态徽标(执行中 warning / 完成 success)
 * 2. 摘要行:单行读数(结果摘要或参数片段),点击整卡切换展开
 * 3. 展开区:键值结构化排列(键 11px 灰,字符串值走 Markdown 渲染)
 *
 * 兼容流式语义:toolPhase 'call'→执行中,'done'→完成(与历史投影的 done 态一致)。
 */
import { useState } from 'react'
import Icon from '@/components/bits/Icon'
import Markdown from '@/components/bits/Markdown'
import SpotlightCard from '@/components/bits/reactbits/SpotlightCard'
import type { Msg } from '@/sdk/protocol'

const LABEL_MAP: Record<string, string> = {
  input: '输入', result: '结果', status: '状态', info: '说明',
  sql: 'SQL', args: '参数', agent: '代理', phase: '阶段',
  chart_type: '图表类型', row_count: '返回行数',
}

/** meta 中适合做单行摘要的首选键 */
const SUMMARY_KEYS = ['result', 'status', 'info', 'input'] as const

function stringify(v: unknown, maxLen = 800): string {
  if (v === undefined || v === null) return ''
  if (typeof v === 'string') return v.slice(0, maxLen)
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  try {
    return (JSON.stringify(v, null, 2) ?? '').slice(0, maxLen)
  } catch {
    return String(v).slice(0, maxLen)
  }
}

function summaryOf(meta: Record<string, unknown>): string {
  for (const k of SUMMARY_KEYS) {
    const v = meta[k]
    if (v === undefined || v === null || v === '') continue
    const text = typeof v === 'string' ? v : JSON.stringify(v)
    return text.replace(/\s+/g, ' ').trim().slice(0, 90)
  }
  return ''
}

export default function ToolCard({ msg }: { msg: Msg }) {
  /* 折叠态存于组件本地:直接改写 msg.collapsed 不会触发渲染 */
  const [collapsed, setCollapsed] = useState(msg.collapsed ?? true)
  const meta = msg.toolMeta || {}
  const done = msg.toolPhase === 'done'
  const summary = summaryOf(meta)
  const hasDetail = Object.keys(meta).length > 0

  /* misc 工具卡与正文去重:结果即正文的 misc_agent 工具卡降级为状态点 */
  if (msg.toolName === 'misc_agent') {
    return (
      <div className="text-[11px] text-[var(--text-3)] mono px-1">
        <span className="inline-flex items-center gap-1">
          <Icon name={done ? 'check' : 'loader'} size={12} className={done ? '' : 'animate-spin'} />
          {done ? '已回答' : '生成回答中'}
        </span>
      </div>
    )
  }

  return (
    <SpotlightCard
      className="w-full min-w-0 cursor-pointer transition-colors select-none"
      spotlightColor="#8B6FFF"
      intensity={0.12}
      spotlightSize={340}
      proximity={90}
      borderGlow={0.5}
      style={{
        ['--spotlight-card-surface' as string]: 'var(--cockpit-800)',
        ['--spotlight-card-border' as string]: 'var(--border)',
        borderRadius: 10,
        borderLeft: '2px solid var(--brand)',
      }}
      onClick={() => hasDetail && setCollapsed(v => !v)}
    >
      {/* 头部:图标 + 名称 + 状态徽标 */}
      <div className="flex items-center gap-2 px-3 py-2">
        <Icon name="tools" size={15} color="var(--brand-light)" className="flex-shrink-0" />
        <span className="text-[12px] font-medium text-[var(--text-1)] truncate">
          {msg.toolName || '工具'}
        </span>
        <span
          className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded mono flex-shrink-0"
          style={{
            color: done ? 'var(--success)' : 'var(--warning)',
            background: done ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
          }}
        >
          <Icon name={done ? 'check' : 'loader'} size={12} className={done ? '' : 'animate-spin'} />
          {done ? '完成' : '执行中'}
        </span>
        <Icon
          name="arrowDown"
          size={14}
          className={`flex-shrink-0 ml-auto text-[var(--text-3)] transition-transform ${collapsed ? '' : 'rotate-180'}`}
        />
      </div>

      {/* 摘要行(有摘要才显示;展开时隐藏避免与详情重复) */}
      {summary && (collapsed || !hasDetail) && (
        <div className="px-3 pb-2 -mt-0.5 text-[11px] text-[var(--text-2)] truncate mono">
          {summary}
        </div>
      )}

      {/* 展开区:键值结构化,字符串值走 Markdown */}
      {!collapsed && hasDetail && (
        <div
          className="px-3 py-2.5 border-t text-[12px] text-[var(--text-2)] leading-relaxed"
          style={{ borderColor: 'var(--border)', background: 'rgba(112,86,248,0.04)' }}
        >
          {Object.entries(meta).map(([k, v]) =>
            v === undefined || v === null || v === '' ? null : (
              <div key={k} className="mb-2 last:mb-0">
                <div className="text-[11px] text-[var(--text-3)] mb-0.5">{LABEL_MAP[k] || k}</div>
                {typeof v === 'string' ? (
                  <Markdown content={v} className="text-[12px]" />
                ) : (
                  <div className="mono text-[12px] whitespace-pre-wrap break-all">{stringify(v)}</div>
                )}
              </div>
            ),
          )}
        </div>
      )}
    </SpotlightCard>
  )
}
