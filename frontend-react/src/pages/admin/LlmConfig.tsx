/**
 * pages/admin/LlmConfig.tsx —— 模型配置中心
 * - 列表直呈现表格(不展示「模型总数/已启用」统计卡,空间让给内容)
 * - 编辑弹窗:基础参数 + 全模态能力复选框组(工具调用/图片输入/思考模式)
 *   + 思考强度(minimal/low/medium/high)+ 采样参数(对齐 OpenAI SDK)
 */
import { useEffect, useState } from 'react'
import { App, Button, Form, Input, InputNumber, Modal, Select, Switch, Table, Tag, Checkbox, Tooltip } from 'antd'
import { api } from '@/api/client'
import { useConfigStore, type LlmProvider } from '@/stores/config'

const EFFORT_OPTIONS = [
  { value: '', label: '默认(不指定)' },
  { value: 'minimal', label: 'minimal · 最低' },
  { value: 'low', label: 'low · 低' },
  { value: 'medium', label: 'medium · 中(推荐)' },
  { value: 'high', label: 'high · 高' },
]

const EMPTY: Partial<LlmProvider> = {
  id: '', name: '', api_base: '', model: '', api_key: '', api_key_env: '',
  key_mode: 'env', temperature: 0.3, max_tokens: 4096, enabled: true, is_default: false,
  thinking_mode: false,
  capabilities: { tools: true, image_input: false, thinking: false },
  params: { top_p: 1, presence_penalty: 0, frequency_penalty: 0, reasoning_effort: '' },
}

