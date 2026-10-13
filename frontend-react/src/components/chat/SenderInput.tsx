/**
 * SenderInput.tsx —— 输入区
 *
 * 对齐官方独立式样板间:上方一排建议 Prompts(空输入时可见),下方 antdx Sender。
 * 业务扩展保留:Sender.Header 承载 模式切换 / 联网搜索 / 模型选择(项目必需能力)。
 */
import { useState } from 'react'
import { Prompts, Sender } from '@ant-design/x'
import { Segmented, Switch, Tooltip } from 'antd'
import { Globe, Sparkles } from 'lucide-react'
import { useChatStore } from '@/stores/chat'
import { useConfigStore } from '@/stores/config'
import ModelSelector from './ModelSelector'

const MODES = [
  { label: '数据分析', value: 'data' },
  { label: '研究报告', value: 'report' },
  { label: '文档智读', value: 'doc' },
  { label: '通用任务', value: 'task' },
]

export default function SenderInput() {
  const store = useChatStore()
  const config = useConfigStore()
  const [text, setText] = useState('')

  const submit = (value: string) => {
    if (!value.trim()) return
    store.sendMessage(value.trim())
    setText('')
  }

  /* 建议:空输入且空闲时才占位,生成中让位给停止按钮 */
  const suggestions = store.suggestions.slice(0, 4)
  const showPrompts = !store.isLoading && text.length === 0 && suggestions.length > 0

  const header = (
    <div className="flex items-center gap-3 flex-wrap px-1 pt-2 pb-1">
      <Segmented
        size="small"
        value={store.mode}
        options={MODES}
        onChange={v => store.setMode(String(v))}
        style={{ background: 'transparent' }}
      />
      <span className="flex items-center gap-1.5">
        <Switch size="small" checked={store.webSearch} onChange={store.setWebSearch} />
        <span className="flex items-center gap-1 text-[12px] text-[var(--text-2)] cursor-pointer"
          onClick={() => store.setWebSearch(!store.webSearch)}>
          <Globe size={13} />
          联网搜索
        </span>
      </span>
      {store.thinkingModeEnabled && (
        <Tooltip title="当前模型已开启思考模式,回答会展示推理过程">
          <span className="text-[11px] mono px-2 py-0.5 rounded cursor-default"
            style={{ color: 'var(--brand-light)', background: 'rgba(112,86,248,0.12)' }}>
            THINKING
          </span>
        </Tooltip>
      )}
      <div className="ml-auto">
        <ModelSelector />
      </div>
    </div>
  )

  return (
    <div className="w-full px-4 pt-2 pb-1 flex flex-col items-center gap-3">
      {showPrompts && (
        <Prompts
          className="w-full"
          style={{ maxWidth: 840 }}
          items={suggestions.map(s => ({
            key: s,
            description: s,
            icon: <Sparkles size={13} style={{ color: 'var(--brand-light)' }} />,
          }))}
          onItemClick={info => submit(String(info.data.description || ''))}
          styles={{ item: { padding: '6px 12px', flex: 1, minWidth: 0 } }}
        />
      )}

      <Sender
        className="w-full"
        style={{ maxWidth: 840 }}
        value={text}
        onChange={setText}
        onSubmit={submit}
        onCancel={() => store.cancelGeneration()}
        loading={store.isLoading}
        placeholder="输入问题,Enter 发送 / Shift+Enter 换行"
        autoSize={{ minRows: 2, maxRows: 6 }}
        header={header}
        submitType="enter"
      />
      {!config.loaded && <span className="sr-only">模型配置加载中</span>}
    </div>
  )
}