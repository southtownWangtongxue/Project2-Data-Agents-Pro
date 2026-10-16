/**
 * ApprovalCard.tsx —— 对话内审批卡(HITL)
 *
 * 语义:SSE 流在审批点挂起等待(对话被阻塞,心跳维持连接)。
 * - pending:紫磷光脉冲 + 「对话已暂停」说明 + 通过/拒绝/编辑后执行
 * - approved:打戳归档(绿),等待后端续流事件汇入对话
 * - edited:打戳归档(橙),展示原 SQL → 最终 SQL 对照
 * - rejected:打戳归档(红) + 终止说明
 *
 * 三态标签/文案/对照由 sdk/approval.ts 的纯函数派生(组件只做渲染)——
 * edited 必须独立成态:它放行了,与 rejected 语义相反,不可落进二值分支。
 */
import { useState } from 'react'
import { App, Button, Input, Space, Spin, Tag } from 'antd'
import type { Msg } from '@/sdk/protocol'
import { approvalViewState } from '@/sdk/approval'
import { useChatStore } from '@/stores/chat'

type Decision = 'approved' | 'rejected' | 'edited'

export default function ApprovalCard({ msg }: { msg: Msg }) {
  const store = useChatStore()
  const { message } = App.useApp()
  const [comment, setComment] = useState('')
  const [editing, setEditing] = useState(false)
  const [editedSql, setEditedSql] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const approval = msg.approval!
  const pending = approval.state === 'pending'
  const view = approvalViewState(approval)

  const decide = async (state: Decision) => {
    const sql = editedSql.trim()
    // edit 必须带非空且与原 SQL 不同的 SQL(后端 schema 拒空值;相同则无意义),
    // 这里先拦一道给即时反馈,免得点了才看到 422
    if (state === 'edited' && (!sql || sql === approval.sql)) {
      message.warning('请先修改 SQL 后再提交(不能与原 SQL 相同)')
      return
    }
    setSubmitting(true)
    try {
      await store.resolveApprovalMsg(msg.id, state, comment, state === 'edited' ? sql : undefined)
    } catch (e) {
      message.error(`审批提交失败:${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const openEditor = () => {
    setEditedSql(approval.sql)
    setEditing(true)
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
        {view.tag && (
          <Tag color={view.tag.color} className="ml-auto">
            {view.tag.text}
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
          {editing && (
            <Input.TextArea
              size="small"
              autoSize={{ minRows: 3, maxRows: 8 }}
              className="mono"
              value={editedSql}
              onChange={e => setEditedSql(e.target.value)}
              placeholder="修改后的 SQL(将替换上方原 SQL 执行)"
            />
          )}
          <Input
            size="small"
            placeholder="审批意见(可选)"
            value={comment}
            onChange={e => setComment(e.target.value)}
            onPressEnter={() => !editing && decide('approved')}
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
            {editing ? (
              <Button
                size="small"
                type="primary"
                ghost
                loading={submitting}
                onClick={() => decide('edited')}
              >
                按修改后执行
              </Button>
            ) : (
              <Button size="small" onClick={openEditor}>
                修改 SQL 后执行
              </Button>
            )}
            <Button size="small" danger loading={submitting} onClick={() => decide('rejected')}>
              拒绝
            </Button>
          </Space>
        </div>
      ) : (
        <div className="space-y-1.5">
          {view.showDiff && view.diff && (
            <div className="text-[11px]">
              <div className="text-[var(--text-3)] mb-1">实际执行的 SQL:</div>
              <pre className="mono text-[12px] rounded p-2 whitespace-pre-wrap break-all"
                style={{ color: 'var(--text-1)', background: 'var(--code-bg)', border: '1px solid var(--border)' }}>
                {view.diff.to}
              </pre>
            </div>
          )}
          <div className="text-[11px] text-[var(--text-3)]">
            {view.footer}
            {approval.comment && <span className="ml-2">意见:{approval.comment}</span>}
          </div>
        </div>
      )}
    </div>
  )
}