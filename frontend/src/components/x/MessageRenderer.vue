<script setup lang="ts">
/**
 * MessageRenderer.vue — 消息内容渲染器（P2）
 *
 * 依据 docs/plans/2026-08-05-ant-design-x-vue-integration.md §4.2：
 * 将 ChatMessage 按 type 分发渲染为 Markdown / SQL 卡片 / 结果表格 / 图表 / 错误 / 追问 / 计划。
 * 由 Bubble.List 的 #message 插槽传入 item.content（原始 ChatMessage 对象）。
 */
import { computed } from 'vue'
import { marked } from 'marked'
import { format as formatSQLText } from 'sql-formatter'
import { useChatStore, type ChatMessage } from '@/stores/chat'
import ClarifierCard from '@/components/ClarifierCard.vue'
import ExecutionCard from '@/components/ExecutionCard.vue'
import XThoughtChain from './XThoughtChain.vue'

const store = useChatStore()

const props = defineProps<{ msg: ChatMessage }>()

/* Markdown 渲染（安全模式：禁止 raw HTML） */
marked.setOptions({ breaks: true, gfm: true })
function renderMarkdown(text: string): string {
  if (!text) return ''
  return marked.parse(text) as string
}

/* SQL 格式化 */
function formatSQL(sql: string): string {
  if (!sql) return ''
  try {
    return formatSQLText(sql, { language: 'mysql', tabWidth: 2 })
  } catch {
    return sql
  }
}

/* ECharts 配置（注入暗色主题） */
function getEChartsOption(msg: ChatMessage): Record<string, unknown> | null {
  const chartCfg = msg.chartConfig
  if (!chartCfg) return null
  const config = ((chartCfg as Record<string, unknown>).echarts_config as Record<string, unknown>) || chartCfg
  return injectDarkTheme(config)
}

function injectDarkTheme(config: Record<string, unknown>): Record<string, unknown> {
  const result = { ...config }
  if (!result.textStyle) result.textStyle = { color: '#a1a1aa' }
  if (result.legend && typeof result.legend === 'object') {
    const legend = result.legend as Record<string, unknown>
    if (!legend.textStyle) legend.textStyle = { color: '#a1a1aa' }
  }
  if (result.xAxis && typeof result.xAxis === 'object') {
    const xAxis = result.xAxis as Record<string, unknown>
    if (!xAxis.axisLabel) xAxis.axisLabel = { color: '#a1a1aa' }
  }
  if (result.yAxis && typeof result.yAxis === 'object') {
    const yAxis = result.yAxis as Record<string, unknown>
    if (!yAxis.axisLabel) yAxis.axisLabel = { color: '#a1a1aa' }
  }
  if (!result.backgroundColor) result.backgroundColor = 'transparent'
  return result
}

const chartOption = computed(() => getEChartsOption(props.msg))

/* 复制 SQL */
async function copySQL(sql: string) {
  try {
    await navigator.clipboard.writeText(sql)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = sql
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
}

/* 追问选项点击 */
function onClarifySelect(option: string) {
  store.sendMessage(option)
}

/* toolMeta 摘要格式化 */
function formatToolMeta(meta?: Record<string, unknown>): string {
  if (!meta) return ''
  return Object.entries(meta)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => {
      const val = typeof v === 'string' ? v : JSON.stringify(v)
      return `${k}: ${val.length > 80 ? val.slice(0, 80) + '...' : val}`
    })
    .join(' | ')
}
</script>

