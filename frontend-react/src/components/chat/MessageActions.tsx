/**
 * MessageActions.tsx —— AI 正文气泡底部操作条(antdx Actions)
 * 对齐官方独立式样板间的 footer:重新生成 / 复制 / 点赞点踩。
 * 说明:后端暂无反馈上报端点,反馈仅本地记录(切换会话后失效),已在 tooltip 中标注。
 */
import { Actions } from '@ant-design/x'
import Icon from '@/components/bits/Icon'
import { Tooltip } from 'antd'
import { useChatStore } from '@/stores/chat'
import type { Msg } from '@/sdk/protocol'

export default function MessageActions({ msg, content }: { msg: Msg; content: string }) {
  const store = useChatStore()
  const feedback = store.feedbacks[msg.id] || 'default'

  return (
    <Actions
      items={[
        {
          key: 'retry',
          label: '重新生成',
          icon: <Icon name="refresh" size={16} />,
          onItemClick: () => store.retryLastMessage(),
        },
        {
          key: 'copy',
          actionRender: <Actions.Copy text={content} />,
        },
        {
          key: 'feedback',
          actionRender: (
            <Tooltip title="反馈仅记录在本地会话,暂未上报服务端">
              <span>
                <Actions.Feedback
                  value={feedback}
                  styles={{ liked: { color: '#f759ab' } }}
                  onChange={v => store.setFeedback(msg.id, v)}
                />
              </span>
            </Tooltip>
          ),
        },
      ]}
    />
  )
}