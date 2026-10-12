<script setup lang="ts">
/**
 * MessageRenderer.vue — 单条消息渲染器(重构 R1)
 *
 * 从 Chat.vue 平移的 14 类消息模板,按 ChatMessage.type 分发:
 *   text(user/assistant) / status / sql / result / chart / error / reasoning /
 *   thinking / tool_call / tool_result / tool_chain / clarification / plan / subagent
 *
 * 数据源:props.msg(来自 chat store,含 stepId/channel 等盖章字段);
 * 自包含全部渲染辅助函数与作用域样式,父组件只负责布局与分组。
 */
import { ref, computed } from 'vue'
import { marked } from 'marked'
import { format as formatSQLText } from 'sql-formatter'
import { useChatStore, type ChatMessage } from '@/stores/chat'
import ReasoningBlock from '@/components/ReasoningBlock.vue'
import ClarifierCard from '@/components/ClarifierCard.vue'
import ExecutionCard from '@/components/ExecutionCard.vue'
import SubagentNode from '@/components/SubagentNode.vue'

const props = defineProps<{ msg: ChatMessage }>()
const store = useChatStore()

/* ── 反馈(阶段3 A5)── */
const feedbackMap = ref<Record<string, string>>({})
function setFeedback(msgId: string, kind: 'good' | 'bad') {
  feedbackMap.value[msgId] = feedbackMap.value[msgId] === kind ? '' : kind
}

/* ── 复制 SQL ── */
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

/* ── Markdown(安全模式:禁止 raw HTML)── */
marked.setOptions({ breaks: true, gfm: true })
function renderMarkdown(text: string): string {
  if (!text) return ''
  return marked.parse(text) as string
}

/* ── SQL 格式化 ── */
function formatSQL(sql: string): string {
  if (!sql) return ''
  try {
    return formatSQLText(sql, { language: 'mysql', tabWidth: 2 })
  } catch {
    return sql
  }
}

/* ── 折叠切换 ── */
function toggleCollapse(msg: ChatMessage) {
  msg.collapsed = !msg.collapsed
}

/* ── tool 信息(单行折叠,对齐 Harness)── */
function toolInfo(msg: ChatMessage): { label: string; icon: string } {
  switch (msg.type) {
    case 'thinking': return { label: `${msg.agent || ''} — ${msg.phase || '思考中'}`, icon: '💭' }
    case 'tool_call':
    case 'tool_result':
    case 'tool_chain': return { label: `${msg.toolName || '工具'}`, icon: '🔧' }
    default: return { label: '', icon: '📋' }
  }
}

function formatToolMeta(meta?: Record<string, unknown>): string {
  if (!meta) return ''
  const pick = (k: string): string => {
    const v = meta[k]
    if (v === undefined || v === null || v === '') return ''
    const s = typeof v === 'string' ? v : JSON.stringify(v)
    return s.length > 60 ? s.slice(0, 60) + '…' : s
  }
  return pick('result') || pick('status') || pick('input') || pick('info') || ''
}

function stringifyValue(v: unknown, maxLen = 500): string {
  if (v === undefined || v === null) return ''
  if (typeof v === 'string') return v.slice(0, maxLen)
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  try {
    const s = JSON.stringify(v, null, 2)
    return (s ?? '').slice(0, maxLen)
  } catch {
    return String(v).slice(0, maxLen)
  }
}

function toolExpandContent(msg: ChatMessage): string {
  const meta = msg.toolMeta || {}
  if (Object.keys(meta).length === 0) {
    if (msg.toolName === 'execute_sql') {
      const lastResult = [...store.messages].reverse().find(m => m.type === 'result')
      if (lastResult?.data) return `返回 ${lastResult.data.length} 条记录`
    }
    if (msg.toolName === 'sql_coder') {
      const lastSQL = [...store.messages].reverse().find(m => m.type === 'sql')
      if (lastSQL?.sql) return `SQL 查询已生成`
    }
    if (msg.toolName === 'analyst') {
      const lastAnalysis = [...store.messages].reverse().find(m => m.role === 'assistant' && m.type === 'text')
      if (lastAnalysis?.content) return `分析结果:\n${String(lastAnalysis.content).slice(0, 500)}`
    }
  }
  const labelMap: Record<string, string> = {
    input: '输入', result: '结果', status: '状态', info: '说明',
    sql: 'SQL', args: '参数', agent: '代理', phase: '阶段',
    chart_type: '图表类型', row_count: '返回行数',
  }
  const parts: string[] = []
  for (const [k, v] of Object.entries(meta)) {
    if (v === undefined || v === null || v === '') continue
    const label = labelMap[k] || k
    parts.push(`${label}:\n${stringifyValue(v)}`)
  }
  return parts.join('\n\n')
}

