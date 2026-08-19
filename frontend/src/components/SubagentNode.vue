<script setup lang="ts">
/**
 * SubagentNode.vue — 子代理执行节点（阶段4 B4，对齐 Harness 子代理可视化）
 *
 * 将 DeepAgent 模式的子代理委派（SSE tool_result name=subagent）渲染为
 * 独立执行节点：机器人图标 + 子代理名称 + 运行状态 + 可展开结果。
 */
import { computed, ref } from 'vue'
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{ msg: ChatMessage }>()

const expanded = ref(false)

const isRunning = computed(() => (props.msg.status || '') === 'running')

const statusText = computed(() => (isRunning.value ? '执行中' : '已完成'))
</script>

<template>
  <div class="subagent-node" @click="expanded = !expanded">
    <div class="subagent-head">
      <span class="subagent-icon">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4M8 4h8"/>
          <circle cx="9" cy="13" r="1.2" fill="currentColor" stroke="none"/>
          <circle cx="15" cy="13" r="1.2" fill="currentColor" stroke="none"/>
          <path d="M9 16.5a4 4 0 0 0 6 0"/>
        </svg>
      </span>
      <span class="subagent-title">子代理</span>
      <span class="subagent-status" :class="isRunning ? 'is-running' : 'is-done'">{{ statusText }}</span>
      <svg class="subagent-chevron" :class="{ 'is-open': expanded }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </div>
    <div v-if="expanded && msg.content" class="subagent-body">{{ msg.content }}</div>
  </div>
</template>

<style scoped>
.subagent-node {
  max-width: 82%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid #8b5cf6;
  border-radius: 8px;
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-bottom: var(--space-2);
}
.subagent-node:hover {
  border-color: var(--color-border-light);
  border-left-color: #a78bfa;
  background: var(--color-surface-elevated);
}
.subagent-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 13px;
}
.subagent-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: rgba(139, 92, 246, 0.12);
  color: #a78bfa;
  flex-shrink: 0;
}
.subagent-title {
  font-weight: 600;
  color: var(--color-text-primary);
}
.subagent-status {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: var(--radius-full);
}
.subagent-status.is-running {
  color: #a78bfa;
  background: rgba(139, 92, 246, 0.12);
}
.subagent-status.is-done {
  color: var(--color-text-muted);
  background: var(--color-surface-elevated);
}
.subagent-chevron {
  margin-left: auto;
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
}
.subagent-chevron.is-open { transform: rotate(180deg); }
.subagent-body {
  margin-top: var(--space-2);
  padding: var(--space-3);
  background: rgba(139, 92, 246, 0.04);
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}
</style>
