<script setup lang="ts">
/**
 * ExecutionCard — 执行计划卡片
 * 展示 Planner 生成的结构化执行计划，包含步骤链和 chart_suitable 标记
 */
import { computed } from 'vue'
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{
  msg: ChatMessage
}>()

/* 步骤对应的图标 */
const stepIcons: Record<string, string> = {
  load_schema: '📋',
  generate_sql: '⚡',
  security_check: '🛡️',
  execute_query: '▶️',
  analyze_data: '📊',
  generate_chart: '📈',
  rag_retrieval: '🔍',
  answer_text: '💬',
}

/* 步骤对应的中文名 */
const stepNames: Record<string, string> = {
  load_schema: '加载表结构',
  generate_sql: '生成 SQL',
  security_check: '安全检查',
  execute_query: '执行查询',
  analyze_data: '数据分析',
  generate_chart: '生成图表',
  rag_retrieval: '知识库检索',
  answer_text: '文本回答',
}

const steps = computed(() => props.msg.planSteps || [])
</script>

<template>
  <div class="execution-card">
    <div class="exec-header">
      <span class="exec-icon">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
      </span>
      <span class="exec-title">执行计划</span>
      <span class="exec-intent-tag">{{ msg.planIntentLabel }}</span>
      <span v-if="msg.planChartSuitable" class="exec-chart-tag" title="将生成图表">📈</span>
    </div>

    <!-- 步骤链 -->
    <div class="exec-steps">
      <template v-for="(step, idx) in steps" :key="step">
        <div class="exec-step">
          <span class="step-icon">{{ stepIcons[step] || '🔹' }}</span>
          <span class="step-name">{{ stepNames[step] || step }}</span>
        </div>
        <div v-if="idx < steps.length - 1" class="step-arrow">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </div>
      </template>
    </div>

    <!-- 空状态 -->
    <div v-if="!steps.length" class="exec-empty">无执行步骤</div>
  </div>
</template>

<style scoped>
.execution-card {
  max-width: 100%;
  width: 100%;
  background: rgba(24, 24, 27, 0.8);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.exec-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.exec-icon {
  color: var(--color-text-secondary);
  display: flex;
}

.exec-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.exec-intent-tag {
  padding: 2px 8px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-full);
  font-size: 11px;
  color: var(--color-primary-light);
}

.exec-chart-tag {
  font-size: 14px;
}

.exec-steps {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.exec-step {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: var(--space-1) var(--space-3);
  background: rgba(99, 102, 241, 0.06);
  border: 1px solid rgba(99, 102, 241, 0.12);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-text-secondary);
  transition: all var(--transition-fast);
}

.step-icon {
  font-size: 13px;
}

.step-name {
  font-weight: 500;
}

.step-arrow {
  color: var(--color-text-muted);
  display: flex;
  opacity: 0.5;
}

.exec-empty {
  font-size: 13px;
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-3);
}
</style>
