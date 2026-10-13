/**
 * ToolCard.tsx —— 工具调用卡(可展开详情;统一图标无前缀,避免流式视觉跳变)
 */
import { useState } from 'react'
import { Wrench } from 'lucide-react'
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
  /* 折叠态存于组件本地:直接改写 msg.collapsed 不会触发渲染 */
  const [collapsed, setCollapsed] = useState(msg.collapsed ?? true)
  const meta = msg.toolMeta || {}
  const oneLine = meta.result || meta.status || meta.input || meta.info || ''
  const oneLineText = oneLine
    ? (typeof oneLine === 'string' ? oneLine : JSON.stringify(oneLine)).slice(0, 60)
    : ''

  return (
    <div
      className="max-w-[82%] rounded-lg border-l-2 border-l-brand px-3 py-2 cursor-pointer transition-colors select-none"
      style={{ background: 'var(--cockpit-800)', border: '1px solid var(--border)', borderLeftColor: 'var(--brand)' }}
      onClick={() => setCollapsed(v => !v)}
    >
      <div className="flex items-center gap-2 text-xs">
        <Wrench size={13} className="flex-shrink-0" style={{ color: 'var(--brand-light)' }} />
        <span className="font-medium text-[var(--text-2)]">{msg.toolName || '工具'}</span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded mono"
          style={{
            color: msg.toolPhase === 'done' ? 'var(--success)' : 'var(--warning)',
            background: msg.toolPhase === 'done' ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
          }}
        >
          {msg.toolPhase === 'done' ? '完成' : '执行中'}
        </span>
        {oneLineText && (
          <span className="ml-auto text-[11px] text-[var(--text-3)] max-w-[240px] truncate mono">{oneLineText}</span>
        )}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`flex-shrink-0 text-[var(--text-3)] transition-transform ${collapsed ? '' : 'rotate-180'}`}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
      {!collapsed && Object.keys(meta).length > 0 && (
        <div className="mt-2 p-2.5 rounded text-[12px] text-[var(--text-2)] leading-relaxed whitespace-pre-wrap"
          style={{ background: 'rgba(112,86,248,0.05)' }}>
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