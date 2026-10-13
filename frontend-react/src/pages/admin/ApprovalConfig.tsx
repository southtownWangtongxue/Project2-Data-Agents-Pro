/**
 * pages/admin/ApprovalConfig.tsx —— 审批策略(对话内审批的权限范围)
 * 复用 /approve/policy;tier 由管理员统一在此配置
 */
import { useEffect, useState } from 'react'
import { App, Button, Modal, Radio, Tag } from 'antd'
import { api } from '@/api/client'

const TIERS = [
  {
    value: 'read_only',
    label: '严格模式 · 全部人工审批',
    desc: '所有写操作(DML/DDL)均需管理员在对话内审批。最安全的默认档位。',
    tone: 'green' as const,
  },
  {
    value: 'workspace_write',
    label: '平衡模式 · DML 自动放行',
    desc: '常规数据写入(DML)自动执行;DDL、权限变更等高危操作仍需审批。',
    tone: 'gold' as const,
  },
  {
    value: 'full_access',
    label: '全权模式 · 全部自动放行(危险)',
    desc: '所有 SQL 直接执行,不再触发审批。仅在受控演示环境使用。',
    tone: 'red' as const,
  },
]

export default function ApprovalConfig() {
  const { message } = App.useApp()
  const [tier, setTier] = useState('')
  const [pending, setPending] = useState('')

  useEffect(() => {
    api<{ tier: string }>('/approve/policy')
      .then(d => setTier(d.tier))
      .catch(() => setTier(''))
  }, [])

  const save = (value: string) => {
    const commit = async (confirm: boolean) => {
      setPending(value)
      try {
        await api('/approve/policy', { method: 'PUT', body: { tier: value, confirm } })
        setTier(value)
        message.success('审批档位已生效(热更新)')
      } catch (e) {
        message.error(`设置失败:${(e as Error).message}`)
      } finally {
        setPending('')
      }
    }
    if (value === 'full_access') {
      Modal.confirm({
        title: '确认切换到全权模式?',
        content: '所有 SQL 将直接执行,不再触发审批。生产环境请谨慎。',
        okText: '我已知悉,切换',
        okButtonProps: { danger: true },
        cancelText: '取消',
        onOk: () => commit(true),
      })
    } else {
      commit(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-4">
        <h1 className="text-xl font-semibold m-0">审批策略</h1>
        <div className="text-[12px] text-[var(--text-3)] mt-0.5">
          高危 SQL 触发对话内审批(HITL)时的权限范围 · 仅管理员可修改
        </div>
      </div>

      <div className="space-y-3">
        {TIERS.map(t => {
          const active = tier === t.value
          return (
            <div
              key={t.value}
              className={`rounded-xl border p-4 transition-colors ${
                active ? 'border-brand/40 bg-brand/[0.06]' : 'border-[var(--border)] bg-[var(--cockpit-800)]'
              }`}
            >
              <div className="flex items-center gap-3">
                <Radio checked={active} onChange={() => save(t.value)} disabled={pending === t.value} />
                <span className="text-[14px] font-medium text-[var(--text-1)]">{t.label}</span>
                {active && <Tag color="purple" className="ml-auto">当前档位</Tag>}
              </div>
              <div className="text-[12px] text-[var(--text-2)] mt-2 ml-6 leading-relaxed">{t.desc}</div>
            </div>
          )
        })}
      </div>

      <div className="mt-6 text-[11px] text-[var(--text-3)] leading-relaxed border-t border-[var(--border)] pt-3">
        说明:审批本身遵循职责分离原则——发起人不可自审,仅管理员(user_type=00)可审批;
        每次审批动作都会落库审计,可在审批记录接口查询。
      </div>
    </div>
  )
}