<template>
  <!-- 用户文本 -->
  <div v-if="msg.role === 'user' && msg.type === 'text'" class="xr-user">
    {{ msg.content }}
  </div>

  <!-- 状态消息 -->
  <div v-else-if="msg.type === 'status'" class="xr-status">
    <span class="xr-status-dot"></span>{{ msg.content }}
  </div>

  <!-- SQL 卡片 -->
  <div v-else-if="msg.type === 'sql'" class="xr-sql">
    <div class="xr-sql-header">
      <span class="xr-sql-label">SQL 查询</span>
      <button class="xr-btn" @click="copySQL(msg.sql || '')">复制</button>
    </div>
    <pre class="xr-sql-code"><code>{{ formatSQL(msg.sql || '') }}</code></pre>
  </div>

  <!-- 查询结果 -->
  <div v-else-if="msg.type === 'result'" class="xr-result">
    <div class="xr-result-header">
      <span class="xr-result-label">查询结果</span>
      <div class="xr-result-actions">
        <span v-if="msg.data" class="xr-result-count">{{ msg.data.length }} 条记录</span>
        <button
          v-if="msg.data?.length && msg.columns?.length"
          class="xr-btn" @click="store.exportData(msg.data!, msg.columns!, 'csv')"
        >CSV</button>
        <button
          v-if="msg.data?.length && msg.columns?.length"
          class="xr-btn xr-btn--excel" @click="store.exportData(msg.data!, msg.columns!, 'excel')"
        >Excel</button>
      </div>
    </div>
    <div class="xr-result-table">
      <el-table
        :data="msg.data || []" border stripe size="small" max-height="360" style="width: 100%"
        :header-cell-style="{ background: '#27272a', color: '#fafafa', borderColor: '#3f3f46' }"
        :cell-style="{ background: '#18181b', color: '#a1a1aa', borderColor: '#3f3f46' }"
      >
        <el-table-column
          v-for="col in msg.columns" :key="col" :prop="col" :label="col"
          min-width="120" show-overflow-tooltip
        />
      </el-table>
    </div>
  </div>

  <!-- 图表 -->
  <div v-else-if="msg.type === 'chart'" class="xr-chart">
    <div class="xr-chart-header">
      <span class="xr-chart-label">
        {{ (msg.chartConfig as Record<string, unknown>)?.chart_title || '数据可视化' }}
      </span>
      <span
        v-if="(msg.chartConfig as Record<string, unknown>)?.chart_type"
        class="xr-chart-tag"
      >{{ (msg.chartConfig as Record<string, unknown>)?.chart_type }}</span>
    </div>
    <div class="xr-chart-container">
      <VChart v-if="chartOption" :option="chartOption" autoresize style="height: 360px; width: 100%" />
      <div v-else class="xr-chart-empty">图表配置为空</div>
    </div>
  </div>

  <!-- 错误 -->
  <div v-else-if="msg.type === 'error'" class="xr-error">
    <div class="xr-error-text">
      <span class="xr-error-icon">!</span>
      {{ msg.content }}
      <span v-if="msg.errorCode" class="xr-error-code">[{{ msg.errorCode }}]</span>
    </div>
    <button v-if="msg.recoverable !== false" class="xr-btn xr-btn--retry" :disabled="store.isLoading" @click="store.retryLastMessage()">
      重试
    </button>
  </div>

  <!-- 思考/工具卡片：ThoughtChain 思维链渲染（P5） -->
  <div
    v-else-if="msg.type === 'thinking' || msg.type === 'tool_call' || msg.type === 'tool_result' || msg.type === 'tool_chain'"
    class="xr-thought"
  >
    <XThoughtChain :msg="msg" />
  </div>

  <!-- Clarifier 追问 -->
  <ClarifierCard v-else-if="msg.type === 'clarification'" :msg="msg" @select="onClarifySelect" />

  <!-- Planner 执行计划 -->
  <ExecutionCard v-else-if="msg.type === 'plan'" :msg="msg" />

  <!-- 助手文本（Markdown） -->
  <div v-else-if="msg.role === 'assistant'" class="xr-markdown markdown-body" v-html="renderMarkdown(msg.content || '')"></div>

  <!-- 兜底 -->
  <div v-else class="xr-fallback">{{ msg.content }}</div>
</template>

