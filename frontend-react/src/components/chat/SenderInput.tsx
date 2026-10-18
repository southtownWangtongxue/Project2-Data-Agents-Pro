/**
 * SenderInput.tsx —— 输入区
 *
 * 对齐官方独立式样板间:上方一排建议 Prompts(空输入时可见),下方 antdx Sender。
 * 2026-10 重做(问题3):
 * - 多模式切换 → ModeSwitcher 下拉面板(图标+名称+说明+路由提示,替代 Segmented)
 * - 联网搜索 / 思考模式 → Sender.Switch 开关;思考模式默认关、localStorage
 *   持久化,语义为「显隐 + 传参后端」(请求体带 thinking,后端尽力禁用推理);
 *   当前模型不具备思考能力时开关禁用并 Tooltip 说明
 */
import { useState } from 'react'
import { Prompts, Sender } from '@ant-design/x'
import { Tooltip } from 'antd'
import Icon from '@/components/bits/Icon'
import { useChatStore } from '@/stores/chat'
import { useConfigStore } from '@/stores/config'
import ModelSelector from './ModelSelector'
import ModeSwitcher from './ModeSwitcher'

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

  const thinkingSwitch = (
    <Sender.Switch
      value={store.thinking}
      onChange={v => store.setThinking(v)}
      disabled={!store.thinkingCapable}
      icon={<Icon name="brain" size={15} />}
    >
      深度思考
    </Sender.Switch>
  )

  const header = (
    <div className="flex items-center gap-3 flex-wrap px-1 pt-2 pb-1">
      <ModeSwitcher />
      <Sender.Switch
        value={store.webSearch}
        onChange={v => store.setWebSearch(v)}
        icon={<Icon name="globe" size={15} />}
      >
        智能搜索
      </Sender.Switch>
      {store.thinkingCapable ? thinkingSwitch : (
        <Tooltip title="当前模型不具备深度思考能力,切换支持思考的模型后可开启">
          <span className="inline-flex cursor-not-allowed opacity-60">{thinkingSwitch}</span>
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
            icon: <Icon name="sparkles" size={15} color="var(--brand-light)" />,
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