function selectClarifyOption(option: string) {
  store.sendMessage(option)
}

/* ── ECharts(暗色注入)── */
function getEChartsOption(msg: ChatMessage): Record<string, unknown> | null {
  const chartCfg = msg.chartConfig
  if (!chartCfg) return null
  const config = (chartCfg as Record<string, unknown>).echarts_config as Record<string, unknown> || chartCfg
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
  return result
}

/* ── 追问建议(仅最后一条助手文本且非加载中)── */
const followUpSuggestions = computed(() => {
  const lastAssistant = [...store.messages].reverse().find(m => m.role === 'assistant' && m.type === 'text')
  if (!lastAssistant || store.isLoading) return []
  const isLast = store.messages[store.messages.length - 1]?.id === props.msg.id
  if (!isLast) return []
  const hasResult = store.messages.some(m => m.type === 'result')
  const hasChart = store.messages.some(m => m.type === 'chart')
  const suggestions: string[] = []
  if (hasResult) suggestions.push('导出数据', '深入分析')
  if (hasChart) suggestions.push('换一种图表')
  suggestions.push('换个角度分析')
  return suggestions.slice(0, 3)
})
</script>

<template>
  <!-- 用户消息 -->
  <template v-if="msg.role === 'user' && msg.type === 'text'">
    <div class="mr-bubble mr-bubble--user">{{ msg.content }}</div>
  </template>

  <!-- 状态消息 -->
  <template v-else-if="msg.type === 'status'">
    <div class="mr-status-text">
      <span class="mr-status-dot"></span>{{ msg.content }}
    </div>
  </template>

  <!-- SQL -->
  <template v-else-if="msg.type === 'sql'">
    <div class="mr-sql">
      <div class="mr-sql-header">
        <div class="mr-sql-label">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
          </svg>
          SQL 查询
        </div>
        <button class="mr-sql-copy" @click="copySQL(msg.sql || '')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          复制
        </button>
      </div>
      <pre class="mr-sql-code"><code>{{ formatSQL(msg.sql || '') }}</code></pre>
    </div>
  </template>

  <!-- 查询结果 -->
  <template v-else-if="msg.type === 'result'">
    <div class="mr-result">
      <div class="mr-result-header">
        <div class="mr-result-label">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/>
            <line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>
          </svg>
          查询结果
        </div>
        <div class="mr-result-actions">
          <span class="mr-result-count" v-if="msg.data">{{ msg.data.length }} 条记录</span>
          <button v-if="msg.data?.length && msg.columns?.length" class="mr-export-btn"
            @click="store.exportData(msg.data!, msg.columns!, 'csv')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            CSV
          </button>
          <button v-if="msg.data?.length && msg.columns?.length" class="mr-export-btn mr-export-excel"
            @click="store.exportData(msg.data!, msg.columns!, 'excel')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Excel
          </button>
        </div>
      </div>
      <div class="mr-result-table">
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
  </template>

  <!-- 图表 -->
  <template v-else-if="msg.type === 'chart'">
    <div class="mr-chart">
      <div class="mr-chart-header">
        <div class="mr-chart-label">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          {{ (msg.chartConfig as Record<string, unknown>)?.chart_title || '数据可视化' }}
        </div>
        <span class="mr-chart-tag" v-if="(msg.chartConfig as Record<string, unknown>)?.chart_type">
          {{ (msg.chartConfig as Record<string, unknown>)?.chart_type }}
        </span>
      </div>
      <div class="mr-chart-body">
        <VChart v-if="getEChartsOption(msg)" :option="getEChartsOption(msg)!" autoresize
          style="height: 360px; width: 100%"
        />
        <div v-else class="mr-chart-empty">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          <span>图表配置为空</span>
        </div>
      </div>
    </div>
  </template>

  <!-- 错误 -->
  <template v-else-if="msg.type === 'error'">
    <div class="mr-error-row">
      <div class="mr-error-text">
        <span class="mr-error-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </span>
        {{ msg.content }}
        <span v-if="msg.errorCode" class="mr-error-code">[{{ msg.errorCode }}]</span>
      </div>
      <button v-if="msg.recoverable !== false" class="mr-retry-btn" :disabled="store.isLoading"
        @click="store.retryLastMessage()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/>
          <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
        </svg>
        重试
      </button>
    </div>
  </template>

  <!-- 深度思考卡片(思考模式开启时可见,由父级条件控制) -->
  <template v-else-if="msg.type === 'reasoning'">
    <ReasoningBlock :msg="msg" />
  </template>

  <!-- 思考卡片 -->
  <template v-else-if="msg.type === 'thinking'">
    <div class="mr-card" @click="toggleCollapse(msg)">
      <div class="mr-card-header">
        <span class="mr-card-icon">
          <svg v-if="msg.collapsed" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </span>
        <span class="mr-card-title">{{ msg.agent }}</span>
        <span class="mr-card-phase">{{ msg.phase }}</span>
        <svg class="mr-card-chevron" :class="{ 'is-open': !msg.collapsed }"
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="!msg.collapsed && msg.content" class="mr-card-body">{{ msg.content }}</div>
    </div>
  </template>

  <!-- 子代理执行节点 -->
  <SubagentNode v-else-if="msg.type === 'tool_result' && msg.toolName === 'subagent'" :msg="msg" />

  <!-- 工具卡片 -->
  <template v-else-if="(msg.type === 'tool_call' || msg.type === 'tool_result' || msg.type === 'tool_chain') && msg.toolName !== 'subagent'">
    <div class="mr-card mr-card-tool" :class="msg.type" @click="toggleCollapse(msg)">
      <div class="mr-card-header">
        <span class="mr-tool-icon">{{ toolInfo(msg).icon }}</span>
        <span class="mr-tool-label">{{ toolInfo(msg).label }}</span>
        <span v-if="formatToolMeta(msg.toolMeta)" class="mr-tool-meta">{{ formatToolMeta(msg.toolMeta) }}</span>
        <svg class="mr-card-chevron" :class="{ 'is-open': !msg.collapsed }"
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="!msg.collapsed && toolExpandContent(msg)" class="mr-card-body">
        {{ toolExpandContent(msg) }}
      </div>
    </div>
  </template>

  <!-- Clarifier 追问卡片 -->
  <template v-else-if="msg.type === 'clarification'">
    <ClarifierCard :msg="msg" @select="selectClarifyOption" />
  </template>

  <!-- Planner 执行计划 -->
  <template v-else-if="msg.type === 'plan'">
    <ExecutionCard :msg="msg" />
  </template>

  <!-- 助手文本(Markdown + 流式光标 + 反馈) -->
  <template v-else-if="msg.role === 'assistant'">
    <div
      class="mr-bubble mr-bubble--assistant markdown-body"
      :class="{ 'is-streaming': store.isLoading && msg.id === store.lastAssistantMsgId }"
      v-html="renderMarkdown(msg.content || '')"
    ></div>
    <div class="mr-feedback">
      <button class="mr-fb-btn" :class="{ 'is-active': feedbackMap[msg.id] === 'good' }" title="好的回答" @click="setFeedback(msg.id, 'good')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
      </button>
      <button class="mr-fb-btn" :class="{ 'is-active': feedbackMap[msg.id] === 'bad' }" title="有问题的回答" @click="setFeedback(msg.id, 'bad')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zM17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>
      </button>
    </div>
    <!-- 追问建议 -->
    <div v-if="!store.isLoading && followUpSuggestions.length" class="mr-followup">
      <span class="mr-followup-label">追问：</span>
      <button v-for="sug in followUpSuggestions" :key="sug" class="mr-followup-chip"
        @click="store.sendMessage(sug)">{{ sug }}</button>
    </div>
  </template>
