/**
 * ApprovalCard.tsx —— 对话内审批卡(HITL)
 *
 * 语义:SSE 流在审批点挂起等待(对话被阻塞,心跳维持连接)。
 * - pending:紫磷光脉冲 + 「对话已暂停」说明 + 通过/拒绝
 * - approved:打戳归档,等待后端续流事件汇入对话
 * - rejected:打戳归档 + 终止说明
 */
import { useState } from 'react'
import { App, Button, Input, Space, Spin, Tag } from 'antd'
import type { Msg } from '@/sdk/protocol'
import { useChatStore } from '@/stores/chat'

export default function ApprovalCard({ msg }: { msg: Msg }) {
  const store = useChatStore()
  const { message } = App.useApp()
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const approval = msg.approval!
  const pending = approval.state === 'pending'

  const decide = async (state: 'approved' | 'rejected') => {
    setSubmitting(true)
    try {
      await store.resolveApprovalMsg(msg.id, state, comment)
    } catch (e) {
      message.error(`审批提交失败:${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-[88%] rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/[0.04] p-3">
      <div className="flex items-center gap-2 mb-2">
        {pending ? (
          <span className="w-2 h-2 rounded-full bg-[var(--warning)] brand-pulse" />
        ) : (
          <span className="w-2 h-2 rounded-full bg-[var(--success)]" />
        )}
        <span className="text-[13px] font-semibold text-[var(--warning)]">高危操作待审批</span>
        {submitting && <Spin size="small" />}
        {!pending && (
          <Tag color={approval.state === 'approved' ? 'green' : 'red'} className="ml-auto">
            {approval.state === 'approved' ? '已通过' : '已拒绝'}
          </Tag>
        )}
      </div>

      {pending && (
        <div className="text-[11px] text-[var(--text-3)] mb-2 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-brand brand-pulse" />
          对话已在此处暂停,你的决定将直接决定后续执行(5 分钟内未处理将自动拒绝)
        </div>
      )}

      {approval.reason && <div className="text-[12px] text-[var(--text-2)] mb-1.5">原因:{approval.reason}</div>}
      {approval.sql && (
        <pre className="mono text-[12px] rounded p-2 mb-2 whitespace-pre-wrap break-all"
          style={{ color: 'var(--text-1)', background: 'var(--code-bg)', border: '1px solid var(--border)' }}>
          {approval.sql}
        </pre>
      )}

      {pending ? (
        <div className="space-y-2">
          <Input
            size="small"
            placeholder="审批意见(可选)"
            value={comment}
            onChange={e => setComment(e.target.value)}
            onPressEnter={() => decide('approved')}
          />
          <Space>
            <Button
              size="small"
              type="primary"
              loading={submitting}
              onClick={() => decide('approved')}
            >
              通过并继续
            </Button>
            <Button size="small" danger loading={submitting} onClick={() => decide('rejected')}>
              拒绝
            </Button>
          </Space>
        </div>
      ) : (
        <div className="text-[11px] text-[var(--text-3)]">
          {approval.state === 'approved'
            ? '已放行,执行结果将自动续流到本对话'
            : '流程已终止'}
          {approval.comment && <span className="ml-2">意见:{approval.comment}</span>}
        </div>
      )}
    </div>
  )
}