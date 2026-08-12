<script setup lang="ts">
/**
 * XWelcome.vue — 空会话欢迎页 + 建议列表（Ultramodern 紫色风格重构）
 *
 * 官方 API 依据：docs/plans/2026-08-05-ant-design-x-vue-integration.md §2.4
 * - Welcome 无 suggestions、无 click 事件（纯展示：title/description/icon/extra）
 * - 建议列表用 <Prompts :items @item-click>；Prompt 主要内容字段是 label
 * - 提示卡采用官方暗色渐变：linear-gradient(123deg, #1e2a38 0%, #2b1f3b 100%)
 */
import { computed, h } from 'vue'
import { Welcome, Prompts, type PromptsProps } from 'ant-design-x-vue'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()

/* store.suggestions: string[] -> PromptProps[]（带数字序号徽标） */
const promptItems = computed<NonNullable<PromptsProps['items']>>(() =>
  (store.suggestions || []).map((q, i) => ({
    key: q,
    label: q,
    description: '点击直接提问',
    icon: h('span', { class: 'xw-prompt-idx' }, String(i + 1)),
  })),
)

function onItemClick({ data }: { data: NonNullable<PromptsProps['items']>[number] }) {
  const q = (data.label as string) || data.key || ''
  if (q) store.sendMessage(q)
}
</script>

<template>
  <div class="xwelcome-root">
    <Welcome
      class="xw-welcome"
      variant="borderless"
      title="开始您的数据分析之旅"
      description="用自然语言描述您的数据需求，AI 将为您查询、分析并可视化"
    />
    <div class="xw-prompts">
      <!-- 加载中骨架 -->
      <div v-if="store.suggestionsLoading && promptItems.length === 0" class="xw-skeleton">
        <div v-for="n in 3" :key="n" class="xw-skeleton-item" />
      </div>
      <!-- 建议列表 -->
      <Prompts
        v-else-if="promptItems.length"
        class="xw-prompts-list"
        :items="promptItems"
        wrap
        @item-click="onItemClick"
      />
      <!-- 兜底：API 失败时显示默认问题 -->
      <div v-else class="xw-fallback">
        <button class="xw-fallback-btn" @click="store.sendMessage('统计各表的数据量')">统计各表的数据量</button>
        <button class="xw-fallback-btn" @click="store.sendMessage('查看数据库表结构')">查看数据库表结构</button>
        <button class="xw-fallback-btn" @click="store.sendMessage('帮我分析数据库整体概况')">帮我分析数据库整体概况</button>
      </div>
      <!-- 刷新按钮 -->
      <button
        v-if="promptItems.length"
        class="xw-refresh"
        title="重新生成问题建议"
        :disabled="store.suggestionsLoading"
        @click="store.loadSuggestions(true)"
      >⟳</button>
    </div>
  </div>
</template>

<style scoped>
/* 欢迎页根：占满主区，内容左对齐不居中 */
.xwelcome-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 28px;
  padding: 48px 32px;
  overflow-y: auto;
  width: 100%;
}
.xw-welcome {
  text-align: left;
  width: 100%;
}
/* Welcome 标题/描述对比度增强 */
.xw-welcome :deep(.ant-x-welcome-title) {
  font-size: 28px;
  font-weight: 600;
  color: var(--color-text-primary);
  text-align: left;
}
.xw-welcome :deep(.ant-x-welcome-description) {
  font-size: 14px;
  color: var(--color-text-secondary);
  text-align: left;
}
/* Prompts 容器：占满主区宽度 */
.xw-prompts {
  position: relative;
  width: 100%;
}
.xw-prompts-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: flex-start;
}
/* 提示卡：官方暗色渐变（实际类名 ant-prompts-item） */
.xw-prompts-list :deep(.ant-prompts-item) {
  flex: 1 1 240px;
  min-width: 240px;
  max-width: 100%;
  background-image: linear-gradient(123deg, #1e2a38 0%, #2b1f3b 100%) !important;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  transition: all var(--transition-fast);
}
.xw-prompts-list :deep(.ant-prompts-item:hover) {
  border-color: rgba(112, 86, 248, 0.3);
  transform: translateY(-1px);
}
.xw-prompts-list :deep(.ant-prompts-item-label) {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.88) !important;
}
.xw-prompts-list :deep(.ant-prompts-item-description) {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65) !important;
}
/* 建议序号徽标 */
.xw-prompt-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: var(--color-primary);
  box-shadow: 0 0 8px rgba(112, 86, 248, 0.4);
  flex-shrink: 0;
}
.xw-skeleton {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
}
.xw-skeleton-item {
  width: 220px;
  height: 64px;
  border-radius: 12px;
  background: var(--color-surface);
  animation: xwPulse 1.5s ease-in-out infinite;
}
@keyframes xwPulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}
.xw-fallback {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
}
.xw-fallback-btn {
  padding: 10px 18px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.xw-fallback-btn:hover {
  background: rgba(112, 86, 248, 0.1);
  border-color: rgba(112, 86, 248, 0.3);
  color: var(--color-primary-light);
}
.xw-refresh {
  position: absolute;
  top: -14px;
  right: 4px;
  width: 28px;
  height: 28px;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-surface);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.xw-refresh:hover:not(:disabled) {
  background: var(--color-surface-elevated);
  color: var(--color-text-secondary);
}
.xw-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
