/**
 * ResultTable.tsx —— 查询结果表格(antd Table,碳黑驾驶舱配色)
 */
import { Table } from 'antd'
import type { Msg } from '@/sdk/protocol'
import { useChatStore } from '@/stores/chat'

export default function ResultTable({ msg }: { msg: Msg }) {
  const store = useChatStore()
  const columns = (msg.columns || []).map(c => ({
    title: c,
    dataIndex: c,
    key: c,
    ellipsis: true,
    minWidth: 120,
  }))
  const rows = (msg.data || []).map((r, i) => ({ ...r, _key: i }))

  return (
    <div className="max-w-[92%] w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] font-medium text-[var(--text-1)]">查询结果</span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[var(--text-3)] mono">{msg.data?.length ?? 0} 条记录</span>
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
      <div className="rounded-lg overflow-hidden border border-[var(--border)]">
        <Table
          size="small"
          rowKey="_key"
          columns={columns}
          dataSource={rows}
          pagination={false}
          scroll={{ y: 360, x: 'max-content' }}
          bordered
        />
      </div>
    </div>
  )
}
