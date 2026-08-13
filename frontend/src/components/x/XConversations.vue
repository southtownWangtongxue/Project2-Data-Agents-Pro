<script setup lang="ts">
/**
 * XConversations.vue — 基于 Ant Design X Vue 的会话列表（P1）
 *
 * 官方 API 依据：docs/plans/2026-08-05-ant-design-x-vue-integration.md §2.2
 * - <Conversations :items :active-key @active-change :menu groupable />
 * - 无 onSelect / onDelete / onRename；删除与重命名通过 menu 的 onClick 实现。
 */
import { computed, ref, h } from 'vue'
import { Conversations, type ConversationsProps } from 'ant-design-x-vue'
import { useChatStore, type SessionInfo } from '@/stores/chat'
import XConvLabel from './XConvLabel.vue'

const store = useChatStore()

/* 会话分组：今天 / 昨天 / 更早 */
function groupOf(createdAt: string): string {
  const d = new Date(createdAt)
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfTarget = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const dayDiff = Math.round((startOfToday - startOfTarget) / 86400000)
  if (dayDiff === 0) return '今天'
  if (dayDiff === 1) return '昨天'
  return '更早'
}

/* SessionInfo[] -> Conversation[]（label 渲染为 XConvLabel，支持内联重命名） */
const convItems = computed<NonNullable<ConversationsProps['items']>>(() =>
  store.sessions.map((s: SessionInfo) => ({
    key: s.thread_id,
    label: renderLabel(s),
    timestamp: new Date(s.created_at).getTime(),
    group: groupOf(s.created_at),
  })),
)

/* 选中变更 -> 加载历史 */
function onActiveChange(threadId: string) {
  if (threadId) {
    store.loadSession(threadId)
  }
}

/* ── 内联重命名编辑 ── */
const editingKey = ref('')

function startRename(threadId: string) {
  editingKey.value = threadId
}

/* label 渲染：XConvLabel 组件（编辑态内部管理，避免父级重建失焦） */
function renderLabel(s: SessionInfo) {
  return h(XConvLabel, {
    value: s.title || s.question?.slice(0, 30) || '无标题',
    editing: s.thread_id === editingKey.value,
    onRename: (title: string) => {
      if (title) store.editSessionTitle(s.thread_id, title)
      editingKey.value = ''
    },
    onCancel: () => {
      editingKey.value = ''
    },
  })
}

/* menu：重命名 / 删除（menu 为函数形式，按会话生成） */
const menuConfig: NonNullable<ConversationsProps['menu']> = (conv: any) => ({
  items: [
    { key: 'rename', label: '重命名' },
    { key: 'delete', label: '删除', danger: true },
  ],
  onClick: ({ key }: { key: string | number }) => {
    if (key === 'rename') startRename(conv.key)
    if (key === 'delete') store.deleteSession(conv.key)
  },
})

/* 分组排序：今天 → 昨天 → 更早 */
const groupable = {
  sort: (a: string, b: string) => {
    const order: Record<string, number> = { 今天: 0, 昨天: 1, 更早: 2 }
    return (order[a] ?? 3) - (order[b] ?? 3)
  },
}
</script>

<template>
  <div class="x-conversations">
    <div class="x-conv-list">
      <Conversations
        :items="convItems"
        :active-key="store.currentThreadId || undefined"
        :menu="menuConfig"
        :groupable="groupable"
        @active-change="onActiveChange"
      />
      <div v-if="store.sessions.length === 0 && !store.sessionsLoading" class="x-conv-empty">
        暂无会话，点击「新建会话」开始新对话
      </div>
    </div>
  </div>
</template>

<style scoped>
.x-conversations {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.x-conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 4px;
  min-height: 0;
}
.x-conv-list::-webkit-scrollbar { width: 6px; }
.x-conv-list::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: 3px;
}
.x-conv-empty {
  padding: 24px 16px;
  text-align: center;
  font-size: 12px;
  color: var(--color-text-muted);
}
/* 会话项：hover/选中对比度增强 */
.x-conv-list :deep(.ant-x-conversations-item) {
  padding: 0 8px;
  border-radius: 8px;
  transition: all var(--transition-fast);
}
.x-conv-list :deep(.ant-x-conversations-item:hover) {
  background: rgba(255, 255, 255, 0.04);
}
.x-conv-list :deep(.ant-x-conversations-item-active) {
  background: rgba(112, 86, 248, 0.12);
}
.x-conv-list :deep(.ant-x-conversations-item-active .ant-x-conversations-item-label) {
  color: var(--color-primary-light);
}
.x-conv-list :deep(.ant-x-conversations-group-title) {
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
