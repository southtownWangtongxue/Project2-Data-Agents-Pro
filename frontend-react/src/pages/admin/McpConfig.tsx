/**
 * pages/admin/McpConfig.tsx —— MCP 服务管理(增删改 + 连通性测试)
 */
import { useEffect, useState } from 'react'
import { App, Button, Form, Input, Modal, Switch, Table, Tag } from 'antd'
import { api } from '@/api/client'

interface McpServer {
  id: string
  name: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  enabled?: boolean
}

const EMPTY: Partial<McpServer> = { id: '', name: '', command: '', args: [], env: {}, enabled: true }

export default function McpConfig() {
  const { message } = App.useApp()
  const [servers, setServers] = useState<McpServer[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<Partial<McpServer> | null>(null)
  const [isNew, setIsNew] = useState(false)
  const [testing, setTesting] = useState('')
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const data = await api<{ servers: McpServer[] }>('/config/mcp')
      setServers(data.servers || [])
    } catch (e) {
      message.error(`加载 MCP 列表失败:${(e as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openEdit = (s?: McpServer) => {
    setIsNew(!s)
    setEditing(s ?? EMPTY)
    form.setFieldsValue(s ?? EMPTY)
  }

  const save = async () => {
    const v = await form.validateFields()
    const args = typeof v.args === 'string'
      ? v.args.split(/\s+/).filter(Boolean)
      : (v.args ?? [])
    try {
      if (isNew) await api('/config/mcp', { method: 'POST', body: { ...editing, ...v, args } })
      else await api(`/config/mcp/${v.id}`, { method: 'PUT', body: { ...editing, ...v, args } })
      message.success('已保存')
      setEditing(null)
      load()
    } catch (e) {
      message.error(`保存失败:${(e as Error).message}`)
    }
  }

  const remove = (s: McpServer) => {
    Modal.confirm({
      title: '删除 MCP 服务',
      content: `确认删除「${s.name || s.id}」?`,
      okText: '删除', okButtonProps: { danger: true }, cancelText: '取消',
      onOk: async () => {
        await api(`/config/mcp/${s.id}`, { method: 'DELETE' }).catch(() => {})
        load()
      },
    })
  }

  const test = async (s: McpServer) => {
    setTesting(s.id)
    try {
      const r = await api<{ ok: boolean; message?: string }>('/config/mcp/test', { method: 'POST', body: s })
      if (r.ok) message.success(`连接成功:${s.name || s.id}`)
      else message.error(`连接失败:${r.message || '未知错误'}`)
    } catch (e) {
      message.error(`测试失败:${(e as Error).message}`)
    } finally {
      setTesting('')
    }
  }

  const columns = [
    { title: '服务', key: 'name',
      render: (_: unknown, s: McpServer) => (
        <div>
          <div className="text-[13px] text-[var(--text-1)]">{s.name || s.id}</div>
          <div className="text-[10px] text-[var(--text-3)] mono">
            {s.url || s.command || '—'}
          </div>
        </div>
      ) },
    { title: '参数', key: 'args', width: 260,
      render: (_: unknown, s: McpServer) => (
        <span className="text-[11px] text-[var(--text-2)] mono">{(s.args || []).join(' ')}</span>
      ) },
    { title: '启用', key: 'enabled', width: 70,
      render: (_: unknown, s: McpServer) => (
        <Switch size="small" checked={!!s.enabled}
          onChange={async v => { await api(`/config/mcp/${s.id}`, { method: 'PUT', body: { ...s, enabled: v } }).catch(() => {}); load() }} />
      ) },
    { title: '操作', key: 'ops', width: 170,
      render: (_: unknown, s: McpServer) => (
        <div className="flex gap-2">
          <button type="button" disabled={testing === s.id}
            onClick={() => test(s)}
            className="text-[11px] text-brand-light bg-transparent border-none cursor-pointer disabled:opacity-50">
            {testing === s.id ? '测试中…' : '连通测试'}
          </button>
          <button type="button" onClick={() => openEdit(s)}
            className="text-[11px] text-brand-light bg-transparent border-none cursor-pointer hover:underline">编辑</button>
          <button type="button" onClick={() => remove(s)}
            className="text-[11px] text-[#f87171] bg-transparent border-none cursor-pointer hover:underline">删除</button>
        </div>
      ) },
  ]

  return (
    <div className="max-w-5xl">
      <div className="flex items-center mb-4">
        <div>
          <h1 className="text-xl font-semibold m-0">MCP 服务</h1>
          <div className="text-[12px] text-[var(--text-3)] mt-0.5">Model Context Protocol 服务端接入(保存前可做连通性测试)</div>
        </div>
        <Button type="primary" className="ml-auto" style={{ background: '#7056F8', borderColor: '#7056F8' }}
          onClick={() => openEdit()}>
          + 新增服务
        </Button>
      </div>
      <div className="rounded-xl border border-[var(--border)] overflow-hidden">
        <Table rowKey="id" columns={columns} dataSource={servers} pagination={false} loading={loading} size="middle" />
      </div>

      <Modal
        title={isNew ? '新增 MCP 服务' : `编辑 · ${editing?.name ?? ''}`}
        open={!!editing}
        onOk={save}
        onCancel={() => setEditing(null)}
        okText="保存"
        cancelText="取消"
        width={560}
      >
        <Form form={form} layout="vertical" className="pt-2">
          <div className="grid grid-cols-2 gap-x-3">
            <Form.Item name="name" label="显示名称" rules={[{ required: true, message: '必填' }]}>
              <Input placeholder="例如:filesystem" />
            </Form.Item>
            <Form.Item name="id" label="服务标识" rules={[{ required: isNew, message: '新增时必填' }]}>
              <Input placeholder="唯一 id" disabled={!isNew} />
            </Form.Item>
          </div>
          <Form.Item name="command" label="启动命令(stdio 模式)">
            <Input placeholder="例如: npx" />
          </Form.Item>
          <Form.Item name="args" label="命令参数(空格分隔)">
            <Input placeholder="例如: -y @modelcontextprotocol/server-filesystem ." />
          </Form.Item>
          <Form.Item name="url" label="远端地址(SSE/HTTP 模式,可留空)">
            <Input placeholder="https://…" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}