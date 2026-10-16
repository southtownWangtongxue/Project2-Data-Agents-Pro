/**
 * approval.test.ts —— 对话内审批状态机(TDD)
 * 覆盖:pending → approved/rejected/edited 本地推进、approval_state 打戳(超时/拒绝)、
 * 审批卡的恢复语义(消息保留不清除)、三态展示派生(approvalViewState)。
 */
import { describe, it, expect } from 'vitest'
import { applyEvent, initialChatState, resolveApproval } from './reducer'
import { approvalViewState } from './approval'
import { E } from './protocol'

function withPendingApproval() {
  let s = initialChatState()
  s = applyEvent(s, { type: E.THREAD_ID, thread_id: 'admin:t1' })
  s = applyEvent(s, { type: E.NODE_STARTED, agent: 'security', label: '安全审核', step_id: 4 })
  s = applyEvent(s, {
    type: E.APPROVAL_REQUIRED, thread_id: 'admin:t1', question: '删除订单',
    sql: 'DELETE FROM orders', reason: '写操作', step_id: 4,
  })
  return s
}

describe('对话内审批状态机', () => {
  it('approval_required 生成 pending 审批消息', () => {
    const s = withPendingApproval()
    const card = s.messages.find(m => m.kind === 'approval')!
    expect(card.approval?.state).toBe('pending')
    expect(card.approval?.sql).toBe('DELETE FROM orders')
  })

  it('点击通过:本地置为 approved(等待后端续流事件)', () => {
    const s = withPendingApproval()
    const card = s.messages.find(m => m.kind === 'approval')!
    const next = resolveApproval(s, card.id, 'approved', '同意执行')
    const updated = next.messages.find(m => m.id === card.id)!
    expect(updated.approval?.state).toBe('approved')
    expect(updated.approval?.comment).toBe('同意执行')
  })

  it('拒绝:置为 rejected', () => {
    const s = withPendingApproval()
    const card = s.messages.find(m => m.kind === 'approval')!
    const next = resolveApproval(s, card.id, 'rejected', '风险过高')
    expect(next.messages.find(m => m.id === card.id)!.approval?.state).toBe('rejected')
  })

  it('编辑后执行:置为 edited 并记录最终执行的 SQL', () => {
    const s = withPendingApproval()
    const card = s.messages.find(m => m.kind === 'approval')!
    const next = resolveApproval(s, card.id, 'edited', '加了 WHERE 限定范围',
      'DELETE FROM orders WHERE id = 1')
    const updated = next.messages.find(m => m.id === card.id)!.approval!
    expect(updated.state).toBe('edited')
    expect(updated.editedSql).toBe('DELETE FROM orders WHERE id = 1')
    expect(updated.comment).toBe('加了 WHERE 限定范围')
    // 原 SQL 保留(审批卡可见改了什么)
    expect(updated.sql).toBe('DELETE FROM orders')
  })

  it('后端 approval_state=rejected(拒绝/超时)自动打戳 pending 卡', () => {
    const s = withPendingApproval()
    const next = applyEvent(s, {
      type: E.STATUS, content: '审批超时（5 分钟），已自动拒绝。', approval_state: 'rejected',
    })
    expect(next.messages.find(m => m.kind === 'approval')!.approval?.state).toBe('rejected')
  })
})

// ── 三态展示派生:纯函数(组件只做渲染)──────────────────────

describe('approvalViewState: 三态展示', () => {
  const base = { threadId: 'admin:t1', question: 'q', sql: 'DELETE FROM orders', reason: '写操作' }

  it('pending:无状态标签(靠脉冲点表达进行中)', () => {
    const v = approvalViewState({ ...base, state: 'pending' })
    expect(v.tag).toBeNull()
  })

  it('approved:绿色「已通过」+ 已放行说明', () => {
    const v = approvalViewState({ ...base, state: 'approved' })
    expect(v.tag).toEqual({ color: 'green', text: '已通过' })
    expect(v.footer).toContain('已放行')
  })

  it('rejected:红色「已拒绝」+ 流程终止说明', () => {
    const v = approvalViewState({ ...base, state: 'rejected' })
    expect(v.tag).toEqual({ color: 'red', text: '已拒绝' })
    expect(v.footer).toContain('已终止')
  })

  it('edited:不得被误显示为「已拒绝」(第三态,橙色)', () => {
    // 回归锁定:旧实现是 approved?'green':'red' + ('已通过':'已拒绝'),
    // edited 会落进 red/已拒绝 分支——语义完全错(它放行了,只是改了 SQL)
    const v = approvalViewState({
      ...base, state: 'edited', editedSql: 'DELETE FROM orders WHERE id = 1',
    })
    expect(v.tag).toEqual({ color: 'orange', text: '已修改执行' })
    expect(v.footer).toContain('已按修改后的 SQL 放行')
  })

  it('edited:展示原 SQL 与最终 SQL 的对照(审批人可见改了什么)', () => {
    const v = approvalViewState({
      ...base, state: 'edited', editedSql: 'DELETE FROM orders WHERE id = 1',
    })
    expect(v.showDiff).toBe(true)
    expect(v.diff?.from).toBe('DELETE FROM orders')
    expect(v.diff?.to).toBe('DELETE FROM orders WHERE id = 1')
  })

  it('非 edited 态不展示 SQL 对照', () => {
    const v = approvalViewState({ ...base, state: 'approved' })
    expect(v.showDiff).toBe(false)
  })
})