<style scoped>
.xr-user {
  color: #ffffff;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.xr-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 999px;
  font-size: 13px;
  color: var(--color-primary-light);
}
.xr-status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  animation: xrPulse 1.4s ease-in-out infinite;
}
@keyframes xrPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}
.xr-sql {
  background: #0a0a0a;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  overflow: hidden;
}
.xr-sql-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  background: rgba(112, 86, 248, 0.05);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.xr-sql-label {
  font-size: 12px; font-weight: 500; color: var(--color-primary-light);
  text-transform: uppercase; letter-spacing: 0.5px;
}
.xr-sql-code {
  margin: 0; padding: 16px;
  font-family: var(--font-mono); font-size: 13px; line-height: 1.7;
  color: rgba(255, 255, 255, 0.88); white-space: pre-wrap; word-break: break-word;
  overflow-x: auto; tab-size: 2;
}
.xr-result { width: 100%; }
.xr-result-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
}
.xr-result-label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.xr-result-actions { display: flex; align-items: center; gap: 8px; }
.xr-result-count { font-size: 12px; color: var(--color-text-muted); }
.xr-result-table {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px; overflow: hidden;
}
.xr-chart { width: 100%; }
.xr-chart-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
}
.xr-chart-label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.xr-chart-tag {
  padding: 2px 8px; background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2); border-radius: 999px;
  font-size: 11px; color: var(--color-primary-light); text-transform: capitalize;
}
.xr-chart-container {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px; overflow: hidden; padding: 12px;
}
.xr-chart-empty {
  display: flex; align-items: center; justify-content: center;
  height: 160px; color: var(--color-text-muted); font-size: 13px;
}
.xr-error { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; }
.xr-error-text {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 12px 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 12px;
  font-size: 14px; color: #f87171; line-height: 1.5;
}
.xr-error-icon {
  display: flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; flex-shrink: 0;
  border-radius: 50%; background: rgba(239, 68, 68, 0.2);
  font-size: 11px; font-weight: 700;
}
.xr-error-code { font-family: var(--font-mono); font-size: 11px; color: #fca5a5; opacity: 0.8; }
.xr-card {
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-primary);
  border-radius: 0 8px 8px 0;
  padding: 8px 12px;
  background: var(--color-surface);
}
.xr-card--tool_result { border-left-color: #22c55e; }
.xr-card--tool_chain { border-left-color: var(--color-primary); background: rgba(99, 102, 241, 0.04); }
.xr-card-header { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.xr-card-icon { flex-shrink: 0; }
.xr-card-title { color: var(--color-text-secondary); font-weight: 500; }
.xr-card-meta {
  margin-left: auto; color: var(--color-text-muted); font-size: 11px;
  max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.xr-card-body {
  margin-top: 8px; padding: 12px;
  background: rgba(99, 102, 241, 0.03);
  border-radius: 6px; font-size: 13px; color: var(--color-text-secondary);
  line-height: 1.6; white-space: pre-wrap;
}
.xr-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; background: transparent;
  border: 1px solid var(--color-border); border-radius: 6px;
  font-size: 12px; color: var(--color-text-muted); cursor: pointer;
  transition: all var(--transition-fast);
}
.xr-btn:hover:not(:disabled) {
  background: var(--color-surface-elevated); color: var(--color-text-secondary);
}
.xr-btn--excel:hover {
  background: rgba(34, 197, 94, 0.08); border-color: rgba(34, 197, 94, 0.3); color: #22c55e;
}
.xr-btn--retry {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.3);
  color: var(--color-primary-light);
}
.xr-btn--retry:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.25); border-color: var(--color-primary);
}
.xr-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.xr-fallback { color: var(--color-text-secondary); }
.xr-thought {
  max-width: 100%;
  width: 100%;
}
</style>

<!-- Markdown 样式（复用现有 markdown-body 全局类，需穿透；2026-08-05 增强可读性） -->
<style>
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-primary);
}
.markdown-body p { margin: 0 0 10px; }
.markdown-body p:last-child { margin-bottom: 0; }
.markdown-body ul, .markdown-body ol { margin: 10px 0; padding-left: 22px; }
.markdown-body li { margin-bottom: 6px; }
.markdown-body code {
  background: rgba(112, 86, 248, 0.12);
  padding: 2px 6px; border-radius: 4px;
  font-family: var(--font-mono); font-size: 13px;
  color: var(--color-primary-light);
}
.markdown-body pre {
  background: #0a0a0a; border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px; padding: 14px; overflow-x: auto; margin: 10px 0;
}
.markdown-body pre code { background: none; padding: 0; color: rgba(255, 255, 255, 0.88); }
.markdown-body strong { font-weight: 600; }
.markdown-body h1, .markdown-body h2, .markdown-body h3 { margin: 18px 0 10px; font-weight: 600; }
.markdown-body h1 { font-size: 18px; }
.markdown-body h2 { font-size: 16px; }
.markdown-body h3 { font-size: 15px; }
.markdown-body table {
  width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px;
}
.markdown-body th, .markdown-body td { padding: 10px 12px; border: 1px solid rgba(255, 255, 255, 0.08); text-align: left; }
.markdown-body th { background: var(--color-surface-elevated); font-weight: 600; }
.markdown-body blockquote {
  border-left: 3px solid var(--color-primary);
  padding-left: 14px; margin: 10px 0; color: var(--color-text-secondary);
}
.markdown-body a { color: var(--color-primary-light); }
</style>
