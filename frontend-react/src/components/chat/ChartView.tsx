/**
 * ChartView.tsx —— ECharts 图表(复用后端产出的 option,按当前主题注入坐标轴/图例配色)
 */
import ReactECharts from 'echarts-for-react'
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

  const axisColor = mode === 'dark' ? '#a1a1aa' : '#52525b'
  const option = withTheme(
    ((cfg as Record<string, unknown>).echarts_config as Record<string, unknown>) || (cfg as Record<string, unknown>),
    axisColor,
  )
  const chartType = (cfg as Record<string, unknown>).chart_type as string | undefined
  const title = ((cfg as Record<string, unknown>).chart_title as string) || '数据可视化'

  return (
    <div className="max-w-[92%] w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] font-medium text-[var(--text-1)]">{title}</span>
        {chartType && (
          <span className="px-2 py-0.5 rounded-full text-[11px] mono capitalize"
            style={{ color: 'var(--brand-light)', background: 'rgba(112,86,248,0.1)', border: '1px solid rgba(112,86,248,0.2)' }}>
            {chartType}
          </span>
        )}
      </div>
      <div className="rounded-lg overflow-hidden border p-3" style={{ borderColor: 'var(--border)', background: 'var(--cockpit-800)' }}>
        <ReactECharts option={option} style={{ height: 360, width: '100%' }} notMerge lazyUpdate />
      </div>
    </div>
  )
}