</template>

<style scoped>
/* ========== 气泡 ========== */
.mr-bubble {
  max-width: 72%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-xl);
  font-size: 15px; line-height: 1.6;
  word-break: break-word; white-space: pre-wrap;
}
.mr-bubble--user {
  background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
  color: white; border-bottom-right-radius: var(--radius-sm);
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}
.mr-bubble--assistant {
  background-color: var(--color-surface);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border);
  border-bottom-left-radius: var(--radius-sm);
}

/* ========== 反馈 ========== */
.mr-feedback { display: flex; gap: 4px; margin-top: 6px; padding-left: 2px; }
.mr-fb-btn {
  display: flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  border: 1px solid transparent; background: transparent;
  border-radius: var(--radius-md); color: var(--color-text-muted);
  cursor: pointer; transition: all var(--transition-fast);
}
.mr-fb-btn:hover { background: var(--color-surface-elevated); color: var(--color-text-secondary); }
.mr-fb-btn.is-active[title="好的回答"] { color: #6366f1; background: rgba(99, 102, 241, 0.1); }
.mr-fb-btn.is-active[title="有问题的回答"] { color: #ef4444; background: rgba(239, 68, 68, 0.1); }

/* ========== Markdown ========== */
.markdown-body :deep(p) { margin: 0 0 var(--space-2); }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: var(--space-2) 0; padding-left: var(--space-5); }
.markdown-body :deep(li) { margin-bottom: var(--space-1); }
.markdown-body :deep(code) {
  background: rgba(99, 102, 241, 0.1); padding: 2px 6px;
  border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 13px;
}
.markdown-body :deep(pre) {
  background: #0d0d0f; border: 1px solid var(--color-border);
  border-radius: var(--radius-md); padding: var(--space-3);
  overflow-x: auto; margin: var(--space-2) 0;
}
.markdown-body :deep(pre code) { background: none; padding: 0; color: #e2e8f0; }
.markdown-body :deep(strong) { font-weight: 600; }
.markdown-body :deep(em) { font-style: italic; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) {
  margin: var(--space-4) 0 var(--space-2); font-weight: 600;
}
.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { font-size: 16px; }
.markdown-body :deep(h3) { font-size: 14px; }
.markdown-body :deep(table) {
  width: 100%; border-collapse: collapse; margin: var(--space-2) 0; font-size: 13px;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  padding: var(--space-2); border: 1px solid var(--color-border); text-align: left;
}
.markdown-body :deep(th) { background: var(--color-surface-elevated); font-weight: 600; }
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-primary); padding-left: var(--space-3);
  margin: var(--space-2) 0; color: var(--color-text-secondary);
}

