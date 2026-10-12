/**
 * SenderInput.tsx —— 输入区(antdx Sender + 驾驶舱 chips)
 * 生成中:loading + onCancel → 停止按钮;header 放 模式/联网/模型 chips。
 */
import { useState } from 'react'
import { Sender } from '@ant-design/x'
import { useChatStore } from '@/stores/chat'
import ModelSelector from './ModelSelector'

const MODES = [
  { key: 'data', label: '数据分析' },
  { key: 'report', label: '研究报告' },
  { key: 'doc', label: '文档智读' },
  { key: 'task', label: '通用任务' },
]

export default function SenderInput() {
  const store = useChatStore()
  const [text, setText] = useState('')

  const submit = (value: string) => {
    if (!value.trim()) return
    store.sendMessage(value.trim())
    setText('')
  }

  const header = (
    <div className="flex items-center gap-1.5 flex-wrap px-1 pt-1">
      {MODES.map(m => (
        <button
          key={m.key}
          type="button"
          onClick={() => store.setMode(m.key)}
          className={`px-2.5 py-1 text-[11px] rounded-md border cursor-pointer transition-colors ${
            store.mode === m.key
              ? 'text-brand-light border-brand/40 bg-brand/10'
              : 'text-[var(--text-3)] border-[var(--border)] bg-transparent hover:text-[var(--text-2)]'
          }`}
        >
          {m.label}
        </button>
      ))}
      <button
        type="button"
        onClick={() => store.setWebSearch(!store.webSearch)}
        className={`px-2.5 py-1 text-[11px] rounded-md border cursor-pointer transition-colors ${
          store.webSearch
            ? 'text-[var(--success)] border-[var(--success)]/40 bg-[var(--success)]/10'
            : 'text-[var(--text-3)] border-[var(--border)] bg-transparent hover:text-[var(--text-2)]'
        }`}
      >
        🌐 联网搜索
      </button>
      <div className="ml-auto">
        <ModelSelector />
      </div>
    </div>
  )

  return (
    <div className="max-w-3xl mx-auto">
      <Sender
        value={text}
        onChange={setText}
        onSubmit={submit}
        onCancel={() => store.cancelGeneration()}
        loading={store.isLoading}
        placeholder="输入问题,Enter 发送 / Shift+Enter 换行"
        autoSize={{ minRows: 1, maxRows: 4 }}
        header={header}
        submitType="enter"
        className="!bg-[var(--cockpit-800)] !border-[var(--border)]"
      />
      {store.lastPerf && (
        <div className="mt-1.5 px-1 text-[10px] text-[var(--text-3)] mono">
          首token {(store.lastPerf.firstTokenMs / 1000).toFixed(1)}s · 总用时 {(store.lastPerf.durationMs / 1000).toFixed(1)}s ·{' '}
          {store.lastPerf.tokens} tok{store.lastPerf.tokPerSec !== null ? ` · ${store.lastPerf.tokPerSec} tok/s` : ''}
        </div>
      )}
    </div>
  )
}
