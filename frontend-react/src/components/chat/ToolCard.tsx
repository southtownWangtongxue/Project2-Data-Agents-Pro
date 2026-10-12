/**
 * ToolCard.tsx —— 工具调用卡(可展开详情;统一图标无前缀,避免流式视觉跳变)
 */
import type { Msg } from '@/sdk/protocol'

const LABEL_MAP: Record<string, string> = {
  input: '输入', result: '结果', status: '状态', info: '说明',
  sql: 'SQL', args: '参数', agent: '代理', phase: '阶段',
  chart_type: '图表类型', row_count: '返回行数',
}

function stringify(v: unknown, maxLen = 500): string {
  if (v === undefined || v === null) return ''
  if (typeof v === 'string') return v.slice(0, maxLen)
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  try {
    return (JSON.stringify(v, null, 2) ?? '').slice(0, maxLen)
  } catch {
    return String(v).slice(0, maxLen)
  }
}

export default function ToolCard({ msg }: { msg: Msg }) {
  const meta = msg.toolMeta || {}
  const oneLine = meta.result || meta.status || meta.input || meta.info || ''
  const oneLineText = oneLine
    ? (typeof oneLine === 'string' ? oneLine : JSON.stringify(oneLine)).slice(0, 60)
    : ''

  return (
    <div
      className="max-w-[82%] bg-[var(--cockpit-800)] border border-[var(--border)] border-l-2 border-l-brand rounded-r-md px-3 py-2 cursor-pointer transition-colors hover:bg-[var(--cockpit-700)] select-none"
      onClick={() => { msg.collapsed = !msg.collapsed }}
    >
      <div className="flex items-center gap-2 text-xs">
        <span className="flex-shrink-0">🔧</span>
        <span className="font-medium text-[var(--text-2)]">{msg.toolName || '工具'}</span>
        {oneLineText && (
          <span className="ml-auto text-[11px] text-[var(--text-3)] max-w-[240px] truncate mono">{oneLineText}</span>
        )}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`flex-shrink-0 text-[var(--text-3)] transition-transform ${msg.collapsed ? '' : 'rotate-180'}`}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
      {!msg.collapsed && Object.keys(meta).length > 0 && (
        <div className="mt-2 p-2.5 rounded text-[12px] text-[var(--text-2)] leading-relaxed whitespace-pre-wrap"
          style={{ background: 'rgba(112,86,248,0.03)' }}>
          {Object.entries(meta).map(([k, v]) =>
            v === undefined || v === null || v === '' ? null : (
              <div key={k} className="mb-1.5 last:mb-0">
                <span className="text-[var(--text-3)]">{LABEL_MAP[k] || k}:</span>
                <span className="mono ml-1">{stringify(v)}</span>
              </div>
            ),
          )}
        </div>
      )}
    </div>
  )
}