/* ========== 状态 ========== */
.mr-status-text {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-full); font-size: 13px; color: var(--color-primary-light);
}
.mr-status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  animation: mr-pulse 1.4s ease-in-out infinite;
}
@keyframes mr-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

/* ========== SQL ========== */
.mr-sql {
  max-width: 88%; background: #0d0d0f;
  border: 1px solid var(--color-border); border-radius: var(--radius-lg);
  overflow: hidden; box-shadow: var(--shadow-md);
}
.mr-sql-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background: rgba(99, 102, 241, 0.05); border-bottom: 1px solid var(--color-border);
}
.mr-sql-label {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: 12px; font-weight: 500; color: var(--color-primary-light);
  letter-spacing: 0.5px; text-transform: uppercase;
}
.mr-sql-copy {
  display: flex; align-items: center; gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: transparent; border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); font-size: 12px;
  color: var(--color-text-muted); cursor: pointer;
  transition: all var(--transition-fast);
}
.mr-sql-copy:hover { background: var(--color-surface); border-color: var(--color-border-light); color: var(--color-text-secondary); }
.mr-sql-code {
  margin: 0; padding: var(--space-4);
  font-family: var(--font-mono); font-size: 13px;
  line-height: 1.7; color: #e2e8f0;
  white-space: pre-wrap; word-break: break-word;
  overflow-x: auto; tab-size: 2;
}

