/**
 * pages/admin/SkillConfig.tsx —— 技能管理(安装 / 启停)
 */
import { useEffect, useState } from 'react'
import { App, Button, Table, Tag, Switch } from 'antd'
import { api } from '@/api/client'

interface Skill {
  id: string
  name: string
  type?: string
  description?: string
  enabled?: boolean
  installed?: boolean
}

export default function SkillConfig() {
  const { message } = App.useApp()
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api<{ skills: Skill[] }>('/config/skills')
      setSkills(data.skills || [])
    } catch (e) {
      message.error(`加载技能失败:${(e as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const act = async (id: string, action: 'install' | 'uninstall') => {
    try {
      await api(`/config/skills/${action}`, { method: 'POST', body: { id } })
      message.success(action === 'install' ? '已安装' : '已卸载')
      load()
    } catch (e) {
      message.error(`操作失败:${(e as Error).message}`)
    }
  }

  const toggle = async (s: Skill, enabled: boolean) => {
    try {
      await api(`/config/skills/${s.id}`, { method: 'PUT', body: { ...s, enabled } })
      load()
    } catch (e) {
      message.error(`切换失败:${(e as Error).message}`)
    }
  }

  const columns = [
    { title: '技能', key: 'name',
      render: (_: unknown, s: Skill) => (
        <div>
          <div className="text-[13px] text-[var(--text-1)]">{s.name || s.id}</div>
          <div className="text-[10px] text-[var(--text-3)] mono">{s.id}</div>
        </div>
      ) },
    { title: '说明', dataIndex: 'description', key: 'description',
      render: (v: string) => <span className="text-[12px] text-[var(--text-2)]">{v || '—'}</span> },
    { title: '类型', dataIndex: 'type', key: 'type', width: 90,
      render: (v: string) => <Tag>{v || 'builtin'}</Tag> },
    { title: '状态', key: 'state', width: 110,
      render: (_: unknown, s: Skill) => (
        <Tag color={s.installed ? 'green' : 'default'}>{s.installed ? '已安装' : '未安装'}</Tag>
      ) },
    { title: '启用', key: 'enabled', width: 70,
      render: (_: unknown, s: Skill) => <Switch size="small" checked={!!s.enabled} onChange={v => toggle(s, v)} /> },
    { title: '操作', key: 'ops', width: 120,
      render: (_: unknown, s: Skill) => (
        <Button size="small" type={s.installed ? 'default' : 'primary'}
          style={s.installed ? {} : { background: '#7056F8', borderColor: '#7056F8' }}
          onClick={() => act(s.id, s.installed ? 'uninstall' : 'install')}>
          {s.installed ? '卸载' : '安装'}
        </Button>
      ) },
  ]

  return (
    <div className="max-w-5xl">
      <div className="mb-4">
        <h1 className="text-xl font-semibold m-0">技能管理</h1>
        <div className="text-[12px] text-[var(--text-3)] mt-0.5">Skills 安装与启停(热更新即时生效)</div>
      </div>
      <div className="rounded-xl border border-[var(--border)] overflow-hidden">
        <Table rowKey="id" columns={columns} dataSource={skills} pagination={false} loading={loading} size="middle" />
      </div>
    </div>
  )
}