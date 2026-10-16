/**
 * approval.test.ts —— 对话内审批状态机(TDD)
 * 覆盖:pending → approved/rejected 本地推进、approval_state 打戳(超时/拒绝)、
 * 审批卡的恢复语义(消息保留不清除)。
 */
import { describe, it, expect } from 'vitest'
import { applyEvent, initialChatState, resolveApproval } from './reducer'
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
      type: E.STATUS,
      content: '该高危操作已被拒绝，流程终止（审批超时（5 分钟），自动拒绝）',
      approval_state: 'rejected',
    })
    const card = next.messages.find(m => m.kind === 'approval')!
    expect(card.approval?.state).toBe('rejected')
    // 状态消息保留(终止原因可见)
    expect(next.messages.some(m => m.kind === 'status' && m.content?.includes('已被拒绝'))).toBe(true)
  })

  it('打戳只作用于当前会话的 pending 卡', () => {
    let s = withPendingApproval()
    // 另一会话的审批卡
    s = applyEvent(s, { type: E.NODE_STARTED, agent: 'security', label: '安全审核', step_id: 9 })
    s = applyEvent(s, {
      type: E.APPROVAL_REQUIRED, thread_id: 'admin:other', question: 'q', sql: 's', reason: 'r', step_id: 9,
    })
    const next = applyEvent(s, { type: E.STATUS, content: 'x', approval_state: 'rejected' })
    const cards = next.messages.filter(m => m.kind === 'approval')
    expect(cards[0].approval?.state).toBe('rejected')   // admin:t1(thread 匹配)
    expect(cards[1].approval?.state).toBe('pending')    // admin:other 不受影响
  })
})