/* ========== 结果表格 ========== */
.mr-result { max-width: 92%; width: 100%; }
.mr-result-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--space-3);
}
.mr-result-label {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: 13px; font-weight: 500; color: var(--color-text-primary);
}
.mr-result-count { font-size: 12px; color: var(--color-text-muted); }
.mr-result-table {
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); overflow: hidden;
}
.mr-result-actions { display: flex; align-items: center; gap: var(--space-2); }
.mr-export-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; background: transparent;
  border: 1px solid var(--color-border); border-radius: var(--radius-sm);
  font-size: 12px; color: var(--color-text-muted);
  cursor: pointer; transition: all var(--transition-fast);
}
.mr-export-btn:hover { background: var(--color-surface-elevated); border-color: var(--color-border-light); color: var(--color-text-secondary); }
.mr-export-excel:hover { background: rgba(34, 197, 94, 0.08); border-color: rgba(34, 197, 94, 0.3); color: #22c55e; }

/* ========== 错误 ========== */
.mr-error-row {
  display: flex; flex-direction: column; align-items: center;
  gap: var(--space-3); width: 100%;
}
.mr-error-text {
  display: inline-flex; align-items: center; gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-lg);
  font-size: 14px; color: #f87171; max-width: 82%; line-height: 1.5;
}
.mr-error-icon { display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.mr-error-code { font-family: var(--font-mono); font-size: 11px; color: #fca5a5; opacity: 0.8; }
.mr-retry-btn {
  display: inline-flex; align-items: center; gap: var(--space-1);
  padding: var(--space-2) var(--space-4);
  background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-full);
  color: var(--color-primary-light); font-size: 13px;
  cursor: pointer; transition: all var(--transition-fast);
}
.mr-retry-btn:hover:not(:disabled) { background: rgba(99, 102, 241, 0.25); border-color: var(--color-primary); }
.mr-retry-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ========== 思考/工具卡片 ========== */
.mr-card {
  max-width: 82%; width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-primary);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  padding: var(--space-2) var(--space-3);
  cursor: pointer; transition: all var(--transition-fast); user-select: none;
  margin-bottom: var(--space-2);
}
.mr-card:hover { border-color: var(--color-border-light); border-left-color: var(--color-primary-light); background: var(--color-surface-elevated); }
.mr-card-tool { border-left-color: var(--color-primary); }
.mr-card-tool.tool_chain { background: rgba(99, 102, 241, 0.04); }
.mr-card-tool.tool_chain:hover { border-left-color: var(--color-primary-light); }
.mr-card-tool.tool_result { border-left-color: #22c55e; background: rgba(34, 197, 94, 0.03); }
.mr-card-tool.tool_result:hover { border-left-color: #22c55e; }
.mr-card-header { display: flex; align-items: center; gap: var(--space-2); font-size: 12px; }
.mr-card-icon {
  display: flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 50%;
  background: rgba(99, 102, 241, 0.1); color: var(--color-primary-light); flex-shrink: 0;
}
.mr-tool-icon { font-size: 13px; flex-shrink: 0; }
.mr-card-title { color: var(--color-text-primary); font-weight: 600; font-size: 13px; }
.mr-card-phase {
  color: var(--color-text-muted); font-size: 11px;
  padding: 1px 8px; background: var(--color-surface-elevated); border-radius: var(--radius-full);
}
.mr-tool-label { color: var(--color-text-secondary); font-weight: 500; }
.mr-tool-meta {
  color: var(--color-text-muted); font-size: 11px; margin-left: auto;
  max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.mr-card-chevron { flex-shrink: 0; color: var(--color-text-muted); transition: transform var(--transition-fast); margin-left: auto; }
.mr-card-chevron.is-open { transform: rotate(180deg); }
.mr-card-body {
  margin-top: var(--space-2); padding: var(--space-3);
  background: rgba(99, 102, 241, 0.03); border-radius: var(--radius-sm);
  font-size: 13px; color: var(--color-text-secondary);
  line-height: 1.6; white-space: pre-wrap;
}

/* ========== 图表 ========== */
.mr-chart { max-width: 92%; width: 100%; }
.mr-chart-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--space-3);
}
.mr-chart-label {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: 13px; font-weight: 500; color: var(--color-text-primary);
}
.mr-chart-tag {
  padding: 2px 8px; background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2); border-radius: var(--radius-full);
  font-size: 11px; color: var(--color-primary-light); text-transform: capitalize;
}
.mr-chart-body {
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); overflow: hidden; padding: var(--space-3);
}
.mr-chart-empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: var(--space-3); height: 160px;
  color: var(--color-text-muted); font-size: 13px;
}

/* ========== 追问建议 ========== */
.mr-followup {
  display: flex; align-items: center; gap: var(--space-2);
  margin-top: var(--space-1); padding: var(--space-2) 0;
  animation: mr-fade-in 0.3s ease-out;
}
.mr-followup-label { font-size: 12px; color: var(--color-text-muted); white-space: nowrap; }
.mr-followup-chip {
  padding: 4px 12px; background: rgba(99, 102, 241, 0.06);
  border: 1px solid rgba(99, 102, 241, 0.15); border-radius: var(--radius-full);
  font-size: 12px; color: var(--color-primary-light);
  cursor: pointer; transition: all var(--transition-fast);
}
.mr-followup-chip:hover { background: rgba(99, 102, 241, 0.15); border-color: var(--color-primary); color: var(--color-primary); }
@keyframes mr-fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
</style>
