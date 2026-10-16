/**
 * approval.ts —— 审批卡展示派生(纯函数)
 *
 * 抽成纯函数而非留在组件里:三态的标签/文案/对照是有明确契约的展示逻辑,
 * 且组件渲染测试在本项目无先例(无 testing-library),纯函数可用现有 vitest 锁定。
 *
 * 契约要点:edited 是**独立第三态**——它放行了(与 rejected 的语义相反),
 * 不可落进 approved/rejected 的二值分支(旧实现会把它显示成红色「已拒绝」)。
 */
import type { Msg } from './protocol'

type Approval = NonNullable<Msg['approval']>

export interface ApprovalViewState {
  /** 状态标签;pending 为 null(进行中靠脉冲点表达,不打戳) */
  tag: { color: 'green' | 'red' | 'orange'; text: string } | null
  /** 归档说明文案 */
  footer: string
  /** 是否展示「原 SQL → 最终 SQL」对照 */
  showDiff: boolean
  diff?: { from: string; to: string }
}

const VIEW: Record<
  Exclude<Approval['state'], 'pending'>,
  { tag: NonNullable<ApprovalViewState['tag']>; footer: string }
> = {
  approved: { tag: { color: 'green', text: '已通过' }, footer: '已放行,执行结果将自动续流到本对话' },
  rejected: { tag: { color: 'red', text: '已拒绝' }, footer: '流程已终止' },
  // edited 放行了但 SQL 被改过,用橙色与 approved 区分,避免与 rejected 混淆
  edited: { tag: { color: 'orange', text: '已修改执行' }, footer: '已按修改后的 SQL 放行,执行结果将续流到本对话' },
}

export function approvalViewState(approval: Approval): ApprovalViewState {
  if (approval.state === 'pending') {
    return { tag: null, footer: '', showDiff: false }
  }
  const view = VIEW[approval.state]
  const edited = approval.editedSql?.trim()
  // 仅当改后 SQL 与原 SQL 确实不同才展示对照(没改动就不必占版面)
  const changed = Boolean(edited) && edited !== approval.sql
  return {
    tag: view.tag,
    footer: view.footer,
    showDiff: changed,
    ...(changed ? { diff: { from: approval.sql, to: edited! } } : {}),
  }
}
