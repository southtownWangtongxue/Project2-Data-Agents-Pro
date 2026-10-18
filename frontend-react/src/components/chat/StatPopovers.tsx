/**
 * StatPopovers.tsx —— 读数条三弹窗(参考 DeepSeek Harness 读数面板)
 *
 * 2026-10-18 重做(验收反馈):
 * - 三项**常驻显示**:新会话无数据时也渲染(占位「—」/「0」),不再整项消失
 * - 上下文增加**缩略圆环进度**(触发器内嵌 SVG ring,与 DeepSeek 一致)
 * - 明细排版:键值行 + 缓存命中/上下文占用进度条,无数据时给出引导文案
 *
 * 数据源:stores/chat.ts 的 sessionStats(前端逐轮派生)与 usage(后端 usage 事件,
 * context 三段为服务端估算,estimated 标记)。
 */
import type { ReactNode } from 'react'
import { Popover } from 'antd'
import Icon from '@/components/bits/Icon'
import { useChatStore } from '@/stores/chat'

/* ── 格式化(模块级单例,避免每帧新建 Intl 实例)── */
const nf = new Intl.NumberFormat('zh-CN')

/** token 数:1,234 → 1,234;19,410 → 19.4K;1,941,026 → 1.9M */
export function formatTokens(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (n < 10_000) return nf.format(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`
  return `${(n / 1_000_000).toFixed(1)}M`
}

/** 毫秒时长:<60s 显示 x.xs,≥60s 显示 x分x秒 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rest = Math.round(s - m * 60)
  return rest > 0 ? `${m}分${rest}秒` : `${m}分`
}

/** 比例(0~1) → 百分比文案 */
function formatRatio(r: number | null | undefined): string {
  if (r === null || r === undefined) return '—'
  return `${Math.round(r * 100)}%`
}

/** 弹窗容器统一样式(dsh 悬浮卡:比面板亮一层 + 弱描边 + 大圆角) */
const POPOVER_STYLES = {
  container: {
    padding: '12px 14px',
    background: 'var(--cockpit-700)',
    border: '1px solid var(--border)',
    borderRadius: 14,
    boxShadow: 'var(--shadow-card)',
  },
} as const

/* ── 弹窗卡片骨架(玻璃面 + 标题行 + 明细行)── */
function PopoverCard({ icon, title, summary, children }: {
  icon: ReactNode
  title: string
  summary?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="w-[308px] px-0.5 py-0.5">
      {/* 标题行(2026-10-18 dsh 定版):去底部边框,靠间距分层 */}
      <div className="flex items-center gap-2.5 pb-2.5 mb-1">
        <span className="flex items-center justify-center w-7 h-7 rounded-lg flex-shrink-0"
          style={{ color: 'var(--brand-light)', background: 'rgba(109,94,246,0.14)' }}>
          {icon}
        </span>
        <span className="text-[15px] font-semibold text-[var(--text-1)]">{title}</span>
        {summary !== undefined && (
          <span className="ml-auto text-[15px] text-[var(--text-1)] tabular-nums">{summary}</span>
        )}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function StatRow({ k, v, muted }: { k: string; v: ReactNode; muted?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 text-[14px] leading-7">
      <span className="text-[var(--text-2)] flex-shrink-0">{k}</span>
      <span className={`mono tabular-nums ${muted ? 'text-[var(--text-2)]' : 'text-[var(--text-1)]'}`}>{v}</span>
    </div>
  )
}

/** 细进度条(track --cockpit-600,值段品牌紫渐变或 success 绿) */
function MiniBar({ pct, color }: { pct: number; color?: string }) {
  const clamped = Math.max(0, Math.min(100, pct))
  return (
    <div className="h-1.5 rounded-full overflow-hidden mt-2" style={{ background: 'var(--cockpit-600)' }}>
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${clamped}%`,
          background: color || 'linear-gradient(90deg, #6D5EF6, #8B7BFF)',
        }}
      />
    </div>
  )
}

/** 缩略圆环进度(触发器内嵌,12.5px 字号内可读;≥80% 转警示色) */
function RingGauge({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct))
  const r = 6.5
  const c = 2 * Math.PI * r
  const stroke = clamped >= 80 ? 'var(--warning)' : 'var(--brand)'
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" className="flex-shrink-0" aria-hidden>
      <circle cx="7.5" cy="7.5" r={r} fill="none" stroke="var(--cockpit-600)" strokeWidth="2" />
      <circle
        cx="7.5" cy="7.5" r={r} fill="none" stroke={stroke} strokeWidth="2"
        strokeDasharray={`${(c * clamped) / 100} ${c}`}
        strokeLinecap="round" transform="rotate(-90 7.5 7.5)"
        style={{ transition: 'stroke-dasharray 0.5s ease' }}
      />
    </svg>
  )
}

