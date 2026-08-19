<script setup lang="ts">
/**
 * ReasoningBlock.vue — 模型思考内容折叠卡片（Phase 4）
 *
 * 对应 SSE `reasoning` 事件（与正文 token 类型化隔离，见 app/core/stream_protocol.py）。
 * - 折叠时仅显示"深度思考"标签，正文保持干净
 * - 展开时显示完整思考内容
 * - 在 Chat.vue（旧界面）与 MessageRenderer.vue（chat-x 新界面）复用
 */
import { ref } from 'vue'
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{ msg: ChatMessage }>()

/* 折叠状态：初始来自 msg.collapsed（默认折叠，保持正文干净） */
const collapsed = ref(props.msg.collapsed ?? true)

function toggle() {
  collapsed.value = !collapsed.value
}
</script>

<template>
  <div class="reasoning-card" :class="{ 'is-open': !collapsed }" @click="toggle">
    <div class="reasoning-header">
      <span class="reasoning-icon">
        <svg v-if="collapsed" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
      </span>
      <span class="reasoning-label">深度思考</span>
      <span class="reasoning-dots"><i /><i /><i /></span>
      <svg class="reasoning-chevron" :class="{ 'is-open': !collapsed }"
        width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </div>
    <!-- 展开/折叠过渡（Phase 5 动效规范：使用 --motion-ease-out） -->
    <Transition name="reasoning">
      <div v-if="!collapsed && msg.content" class="reasoning-body">{{ msg.content }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.reasoning-card {
  max-width: 82%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-primary);
  border-radius: 8px;
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  transition: all var(--transition-fast);
  user-select: none;
  margin-bottom: var(--space-2);
}
.reasoning-card:hover {
  border-color: var(--color-border-light);
  border-left-color: var(--color-primary-light);
  background: var(--color-surface-elevated);
}
.reasoning-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 12px;
}
.reasoning-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: rgba(99, 102, 241, 0.12);
  color: var(--color-primary-light);
  flex-shrink: 0;
}
.reasoning-label {
  color: var(--color-text-primary);
  font-weight: 600;
  font-size: 13px;
}
.reasoning-dots {
  display: flex;
  align-items: center;
  gap: 3px;
}
.reasoning-dots i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--color-text-muted);
  opacity: 0.6;
}
.reasoning-chevron {
  flex-shrink: 0;
  color: var(--color-text-muted);
  transition: transform var(--motion-duration-normal) var(--motion-ease-in-out);
  margin-left: auto;
}
.reasoning-chevron.is-open { transform: rotate(180deg); }

/* 展开/折叠过渡（动效规范：--motion-duration-normal + --motion-ease-out） */
.reasoning-enter-active,
.reasoning-leave-active {
  transition:
    opacity var(--motion-duration-normal) var(--motion-ease-out),
    transform var(--motion-duration-normal) var(--motion-ease-out);
}
.reasoning-enter-from,
.reasoning-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
.reasoning-body {
  margin-top: var(--space-2);
  padding: var(--space-3);
  background: rgba(99, 102, 241, 0.03);
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
}
</style>
