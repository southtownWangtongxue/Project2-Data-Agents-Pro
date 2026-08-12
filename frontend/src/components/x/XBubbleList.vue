<script setup lang="ts">
/**
 * XBubbleList.vue — 基于 Ant Design X Vue 的消息流（P2 + 官方样板间风格）
 *
 * 官方 API 依据：docs/plans/2026-08-05-ant-design-x-vue-integration.md §2.1
 * - <Bubble.List :items :roles autoScroll> + #message 插槽（作用域 { item }）
 * - 消息流居中：paddingInline = calc((100% - 700px) / 2)（官方样板间）
 */
import { computed, h } from 'vue'
import { BubbleList, type BubbleListProps } from 'ant-design-x-vue'
import { useChatStore, type ChatMessage } from '@/stores/chat'
import MessageRenderer from './MessageRenderer.vue'

const store = useChatStore()

/* roles：按 role 设置默认属性（不带 max-width 限制，气泡占满右侧） */
const roles = {
  ai: {
    placement: 'start' as const,
    avatar: h('span', { class: 'xb-avatar xb-avatar--ai' }, 'AI'),
    typing: { step: 5, interval: 20 },
    styles: {
      content: {
        background: 'rgba(255, 255, 255, 0.03)',
        border: '1px solid rgba(255, 255, 255, 0.06)',
        borderRadius: '12px 12px 12px 4px',
        padding: '12px 16px',
        maxWidth: '100%',
      },
    },
  },
  user: {
    placement: 'end' as const,
    avatar: h('span', { class: 'xb-avatar xb-avatar--user' }, '我'),
    styles: {
      content: {
        background: 'linear-gradient(135deg, #7056f8 0%, #8b6fff 100%)',
        color: '#ffffff',
        borderRadius: '12px 12px 4px 12px',
        padding: '12px 16px',
        maxWidth: '100%',
      },
    },
  },
}

/* store.messages -> Bubble.List items（content 传原始 ChatMessage 对象） */
const bubbleItems = computed<NonNullable<BubbleListProps['items']>>(() =>
  store.messages.map((msg: ChatMessage) => ({
    key: msg.id,
    role: msg.role === 'user' ? 'user' : 'ai',
    content: msg,
    loading: store.isLoading && msg.id === store.lastAssistantMsgId && msg.type === 'text',
  })),
)
</script>

<template>
  <div class="xbubble-root">
    <BubbleList
      class="xbubble-list"
      :items="bubbleItems"
      :roles="roles"
      auto-scroll
    >
      <template #message="{ item }">
        <MessageRenderer :msg="item.content" />
      </template>
    </BubbleList>
  </div>
</template>

<style scoped>
.xbubble-root {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 32px 32px 24px;
  width: 100%;
}
.xbubble-root::-webkit-scrollbar { width: 6px; }
.xbubble-root::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: 3px;
}
.xbubble-root::-webkit-scrollbar-track { background-color: transparent; }

/* 消息间距增大（24px 留白） */
.xbubble-root :deep(.ant-x-bubble-list-item) {
  margin-bottom: 24px;
}

.xb-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  flex-shrink: 0;
}
.xb-avatar--ai {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark));
  box-shadow: 0 0 12px rgba(112, 86, 248, 0.3);
}
.xb-avatar--user {
  background: linear-gradient(135deg, #7056f8, #8b6fff);
}
</style>