/* ── 1. 会话统计 ─────────────────────────────────────────────── */
export function SessionStatsPopover() {
  const stats = useChatStore(s => s.sessionStats)
  const avgTtft = stats.ttftCount > 0 ? stats.ttftSumMs / stats.ttftCount : null
  const avgTps = stats.tpsCount > 0 ? stats.tpsSum / stats.tpsCount : null
  const turns = stats.turns
  const hasData = turns > 0 || stats.steps > 0

  return (
    <Popover
      trigger="hover"
      placement="top"
      mouseEnterDelay={0.15}
      styles={POPOVER_STYLES}
      content={
        <PopoverCard icon={<Icon name="speed" size={16} />} title="会话统计"
          summary={`${turns} 轮 ${stats.steps} 步`}>
          <StatRow k="模型耗时" v={formatDuration(stats.llmMs)} muted={!hasData} />
          <StatRow k="工具调用用时" v={formatDuration(stats.toolMs)} muted={!hasData} />
          <StatRow k="首token平均 (TTFT)" v={avgTtft !== null ? formatDuration(avgTtft) : '—'} muted={avgTtft === null} />
          <StatRow k="输出速度 (TPS)" v={avgTps !== null ? `${Math.round(avgTps)} tok/s` : '—'} muted={avgTps === null} />
          {!hasData && <div className="text-[12px] text-[var(--text-3)] mt-1">发起一轮对话后统计本轮指标</div>}
        </PopoverCard>
      }
    >
      <button type="button" className="stat-trigger" title="会话统计">
        <Icon name="speed" size={13} />
        <span>{hasData ? `${turns} 轮 ${stats.steps} 步` : '会话统计'}</span>
        {avgTps !== null && <span className="stat-trigger-dim">· {Math.round(avgTps)} tok/s</span>}
      </button>
    </Popover>
  )
}

/* ── 2. Token 用量 ───────────────────────────────────────────── */
export function TokenUsagePopover() {
  const usage = useChatStore(s => s.usage)
  const u = usage

  return (
    <Popover
      trigger="hover"
      placement="top"
      mouseEnterDelay={0.15}
      styles={POPOVER_STYLES}
      content={
        <PopoverCard icon={<Icon name="coins" size={16} />} title="Token 用量"
          summary={u ? formatTokens(u.totalTokens) : '0'}>
          {u ? (
            <>
              <StatRow k="缓存命中" v={formatRatio(u.cacheHitRatio)} />
              <StatRow k="未缓存输入" v={`${formatTokens(u.uncachedInputTokens)} tok`} />
              <StatRow k="缓存读取" v={`${formatTokens(u.cachedTokens)} tok`} />
              <StatRow k="输出" v={`${formatTokens(u.outputTokens)} tok`} />
              <MiniBar pct={u.cacheHitRatio * 100} color="var(--success)" />
              {u.estimated && <div className="text-[12px] text-[var(--text-3)] mt-1">上下文构成为服务端估算值</div>}
            </>
          ) : (
            <>
              <StatRow k="缓存命中" v="—" muted />
              <StatRow k="未缓存输入" v="—" muted />
              <StatRow k="缓存读取" v="—" muted />
              <StatRow k="输出" v="—" muted />
              <div className="text-[12px] text-[var(--text-3)] mt-1">发起一轮对话后统计本轮用量</div>
            </>
          )}
        </PopoverCard>
      }
    >
      <button type="button" className="stat-trigger" title="Token 用量">
        <Icon name="coins" size={13} />
        <span>{u ? `${formatTokens(u.totalTokens)} tok` : 'Token 用量'}</span>
        {u && <span className="stat-trigger-dim">· 缓存命中 {formatRatio(u.cacheHitRatio)}</span>}
      </button>
    </Popover>
  )
}

/* ── 3. 上下文已用(缩略圆环)─────────────────────────────── */
export function ContextUsagePopover() {
  const usage = useChatStore(s => s.usage)
  const ctx = usage?.context ?? null
  /* 分母实时联动(2026-10-18):模型选择器/配置中心改上下文窗口后,
     即使当前无对话数据也应立刻反映到「/ xxxK」——优先 usage 里的
     provider 窗口,其次 store 的实时窗口(两者任一变化都刷新) */
  const liveWindow = useChatStore(s => s.contextUsage.window)
  const windowSize = ctx?.window || liveWindow || 192_000
  const used = ctx ? ctx.systemPrompt + ctx.toolDefs + ctx.messages : 0
  const pct = ctx
    ? (ctx.usedPct || Math.min(100, Math.round((used / Math.max(1, windowSize)) * 100)))
    : 0

  return (
    <Popover
      trigger="hover"
      placement="top"
      mouseEnterDelay={0.15}
      styles={POPOVER_STYLES}
      content={
        <PopoverCard icon={<Icon name="stack" size={16} />} title="上下文已用"
          summary={ctx
            ? `${formatTokens(used)} / ${formatTokens(windowSize)}`
            : `— / ${formatTokens(windowSize)}`}>
          {ctx ? (
            <>
              <StatRow k="系统提示词" v={`~${formatTokens(ctx.systemPrompt)} tok`} />
              <StatRow k="工具定义" v={`~${formatTokens(ctx.toolDefs)} tok`} />
              <StatRow k="对话消息" v={`~${formatTokens(ctx.messages)} tok`} />
              <MiniBar pct={pct} />
              <div className="text-[12px] text-[var(--text-3)] mt-1">
                已用 {pct}% · 服务端估算
              </div>
            </>
          ) : (
            <>
              <StatRow k="系统提示词" v="—" muted />
              <StatRow k="工具定义" v="—" muted />
              <StatRow k="对话消息" v="—" muted />
              <div className="text-[12px] text-[var(--text-3)] mt-1">发起一轮对话后展示上下文构成</div>
            </>
          )}
        </PopoverCard>
      }
    >
      <button type="button" className="stat-trigger" title="上下文已用">
        <RingGauge pct={pct} />
        <span>{ctx ? `${pct}%` : '上下文'}</span>
      </button>
    </Popover>
  )
}
