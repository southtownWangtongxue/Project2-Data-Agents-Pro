<script setup lang="ts">
/**
 * StepChain.vue — 步骤分组链(重构 R1)
 *
 * 受控折叠语义(已确认):
 * - 运行中:展开
 * - 完成:2 秒后自动折叠(对齐任务清单习惯)
 * - 用户点击头部:手动展开/折叠,优先于自动行为
 *
 * 视觉对齐 antdx ThoughtChain(左轨 + 状态点),但折叠为受控实现——
 * antdx ThoughtChain 的 collapsible 为非受控,无法表达"完成自动折叠+用户优先"。
 */
import { ref, computed, watch } from 'vue'
import type { ChatMessage, Step } from '@/stores/chat'
import MessageRenderer from './MessageRenderer.vue'

const props = defineProps<{
  step: Step
  messages: ChatMessage[]
}>()

/* 组内固定类型序:思考 → 工具 → 正文/SQL/结果/图表(与渲染排序一致) */
const STEP_TYPE_RANK: Record<string, number> = {
  reasoning: 0,
  thinking: 0,
  tool_call: 1,
  tool_chain: 1,
  tool_result: 1,
}

const sortedMessages = computed(() =>
  [...props.messages].sort(
    (a, b) => (STEP_TYPE_RANK[a.type || ''] ?? 2) - (STEP_TYPE_RANK[b.type || ''] ?? 2),
  ),
)

/* 折叠状态:running 展开;completed 先保持 2s 再自动折叠;用户点击优先 */
const autoCollapsed = ref(false)
const userExpanded = ref<boolean | null>(null)
let collapseTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.step.status,
  (status) => {
    if (status === 'completed' && autoCollapsed.value === false) {
      if (collapseTimer) clearTimeout(collapseTimer)
      collapseTimer = setTimeout(() => { autoCollapsed.value = true }, 2000)
    }
  },
  { immediate: true },
)

const expanded = computed(() => {
  if (props.step.status === 'running') return true
  if (userExpanded.value !== null) return userExpanded.value
  return !autoCollapsed.value
})

function toggleExpanded() {
  userExpanded.value = !expanded.value
}
</script>

<template>
  <div class="step-chain" :class="{ 'is-running': step.status === 'running' }">
    <!-- 步骤头(可点击折叠) -->
    <button class="step-head" @click="toggleExpanded">
      <span class="step-dot" :class="step.status"></span>
      <span class="step-index">步骤 {{ step.id }}</span>
      <span class="step-label">{{ step.label }}</span>
      <span class="step-status" :class="step.status">
        {{ step.status === 'running' ? '运行中' : '已完成' }}
      </span>
      <svg class="step-chevron" :class="{ 'is-open': expanded }"
        width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
    <!-- 步骤内容 -->
    <div v-if="expanded" class="step-content">
      <template v-for="msg in sortedMessages" :key="msg.id">
        <MessageRenderer :msg="msg" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.step-chain {
  margin-bottom: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}
.step-chain.is-running {
  border-color: rgba(112, 86, 248, 0.35);
  box-shadow: 0 0 18px rgba(112, 86, 248, 0.08);
}

.step-head {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 12px;
  background: transparent; border: none;
  cursor: pointer; text-align: left;
  font-size: 13px;
}
.step-head:hover { background: rgba(112, 86, 248, 0.05); }

.step-dot {
  width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
}
.step-dot.running {
  background: linear-gradient(135deg, #7056f8, #8b6fff);
  box-shadow: 0 0 10px rgba(112, 86, 248, 0.6);
  animation: step-pulse 1.4s ease-in-out infinite;
}
.step-dot.completed { background: #10b981; }
@keyframes step-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.8); }
}

.step-index { font-weight: 600; color: #8b6fff; }
.step-label { color: var(--color-text-primary); font-weight: 500; }
.step-status {
  margin-left: auto; font-size: 12px; padding: 1px 8px; border-radius: 999px;
}
.step-status.running { color: #f59e0b; background: rgba(245, 158, 11, 0.12); }
.step-status.completed { color: #10b981; background: rgba(16, 185, 129, 0.12); }
.step-chevron { flex-shrink: 0; color: var(--color-text-muted); transition: transform 0.2s ease; opacity: 0.6; }
.step-chevron.is-open { transform: rotate(180deg); }

.step-content {
  padding: var(--space-2) var(--space-3) var(--space-3);
  border-top: 1px solid var(--color-border);
  background: rgba(0, 0, 0, 0.15);
}
</style>
