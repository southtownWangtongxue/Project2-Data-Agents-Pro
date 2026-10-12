/**
 * ApprovalCard.tsx —— 对话内审批卡(HITL)
 * 紫色左边线 + 醒目操作;pending 脉冲;完成后打戳归档。
 */
import { useState } from 'react'
import { Button, Input, Space, Tag } from 'antd'
import type { Msg } from '@/sdk/protocol'
import { useChatStore } from '@/stores/chat'

export default function ApprovalCard({ msg }: { msg: Msg }) {
  const store = useChatStore()
  const [comment, setComment] = useState('')
  const approval = msg.approval!
  const pending = approval.state === 'pending'

  return (
    <div className="max-w-[88%] rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/[0.04] p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-2 h-2 rounded-full ${pending ? 'bg-[var(--warning)] brand-pulse' : 'bg-[var(--success)]'}`} />
        <span className="text-[13px] font-semibold text-[var(--warning)]">高危操作待审批</span>
        {!pending && (
          <Tag color={approval.state === 'approved' ? 'green' : 'red'} className="ml-auto">
            {approval.state === 'approved' ? '已通过' : '已拒绝'}
          </Tag>
        )}
      </div>
      {approval.reason && <div className="text-[12px] text-[var(--text-2)] mb-1.5">原因:{approval.reason}</div>}
      {approval.sql && (
        <pre className="mono text-[12px] text-[#e2e8f0] bg-[#0d0d0f] border border-[var(--border)] rounded p-2 mb-2 whitespace-pre-wrap break-all">{approval.sql}</pre>
      )}
      {pending ? (
        <div className="space-y-2">
          <Input
            size="small"
            placeholder="审批意见(可选)"
            value={comment}
            onChange={e => setComment(e.target.value)}
          />
          <Space>
            <Button
              size="small"
              type="primary"
              style={{ background: '#7056F8', borderColor: '#7056F8' }}
              onClick={() => store.resolveApprovalMsg(msg.id, 'approved', comment)}
            >
              通过并继续
            </Button>
            <Button size="small" danger onClick={() => store.resolveApprovalMsg(msg.id, 'rejected', comment)}>
              拒绝
            </Button>
          </Space>
        </div>
      ) : (
        approval.comment && <div className="text-[11px] text-[var(--text-3)]">意见:{approval.comment}</div>
      )}
    </div>
  )
}
