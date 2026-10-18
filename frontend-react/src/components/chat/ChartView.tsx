/**
 * ChartView.tsx —— ECharts 图表(复用后端产出的 option,按当前主题注入坐标轴/图例配色)
 * 阶段 B:卡片表面换 SpotlightCard 聚光(与结果表/SQL/工具卡视觉统一)
 */
import ReactECharts from 'echarts-for-react'
import SpotlightCard from '@/components/bits/reactbits/SpotlightCard'
import type { Msg } from '@/sdk/protocol'
import { useThemeStore } from '@/stores/theme'

/** 主题配色注入(轴标签 / 图例 / 背景) */
function withTheme(config: Record<string, unknown>, axisColor: string): Record<string, unknown> {
  const result = { ...config }
  if (!result.textStyle) result.textStyle = { color: axisColor }
  if (result.legend && typeof result.legend === 'object') {
    const legend = result.legend as Record<string, unknown>
    if (!legend.textStyle) legend.textStyle = { color: axisColor }
  }
  for (const axis of ['xAxis', 'yAxis']) {
    if (result[axis] && typeof result[axis] === 'object') {
      const ax = result[axis] as Record<string, unknown>
      if (!ax.axisLabel) ax.axisLabel = { color: axisColor }
      if (!ax.axisLine) ax.axisLine = { lineStyle: { color: axisColor, opacity: 0.35 } }
      if (!ax.splitLine) ax.splitLine = { lineStyle: { color: axisColor, opacity: 0.16 } }
    }
  }
  if (!result.backgroundColor) result.backgroundColor = 'transparent'
  return result
}

export default function ChartView({ msg }: { msg: Msg }) {
  const mode = useThemeStore(s => s.mode)
  const cfg = msg.chartConfig
  if (!cfg) return null

  /* GitHub:fg.muted(暗 #8B949E / 亮 #59636E) */
  const axisColor = mode === 'dark' ? '#8b949e' : '#59636e'
  const option = withTheme(
    ((cfg as Record<string, unknown>).echarts_config as Record<string, unknown>) || (cfg as Record<string, unknown>),
    axisColor,
  )
  const chartType = (cfg as Record<string, unknown>).chart_type as string | undefined
  const title = ((cfg as Record<string, unknown>).chart_title as string) || '数据可视化'

  return (
    <div className="w-full min-w-0">
      {/* 标题行:标题 truncate + 徽标不换行(修复标题与 badge 重叠) */}
      <div className="flex items-center gap-2 mb-2 min-w-0">
        <span className="text-[13px] font-medium text-[var(--text-1)] truncate min-w-0">{title}</span>
        {chartType && (
          <span className="px-2 py-0.5 rounded-full text-[11px] mono capitalize flex-shrink-0"
            style={{ color: 'var(--brand-light)', background: 'rgba(112,86,248,0.1)', border: '1px solid rgba(112,86,248,0.2)' }}>
            {chartType}
          </span>
        )}
      </div>
      <SpotlightCard
        className="w-full p-3"
        spotlightColor="#8B6FFF"
        intensity={0.13}
        spotlightSize={360}
        proximity={90}
        borderGlow={0.5}
        style={{
          ['--spotlight-card-surface' as string]: 'var(--cockpit-800)',
          ['--spotlight-card-border' as string]: 'var(--border)',
          borderRadius: 10,
        }}
      >
        <ReactECharts option={option} style={{ height: 320, width: '100%' }} notMerge lazyUpdate />
      </SpotlightCard>
    </div>
  )
}