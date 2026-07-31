<script setup lang="ts">
/**
 * ModeBar.vue — 工作模式切换栏 + 联网搜索开关
 *
 * 4 种模式: data（数据分析）/ report（研究报告）/ doc（文档智读）/ task（通用任务）
 * 联网搜索: 全局 toggle，开启后对所有模式生效
 */
defineProps<{
  modelValue: string       // 当前模式
  webSearch: boolean        // 联网搜索开关状态
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:webSearch': [value: boolean]
}>()

const modes = [
  { key: 'data',   icon: '📊', label: '数据分析' },
  { key: 'report', icon: '📝', label: '研究报告' },
  { key: 'doc',    icon: '📖', label: '文档智读' },
  { key: 'task',   icon: '🤖', label: '通用任务' },
]

function selectMode(key: string) {
  if (modes.find(m => m.key === key)?.disabled) return
  emit('update:modelValue', key)
}
</script>

<template>
  <div class="mode-bar">
    <div class="mode-tabs">
      <button
        v-for="m in modes"
        :key="m.key"
        class="mode-tab"
        :class="{ active: modelValue === m.key, disabled: m.disabled }"
        :disabled="m.disabled"
        :title="m.disabled ? '即将上线' : m.label"
        @click="selectMode(m.key)"
      >
        <span class="mode-icon">{{ m.icon }}</span>
        <span class="mode-label">{{ m.label }}</span>
        <span v-if="m.disabled" class="mode-badge">即将上线</span>
      </button>
    </div>

    <button
      class="web-search-toggle"
      :class="{ active: webSearch }"
      @click="emit('update:webSearch', !webSearch)"
      title="开启后 Agent 可联网搜索最新信息"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.3-4.3" />
      </svg>
      <span>联网搜索</span>
    </button>
  </div>
</template>

<style scoped>
.mode-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px var(--space-3);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.mode-tabs {
  display: flex;
  gap: 2px;
  background: var(--color-surface-elevated);
  border-radius: var(--radius-md);
  padding: 2px;
}

.mode-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all .2s ease;
  white-space: nowrap;
}
.mode-tab:hover:not(.disabled) {
  color: var(--color-text-primary);
}
.mode-tab.active {
  background: var(--color-bg);
  color: #818cf8;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0,0,0,.2);
}
.mode-tab.disabled {
  opacity: .4;
  cursor: not-allowed;
}

.mode-icon { font-size: 14px; line-height: 1; }
.mode-label { font-size: 12px; }

.mode-badge {
  font-size: 8px;
  background: rgba(99,102,241,.15);
  color: #818cf8;
  padding: 1px 4px;
  border-radius: var(--radius-full);
  font-weight: 500;
}

.web-search-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  color: var(--color-text-muted);
  background: transparent;
  border: 1px solid var(--color-border);
  cursor: pointer;
  transition: all .2s ease;
}
.web-search-toggle:hover {
  background: var(--color-surface-elevated);
}
.web-search-toggle.active {
  border-color: rgba(99,102,241,.5);
  color: #818cf8;
  background: rgba(99,102,241,.08);
}
</style>
