<script setup lang="ts">
/**
 * NodeSeparator.vue (Phase E.6) — 节点分隔线组件
 *
 * 在多轮对话中，每个「用户提问 + AI 完整回答」视为一个节点。
 * 节点分隔线显示在节点之间，包含节点标题和跳转锚点。
 *
 * 使用方式：
 *   在消息列表中，当 nodeIndex 变化时，插入一个 NodeSeparator。
 */
defineProps<{
  /** 节点索引（从0开始） */
  index: number
  /** 节点标题（LLM 生成） */
  title: string
}>()
</script>

<template>
  <div :id="`node-${index}`" class="node-separator">
    <div class="node-separator-line"></div>
    <div class="node-separator-label">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/>
      </svg>
      {{ title }}
    </div>
    <div class="node-separator-line"></div>
  </div>
</template>

<style scoped>
.node-separator {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-6) 0 var(--space-4);
  padding: 0 var(--space-4);
  scroll-margin-top: 80px;
}

.node-separator-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, transparent, var(--color-border), transparent);
}

.node-separator-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-4);
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: var(--radius-full);
  font-size: 12px;
  color: var(--color-primary-light);
  white-space: nowrap;
  font-weight: 500;
}
</style>
