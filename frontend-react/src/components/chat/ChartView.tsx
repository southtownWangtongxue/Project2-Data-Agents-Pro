/**
 * ChartView.tsx —— ECharts 图表(复用后端产出的 option,注入暗色主题)
 */
import ReactECharts from 'echarts-for-react'
import type { Msg } from '@/sdk/protocol'

/** 暗色主题注入(与 Vue 端 injectDarkTheme 一致) */
function withDarkTheme(config: Record<string, unknown>): Record<string, unknown> {
  const result = { ...config }
  if (!result.textStyle) result.textStyle = { color: '#a1a1aa' }
  if (result.legend && typeof result.legend === 'object') {
    const legend = result.legend as Record<string, unknown>
    if (!legend.textStyle) legend.textStyle = { color: '#a1a1aa' }
  }
  for (const axis of ['xAxis', 'yAxis']) {
    if (result[axis] && typeof result[axis] === 'object') {
      const ax = result[axis] as Record<string, unknown>
      if (!ax.axisLabel) ax.axisLabel = { color: '#a1a1aa' }
    }
  }
  if (!result.backgroundColor) result.backgroundColor = 'transparent'
  return result
}

export default function ChartView({ msg }: { msg: Msg }) {
  const cfg = msg.chartConfig
  if (!cfg) return null
  const option = withDarkTheme(
    ((cfg as Record<string, unknown>).echarts_config as Record<string, unknown>) || (cfg as Record<string, unknown>),
  )
  const chartType = (cfg as Record<string, unknown>).chart_type as string | undefined
  const title = ((cfg as Record<string, unknown>).chart_title as string) || '数据可视化'

  return (
    <div className="max-w-[92%] w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] font-medium text-[var(--text-1)]">{title}</span>
        {chartType && (
          <span className="px-2 py-0.5 rounded-full text-[11px] text-brand-light mono capitalize"
            style={{ background: 'rgba(112,86,248,0.1)', border: '1px solid rgba(112,86,248,0.2)' }}>
            {chartType}
          </span>
        )}
      </div>
      <div className="rounded-lg overflow-hidden border border-[var(--border)] bg-[var(--cockpit-800)] p-3">
        <ReactECharts option={option} style={{ height: 360, width: '100%' }} notMerge lazyUpdate />
      </div>
    </div>
  )
}
