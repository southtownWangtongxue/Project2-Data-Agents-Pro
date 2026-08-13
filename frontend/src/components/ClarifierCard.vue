<script setup lang="ts">
/**
 * ClarifierCard — 意图追问卡片
 * 当 Clarifier 判断用户意图不够明确时，展示追问文本 + 可点击选项
 */
import type { ChatMessage } from '@/stores/chat'

defineProps<{
  msg: ChatMessage
}>()

const emit = defineEmits<{
  (e: 'select', option: string): void
}>()
</script>

<template>
  <div class="clarifier-card">
    <div class="clarifier-header">
      <span class="clarifier-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </span>
      <span class="clarifier-title">帮您确认一下</span>
    </div>
    <p class="clarifier-text">{{ msg.content }}</p>
    <div v-if="msg.clarifyOptions?.length" class="clarifier-options">
      <button
        v-for="opt in msg.clarifyOptions"
        :key="opt"
        class="clarifier-option-btn"
        @click="emit('select', opt)"
      >
        {{ opt }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.clarifier-card {
  max-width: 100%;
  width: 100%;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(139, 92, 246, 0.05));
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.clarifier-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.clarifier-icon {
  color: var(--color-primary-light);
  display: flex;
}

.clarifier-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-light);
}

.clarifier-text {
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin-bottom: var(--space-4);
}

.clarifier-options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.clarifier-option-btn {
  padding: var(--space-2) var(--space-4);
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: var(--radius-full);
  font-size: 13px;
  color: var(--color-primary-light);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.clarifier-option-btn:hover {
  background: rgba(99, 102, 241, 0.22);
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
}

.clarifier-option-btn:active {
  transform: translateY(0);
}
</style>