export default function LlmConfig() {
  const { message } = App.useApp()
  const config = useConfigStore()
  const [editing, setEditing] = useState<Partial<LlmProvider> | null>(null)
  const [isNew, setIsNew] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => { config.loadProviders() }, [])

  const openEdit = (p?: LlmProvider) => {
    const target = p ?? EMPTY
    setIsNew(!p)
    setEditing(target)
    form.setFieldsValue({
      ...target,
      ...(target.capabilities ?? EMPTY.capabilities),
      // 老配置无 params/capabilities 字段时用默认值兜底,避免输入框显示 0
      ...(EMPTY.params ?? {}),
      ...(target.params ?? {}),
      api_key: target.key_mode === 'env' ? '' : target.api_key,
    })
  }

  const save = async () => {
    const v = await form.validateFields()
    const { top_p, presence_penalty, frequency_penalty, reasoning_effort, seed, ...rest } = v
    const payload: Partial<LlmProvider> = {
      ...editing,
      ...rest,
      api_key: v.key_mode === 'env' ? '' : v.api_key,
      capabilities: { tools: !!v.tools, image_input: !!v.image_input, thinking: !!v.thinking },
      params: { top_p, presence_penalty, frequency_penalty, reasoning_effort, seed: seed ?? null },
    }
    try {
      if (isNew) await api('/config/llm', { method: 'POST', body: payload })
      else await api(`/config/llm/${payload.id}`, { method: 'PUT', body: payload })
      message.success(isNew ? '已新增模型' : '已保存')
      setEditing(null)
      config.loadProviders()
    } catch (e) {
      message.error(`保存失败:${(e as Error).message}`)
    }
  }

  const remove = (p: LlmProvider) => {
    Modal.confirm({
      title: '删除模型',
      content: `确认删除「${p.name}」?`,
      okText: '删除', okButtonProps: { danger: true }, cancelText: '取消',
      onOk: async () => {
        await api(`/config/llm/${p.id}`, { method: 'DELETE' }).catch(() => {})
        config.loadProviders()
      },
    })
  }

  const toggle = async (p: LlmProvider, enabled: boolean) => {
    await api(`/config/llm/${p.id}`, { method: 'PUT', body: { ...p, enabled } }).catch(() => {})
    config.loadProviders()
  }

  const columns = [
    { title: '模型', dataIndex: 'name', key: 'name',
      render: (_: unknown, p: LlmProvider) => (
        <div>
          <div className="text-[13px] text-[var(--text-1)]">
            {p.name}
            {p.is_default && <Tag color="purple" className="ml-2">默认</Tag>}
          </div>
          <div className="text-[10px] text-[var(--text-3)] mono">{p.model}</div>
        </div>
      ) },
    { title: '能力', key: 'caps', width: 220,
      render: (_: unknown, p: LlmProvider) => (
        <div className="flex gap-1 flex-wrap">
          {p.capabilities?.tools && <Tag>工具调用</Tag>}
          {p.capabilities?.image_input && <Tag color="cyan">图片输入</Tag>}
          {(p.thinking_mode || p.capabilities?.thinking) && <Tag color="purple">思考 · {p.params?.reasoning_effort || '默认'}</Tag>}
          {!p.capabilities?.tools && !p.capabilities?.image_input && !p.thinking_mode && (
            <span className="text-[11px] text-[var(--text-3)]">—</span>
          )}
        </div>
      ) },
    { title: '采样', key: 'params', width: 200,
      render: (_: unknown, p: LlmProvider) => (
        <span className="text-[11px] text-[var(--text-2)] mono">
          T={p.temperature} · top_p={p.params?.top_p ?? 1} · max={p.max_tokens}
        </span>
      ) },
    { title: '启用', key: 'enabled', width: 70,
      render: (_: unknown, p: LlmProvider) => <Switch size="small" checked={p.enabled} onChange={v => toggle(p, v)} /> },
    { title: '操作', key: 'ops', width: 130,
      render: (_: unknown, p: LlmProvider) => (
        <div className="flex gap-2">
          <button type="button" onClick={() => openEdit(p)}
            className="text-[11px] text-brand-light bg-transparent border-none cursor-pointer hover:underline">编辑</button>
          <button type="button" onClick={() => remove(p)}
            className="text-[11px] text-[#f87171] bg-transparent border-none cursor-pointer hover:underline">删除</button>
        </div>
      ) },
  ]

  return (
    <div className="max-w-5xl">
      <div className="flex items-center mb-4">
        <div>
          <h1 className="text-xl font-semibold m-0">模型配置</h1>
          <div className="text-[12px] text-[var(--text-3)] mt-0.5">
            多模型接入 · 全模态能力声明 · 思考强度(对齐 OpenAI SDK 参数体系)
          </div>
        </div>
        <Button type="primary" className="ml-auto" style={{ background: '#7056F8', borderColor: '#7056F8' }}
          onClick={() => openEdit()}>
          + 新增模型
        </Button>
      </div>

      <div className="rounded-xl border border-[var(--border)] overflow-hidden">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={config.providers}
          pagination={false}
          size="middle"
          expandable={{
            expandedRowRender: (p: LlmProvider) => (
              <div className="text-[11px] text-[var(--text-2)] mono px-2 py-1 space-y-0.5">
                <div>api_base: {p.api_base}</div>
                <div>密钥: {p.key_mode === 'env' ? `环境变量 ${p.api_key_env || '(未设置)'}` : '直接配置(已隐藏)'}</div>
                {p.params?.reasoning_effort && <div>思考强度: {p.params.reasoning_effort}</div>}
              </div>
            ),
          }}
        />
      </div>

      {/* 编辑弹窗 */}
      <Modal
        title={isNew ? '新增模型' : `编辑模型 · ${editing?.name ?? ''}`}
        open={!!editing}
        onOk={save}
        onCancel={() => setEditing(null)}
        okText="保存"
        cancelText="取消"
        width={620}
      >
        <Form form={form} layout="vertical" className="pt-2">
          <div className="grid grid-cols-2 gap-x-3">
            <Form.Item name="name" label="显示名称" rules={[{ required: true, message: '必填' }]}>
              <Input placeholder="例如:nemotron-3-ultra" />
            </Form.Item>
            <Form.Item name="id" label="模型标识" rules={[{ required: !isNew, message: '新增时必填' }]}>
              <Input placeholder="唯一 id(编辑时不可改)" disabled={!isNew} />
            </Form.Item>
          </div>
          <Form.Item name="model" label="模型名称" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="上游真实模型名,如 nvidia/nemotron-3-ultra-550b-a55b:free" />
          </Form.Item>
          <Form.Item
            name="api_base"
            label={<Tooltip title="OpenAI 兼容根地址,如 https://openrouter.ai/api/v1 —— 不要带 /chat/completions 后缀">API 地址</Tooltip>}
            rules={[{ required: true, message: '必填' }]}
          >
            <Input placeholder="https://openrouter.ai/api/v1" />
          </Form.Item>

          <div className="grid grid-cols-2 gap-x-3">
            <Form.Item name="key_mode" label="密钥配置">
              <Select options={[{ value: 'env', label: '环境变量' }, { value: 'direct', label: '直接输入' }]} />
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(a, b) => a.key_mode !== b.key_mode}>
              {({ getFieldValue }) =>
                getFieldValue('key_mode') === 'env' ? (
                  <Form.Item name="api_key_env" label="环境变量名">
                    <Input placeholder="如 OPENROUTER_API_KEY" />
                  </Form.Item>
                ) : (
                  <Form.Item name="api_key" label="API Key">
                    <Input.Password placeholder="sk-…" />
                  </Form.Item>
                )
              }
            </Form.Item>
          </div>

          <div className="border-t border-[var(--border)] pt-3 mt-1">
            <div className="text-[12px] text-[var(--text-2)] mb-2">全模态能力</div>
            <div className="flex gap-5">
              <Form.Item name="tools" valuePropName="checked" noStyle>
                <Checkbox>工具调用</Checkbox>
              </Form.Item>
              <Form.Item name="image_input" valuePropName="checked" noStyle>
                <Checkbox>图片输入</Checkbox>
              </Form.Item>
              <Form.Item name="thinking" valuePropName="checked" noStyle>
                <Checkbox>推理输出</Checkbox>
              </Form.Item>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-3 mt-3">
            <Form.Item
              name="thinking_mode"
              label={<Tooltip title="开启后,对话界面展示该模型的思考过程(需模型支持 reasoning 输出)">思考模式</Tooltip>}
              valuePropName="checked"
            >
              <Switch checkedChildren="展示" unCheckedChildren="隐藏" />
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(a, b) => a.thinking_mode !== b.thinking_mode}
            >
              {({ getFieldValue }) =>
                getFieldValue('thinking_mode') ? (
                  <Form.Item name="reasoning_effort" label="思考强度">
                    <Select options={EFFORT_OPTIONS} />
                  </Form.Item>
                ) : null
              }
            </Form.Item>
          </div>

          <div className="border-t border-[var(--border)] pt-3 mt-1">
            <div className="text-[12px] text-[var(--text-2)] mb-2">采样参数</div>
            <div className="grid grid-cols-3 gap-x-3">
              <Form.Item name="temperature" label="temperature">
                <InputNumber min={0} max={2} step={0.1} className="!w-full" />
              </Form.Item>
              <Form.Item name="top_p" label="top_p">
                <InputNumber min={0} max={1} step={0.05} className="!w-full" />
              </Form.Item>
              <Form.Item name="max_tokens" label="最大输出">
                <InputNumber min={256} step={256} className="!w-full" />
              </Form.Item>
              <Form.Item name="presence_penalty" label="presence_penalty">
                <InputNumber min={-2} max={2} step={0.1} className="!w-full" />
              </Form.Item>
              <Form.Item name="frequency_penalty" label="frequency_penalty">
                <InputNumber min={-2} max={2} step={0.1} className="!w-full" />
              </Form.Item>
              <Form.Item name="seed" label="seed(可选)">
                <InputNumber className="!w-full" />
              </Form.Item>
            </div>
          </div>

          <div className="flex gap-5 pt-2">
            <Form.Item name="is_default" valuePropName="checked" noStyle>
              <Checkbox>设为默认模型</Checkbox>
            </Form.Item>
            <Form.Item name="enabled" valuePropName="checked" noStyle>
              <Checkbox>启用</Checkbox>
            </Form.Item>
          </div>
        </Form>
      </Modal>
    </div>
  )
}