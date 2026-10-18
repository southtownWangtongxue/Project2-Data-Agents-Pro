/**
 * ResultTable.tsx —— 查询结果表格(antd Table + SpotlightCard 聚光表面)
 */
import { Table } from 'antd'
import SpotlightCard from '@/components/bits/reactbits/SpotlightCard'
import type { Msg } from '@/sdk/protocol'
import { useChatStore } from '@/stores/chat'

export default function ResultTable({ msg }: { msg: Msg }) {
  const store = useChatStore()
  const columns = (msg.columns || []).map(c => ({
    title: <span className="whitespace-nowrap">{c}</span>,
    dataIndex: c,
    key: c,
    ellipsis: true,
    /* antd Table 只认 width(minWidth 无效):列宽 140 起,超出容器横向滚动 */
    width: 140,
  }))
  const rows = (msg.data || []).map((r, i) => ({ ...r, _key: i }))

  return (
    <div className="w-full min-w-0">
      <div className="flex items-center gap-2 mb-2 min-w-0">
        <span className="text-[13px] font-medium text-[var(--text-1)] flex-shrink-0">查询结果</span>
        <span className="text-[11px] text-[var(--text-3)] mono flex-shrink-0">{msg.data?.length ?? 0} 条记录</span>
        <div className="flex items-center gap-2 ml-auto flex-shrink-0">
          {msg.data?.length && msg.columns?.length && (
            <>
              <button type="button" onClick={() => store.exportData(msg.data!, msg.columns!, 'csv')}
                className="px-2.5 py-1 text-[11px] text-[var(--text-3)] bg-transparent border border-[var(--border)] rounded cursor-pointer hover:text-[var(--text-2)] transition-colors">
                CSV
              </button>
              <button type="button" onClick={() => store.exportData(msg.data!, msg.columns!, 'excel')}
                className="px-2.5 py-1 text-[11px] text-[var(--text-3)] bg-transparent border border-[var(--border)] rounded cursor-pointer hover:text-[var(--success)] hover:border-[var(--success)]/30 transition-colors">
                Excel
              </button>
            </>
          )}
        </div>
      </div>
      <SpotlightCard
        className="w-full"
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
        <Table
          size="small"
          rowKey="_key"
          columns={columns}
          dataSource={rows}
          pagination={false}
          scroll={{ y: 360, x: 'max-content' }}
          bordered
        />
      </SpotlightCard>
    </div>
  )
}
