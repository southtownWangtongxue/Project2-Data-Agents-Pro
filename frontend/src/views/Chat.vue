<script setup lang="ts">
/**
 * Chat.vue (Phase E.6) — 三区式布局聊天页面
 *
 * 布局：持久侧边栏 | 消息面板 | 底部输入区
 * 支持：SSE 流式对话、多轮追问、历史恢复、节点导航
 */
import { ref, watch, nextTick, onMounted, computed } from 'vue'
import { useChatStore, type ChatMessage } from '@/stores/chat'
import { marked } from 'marked'
import { format as formatSQLText } from 'sql-formatter'
import ChatSidebar from '@/components/ChatSidebar.vue'
import ChatInput from '@/components/ChatInput.vue'
import ClarifierCard from '@/components/ClarifierCard.vue'
import ExecutionCard from '@/components/ExecutionCard.vue'
import NodeSeparator from '@/components/NodeSeparator.vue'

const store = useChatStore()

/* 消息列表容器 DOM 引用 */
const messagesContainer = ref<HTMLElement | null>(null)

/* 侧边栏是否折叠（窄屏可折叠） */
const sidebarCollapsed = ref(false)

/* 多轮对话下拉菜单状态 */
const showTurnMenu = ref(false)
let hideTurnMenuTimer: ReturnType<typeof setTimeout> | null = null

function onTurnTriggerEnter() {
  if (hideTurnMenuTimer) { clearTimeout(hideTurnMenuTimer); hideTurnMenuTimer = null }
  showTurnMenu.value = true
}

function onTurnTriggerLeave() {
  hideTurnMenuTimer = setTimeout(() => {
    showTurnMenu.value = false
  }, 200)
}

function onTurnMenuEnter() {
  if (hideTurnMenuTimer) { clearTimeout(hideTurnMenuTimer); hideTurnMenuTimer = null }
}

function onTurnMenuLeave() {
  showTurnMenu.value = false
}

/* 自动滚动 */
function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

watch(() => store.messages.length, () => scrollToBottom())

onMounted(() => {
  store.loadSessions()
  store.loadSuggestions()
})

/* 侧边栏选择会话 → 加载历史 */
function handleSessionSelect(threadId: string) {
  if (threadId) {
    store.loadSession(threadId)
  }
}

/* 发送消息 */
function handleSend(text: string) {
  store.sendMessage(text)
}

/* 中止生成 */
function handleCancel() {
  store.stopGeneration()
}

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
    return sql // 格式化失败时返回原始 SQL
  }
}

/* 折叠切换 */
function toggleCollapse(msg: ChatMessage) {
  msg.collapsed = !msg.collapsed
}

/* 消息 CSS 类 */
function messageClass(msg: ChatMessage): Record<string, boolean> {
  return {
    'message-user': msg.role === 'user',
    'message-status': msg.type === 'status',
    'message-error': msg.type === 'error',
    'message-assistant': msg.role === 'assistant' && msg.type !== 'error',
    'message-system-card': msg.type === 'thinking' || msg.type === 'tool_call' || msg.type === 'tool_result' || msg.type === 'clarification' || msg.type === 'plan',
  }
}

/* tool 信息 */
function toolInfo(msg: ChatMessage): { label: string; icon: string } {
  switch (msg.type) {
    case 'thinking': return { label: `${msg.agent || ''} — ${msg.phase || '思考中'}`, icon: '💭' }
    case 'tool_call': return { label: `调用: ${msg.toolName || ''}`, icon: '🔧' }
    case 'tool_result': return { label: `完成: ${msg.toolName || ''}`, icon: '✅' }
    default: return { label: '', icon: '📋' }
  }
}

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

/* 获取工具卡片可展开的内容描述 */
function toolExpandContent(msg: ChatMessage): string {
  const meta = msg.toolMeta || {}
  if (msg.type === 'tool_call') {
    if (meta.sql) return `SQL 预览:\n${String(meta.sql)}`
    if (meta.info) return String(meta.info)
  }
  if (msg.type === 'tool_result') {
    if (meta.result) return String(meta.result)
    // 从关联的消息中提取摘要
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
  return ''
}

/* Clarifier 追问 */
function selectClarifyOption(option: string) {
  store.sendMessage(option)
}

/* ECharts 配置 */
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
  if (!result.backgroundColor) result.backgroundColor = 'transparent'
  return result
}

/* 任务清单进度 */
const tasksCompletedCount = computed(() => store.tasks.filter(t => t.status === 'completed').length)

/* 追问建议 */
const followUpSuggestions = computed(() => {
  const lastAssistant = [...store.messages].reverse().find(m => m.role === 'assistant' && m.type === 'text')
  if (!lastAssistant || store.isLoading) return []
  const hasResult = store.messages.some(m => m.type === 'result')
  const hasChart = store.messages.some(m => m.type === 'chart')
  const suggestions: string[] = []
  if (hasResult) suggestions.push('导出数据', '深入分析')
  if (hasChart) suggestions.push('换一种图表')
  suggestions.push('换个角度分析')
  return suggestions.slice(0, 3)
})

/* 检查当前消息是否是新轮次的起始（用于插入分隔线） */
function hasSeparatorBefore(index: number): { has: boolean; turnIndex: number; title: string } | null {
  let userMsgCount = 0
  for (let i = 0; i <= index; i++) {
    const m = store.messages[i]
    if (m.role === 'user' && m.type === 'text') {
      userMsgCount++
      if (i === index && m.role === 'user' && m.type === 'text' && userMsgCount > 1) {
        const idx = userMsgCount - 1
        const turn = store.turns.find(t => t.index === idx)
        return { has: true, turnIndex: idx, title: turn?.title || `第${idx + 1}轮` }
      }
    }
  }
  return null
}

/* 跳转到指定节点 */
function scrollToNode(nodeIndex: number) {
  // 先尝试找分隔线元素
  const el = document.getElementById(`node-${nodeIndex}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  // 回退：没有分隔线时（如第1轮），滚动到第一条用户消息
  if (nodeIndex === 0 && messagesContainer.value) {
    const firstUserMsg = messagesContainer.value.querySelector('.message-bubble--user')
    if (firstUserMsg) {
      firstUserMsg.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
  }
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = 0
  }
}
</script>

<template>
  <div class="chat-layout">
    <!-- ── 左侧持久侧边栏 ── -->
    <ChatSidebar
      v-if="!sidebarCollapsed"
      @select="handleSessionSelect"
    />

    <!-- ── 右侧主区域 ── -->
    <div class="chat-main">
      <!-- 顶部工具栏 -->
      <header class="chat-toolbar">
        <button
          class="toolbar-btn"
          :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="3" y1="12" x2="21" y2="12" v-if="sidebarCollapsed"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <button class="toolbar-btn" title="新建会话" @click="store.newSession()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
        </button>
        <!-- 多轮对话节点快捷跳转（DeepSeek 风格） -->
        <div
          v-if="store.turns.length > 1"
          class="turn-nav"
          @mouseenter="onTurnTriggerEnter"
          @mouseleave="onTurnTriggerLeave"
        >
          <button class="turn-nav-trigger" :class="{ 'is-open': showTurnMenu }">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="12 2 12 22"/>
              <polyline points="6 6 12 2 18 6"/>
              <polyline points="6 18 12 22 18 18"/>
            </svg>
            <span>第 {{ store.currentTurnIndex + 1 }}/{{ store.turns.length }} 轮</span>
            <svg class="turn-nav-chevron" :class="{ 'is-open': showTurnMenu }"
              width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          <!-- 下拉菜单 -->
          <Transition name="turn-menu-fade">
            <div
              v-if="showTurnMenu"
              class="turn-menu"
              @mouseenter="onTurnMenuEnter"
              @mouseleave="onTurnMenuLeave"
            >
              <div class="turn-menu-header">对话轮次</div>
              <div
                v-for="t in store.turns"
                :key="t.index"
                class="turn-menu-item"
                :class="{ 'is-active': store.currentTurnIndex === t.index }"
                @click="scrollToNode(t.index); showTurnMenu = false"
              >
                <span class="turn-menu-index">{{ t.index + 1 }}</span>
                <div class="turn-menu-body">
                  <span class="turn-menu-title">{{ t.title }}</span>
                  <span class="turn-menu-question">{{ t.question }}</span>
                </div>
              </div>
            </div>
          </Transition>
        </div>
        <span class="toolbar-title" v-if="store.currentThreadId && store.turns.length <= 1">
          {{ store.sessions.find(s => s.thread_id === store.currentThreadId)?.title || '对话中' }}
        </span>
      </header>

      <!-- ── 任务清单（替代旧水平管道）── -->
      <div v-if="store.tasks.length > 0" class="task-list" :class="{ 'is-collapsed': store.tasksCollapsed }">
        <div class="task-list-header" @click="store.tasksCollapsed = !store.tasksCollapsed">
          <span class="task-list-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
            </svg>
            任务清单
          </span>
          <span class="task-list-count">
            {{ store.tasksCollapsed ? `${tasksCompletedCount}/${store.tasks.length}` : '' }}
            <svg class="task-list-chevron" :class="{ 'is-open': !store.tasksCollapsed }"
              width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </span>
        </div>
        <Transition name="task-list-expand">
          <div v-if="!store.tasksCollapsed" class="task-list-body">
            <div
              v-for="task in store.tasks"
              :key="task.key"
              class="task-item"
              :class="{ 'is-running': task.status === 'running', 'is-done': task.status === 'completed' }"
            >
              <div class="task-item-icon">
                <!-- Running: spinner -->
                <svg v-if="task.status === 'running'" class="task-spinner" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>
                <!-- Completed: checkmark -->
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </div>
              <span class="task-item-label">{{ task.label }}</span>
            </div>
          </div>
        </Transition>
      </div>

      <!-- 消息列表 -->
      <div ref="messagesContainer" class="chat-messages" :class="{ 'is-empty': store.messages.length === 0 }">
        <!-- 空状态 -->
        <div v-if="store.messages.length === 0" class="chat-empty">
          <div class="empty-illustration">
            <svg width="80" height="80" viewBox="0 0 80 80" fill="none">
              <rect x="4" y="4" width="72" height="72" rx="16" fill="url(#emptyGradient)" opacity="0.1"/>
              <rect x="4" y="4" width="72" height="72" rx="16" stroke="url(#emptyGradient)" stroke-width="2"/>
              <path d="M24 32h32M24 40h24M24 48h28" stroke="#6366f1" stroke-width="2" stroke-linecap="round"/>
              <circle cx="56" cy="52" r="12" fill="#18181b" stroke="#6366f1" stroke-width="2"/>
              <path d="M56 48v8M52 52h8" stroke="#6366f1" stroke-width="2" stroke-linecap="round"/>
              <defs>
                <linearGradient id="emptyGradient" x1="4" y1="4" x2="76" y2="76">
                  <stop stop-color="#6366f1"/><stop offset="1" stop-color="#818cf8"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h3 class="empty-title">开始您的数据分析之旅</h3>
          <p class="empty-text">用自然语言描述您的数据需求，AI 将为您查询、分析并可视化</p>
          <div class="empty-suggestions">
            <template v-if="store.suggestions.length > 0">
              <button
                v-for="(q, idx) in store.suggestions"
                :key="idx"
                class="suggestion-chip"
                :style="{ animationDelay: `${idx * 80}ms` }"
                @click="handleSend(q)"
              >
                {{ q }}
              </button>
            </template>
            <!-- 加载中骨架屏 -->
            <template v-else-if="store.suggestionsLoading">
              <span class="suggestion-chip suggestion-chip--skeleton" v-for="n in 3" :key="n">
                &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
              </span>
            </template>
            <!-- 兜底：API 失败时显示默认问题 -->
            <template v-else>
              <button class="suggestion-chip" @click="handleSend('帮我分析数据库整体概况')">
                帮我分析数据库整体概况
              </button>
              <button class="suggestion-chip" @click="handleSend('统计各表的数据量')">
                统计各表的数据量
              </button>
              <button class="suggestion-chip" @click="handleSend('查看数据库表结构')">
                查看数据库表结构
              </button>
            </template>
            <!-- 刷新按钮 -->
            <button
              v-if="store.suggestions.length > 0"
              class="suggestion-refresh-btn"
              title="重新生成问题建议"
              @click="store.loadSuggestions(true)"
              :disabled="store.suggestionsLoading"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                :class="{ 'spinning': store.suggestionsLoading }">
                <polyline points="23 4 23 10 17 10"/>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- 消息列表（含节点分隔线） -->
        <template v-for="(msg, msgIndex) in store.messages" :key="msg.id">
          <!-- 多轮对话节点分隔线 -->
          <NodeSeparator
            v-if="hasSeparatorBefore(msgIndex)"
            :index="hasSeparatorBefore(msgIndex)!.turnIndex"
            :title="hasSeparatorBefore(msgIndex)!.title"
          />
          <div
            class="message-item"
            :class="messageClass(msg)"
          >
          <!-- 用户消息 -->
          <template v-if="msg.role === 'user' && msg.type === 'text'">
            <div class="message-bubble message-bubble--user">{{ msg.content }}</div>
          </template>

          <!-- 状态消息 -->
          <template v-else-if="msg.type === 'status'">
            <div class="message-status-text">
              <span class="status-dot"></span>{{ msg.content }}
            </div>
          </template>

          <!-- SQL -->
          <template v-else-if="msg.type === 'sql'">
            <div class="message-sql">
              <div class="sql-header">
                <div class="sql-label">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                  </svg>
                  SQL 查询
                </div>
                <button class="sql-copy-btn" @click="copySQL(msg.sql || '')">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                  复制
                </button>
              </div>
              <pre class="sql-code"><code>{{ formatSQL(msg.sql || '') }}</code></pre>
            </div>
          </template>

          <!-- 查询结果 -->
          <template v-else-if="msg.type === 'result'">
            <div class="message-result">
              <div class="result-header">
                <div class="result-label">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/>
                    <line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>
                  </svg>
                  查询结果
                </div>
                <div class="result-actions">
                  <span class="result-count" v-if="msg.data">{{ msg.data.length }} 条记录</span>
                  <button v-if="msg.data?.length && msg.columns?.length" class="export-btn"
                    @click="store.exportData(msg.data!, msg.columns!, 'csv')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    CSV
                  </button>
                  <button v-if="msg.data?.length && msg.columns?.length" class="export-btn export-btn--excel"
                    @click="store.exportData(msg.data!, msg.columns!, 'excel')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Excel
                  </button>
                </div>
              </div>
              <div class="result-table-wrapper">
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
            <div class="message-chart">
              <div class="chart-header">
                <div class="chart-label">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                  </svg>
                  {{ (msg.chartConfig as Record<string, unknown>)?.chart_title || '数据可视化' }}
                </div>
                <span class="chart-type-tag" v-if="(msg.chartConfig as Record<string, unknown>)?.chart_type">
                  {{ (msg.chartConfig as Record<string, unknown>)?.chart_type }}
                </span>
              </div>
              <div class="chart-container">
                <VChart v-if="getEChartsOption(msg)" :option="getEChartsOption(msg)!" autoresize
                  style="height: 360px; width: 100%"
                />
                <div v-else class="chart-empty">
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
            <div class="message-error-row">
              <div class="message-error-text">
                <span class="error-icon">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                </span>
                {{ msg.content }}
                <span v-if="msg.errorCode" class="error-code">[{{ msg.errorCode }}]</span>
              </div>
              <button v-if="msg.recoverable !== false" class="retry-btn" :disabled="store.isLoading"
                @click="store.retryLastMessage()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/>
                  <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
                </svg>
                重试
              </button>
            </div>
          </template>

          <!-- 思考卡片（优化的 DeepSeek 风格） -->
          <template v-else-if="msg.type === 'thinking'">
            <div class="thinking-card" @click="toggleCollapse(msg)">
              <div class="thinking-header">
                <span class="thinking-icon">
                  <svg v-if="msg.collapsed" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                  </svg>
                  <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </span>
                <span class="thinking-label">{{ msg.agent }}</span>
                <span class="thinking-phase">{{ msg.phase }}</span>
                <svg class="thinking-chevron" :class="{ 'is-open': !msg.collapsed }"
                  width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </div>
              <div v-if="!msg.collapsed && msg.content" class="thinking-body">{{ msg.content }}</div>
            </div>
          </template>

          <!-- 工具卡片（可展开查看详情） -->
          <template v-else-if="msg.type === 'tool_call' || msg.type === 'tool_result'">
            <div class="tool-card" :class="msg.type" @click="toggleCollapse(msg)">
              <div class="tool-header">
                <span class="tool-icon">{{ toolInfo(msg).icon }}</span>
                <span class="tool-label">{{ toolInfo(msg).label }}</span>
                <span v-if="formatToolMeta(msg.toolMeta)" class="tool-meta">{{ formatToolMeta(msg.toolMeta) }}</span>
                <svg class="tool-chevron" :class="{ 'is-open': !msg.collapsed }"
                  width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </div>
              <div v-if="!msg.collapsed && toolExpandContent(msg)" class="tool-body">
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

          <!-- 助手文本（Markdown 渲染） -->
          <template v-else-if="msg.role === 'assistant'">
            <div class="message-bubble message-bubble--assistant markdown-body" v-html="renderMarkdown(msg.content || '')"></div>
          </template>

          <!-- 追问建议 -->
          <template v-if="msg.role === 'assistant' && msg.type === 'text' && !store.isLoading && followUpSuggestions.length">
            <div class="followup-bar">
              <span class="followup-label">追问：</span>
              <button v-for="sug in followUpSuggestions" :key="sug" class="followup-chip"
                @click="handleSend(sug)">{{ sug }}</button>
            </div>
          </template>
        </div>
        </template>
      </div>

      <!-- 底部输入区 -->
      <ChatInput :loading="store.isLoading" @send="handleSend" @cancel="handleCancel" />
    </div>
  </div>
</template>

<style scoped>
/* ========== 整体布局 ========== */
.chat-layout {
  display: flex;
  height: 100%;
  max-height: calc(100vh - 64px);
  overflow: hidden;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background-color: var(--color-bg);
}

/* ========== 顶部工具栏 ========== */
.chat-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.toolbar-btn:hover {
  background: var(--color-surface-elevated);
  border-color: var(--color-border-light);
  color: var(--color-text-secondary);
}

.toolbar-title {
  margin-left: var(--space-4);
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── 多轮对话下拉导航（DeepSeek 风格）── */
.turn-nav {
  position: relative;
  margin-left: var(--space-4);
  flex-shrink: 0;
}

.turn-nav-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
  white-space: nowrap;
}
.turn-nav-trigger:hover,
.turn-nav-trigger.is-open {
  background: var(--color-surface-elevated);
  border-color: var(--color-border-light);
  color: var(--color-text-primary);
}

.turn-nav-chevron {
  transition: transform var(--transition-fast);
  opacity: 0.5;
}
.turn-nav-chevron.is-open {
  transform: rotate(180deg);
}

/* 下拉菜单 */
.turn-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 280px;
  max-width: 360px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  z-index: 100;
  padding: var(--space-2);
}

.turn-menu-header {
  padding: var(--space-2) var(--space-3);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 菜单项 */
.turn-menu-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.turn-menu-item:hover {
  background: var(--color-surface-elevated);
}
.turn-menu-item.is-active {
  background: rgba(99, 102, 241, 0.08);
}

.turn-menu-index {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--color-surface-elevated);
  border: 1px solid var(--color-border);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  flex-shrink: 0;
  margin-top: 1px;
}
.turn-menu-item.is-active .turn-menu-index {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.3);
  color: var(--color-primary-light);
}

.turn-menu-body {
  flex: 1;
  min-width: 0;
}

.turn-menu-title {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 2px;
}

.turn-menu-question {
  display: block;
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 过渡动画 */
.turn-menu-fade-enter-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.turn-menu-fade-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}
.turn-menu-fade-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}
.turn-menu-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ========== 任务清单 ========== */
.task-list {
  margin: var(--space-3) var(--space-4) 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  flex-shrink: 0;
  animation: fadeIn 0.3s ease-out;
  transition: all 0.3s ease;
}
.task-list.is-collapsed {
  border-color: rgba(34, 197, 94, 0.15);
  background: rgba(34, 197, 94, 0.04);
}

.task-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  user-select: none;
  transition: background var(--transition-fast);
}
.task-list-header:hover {
  background: var(--color-surface-elevated);
}
.task-list-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.task-list.is-collapsed .task-list-title {
  color: #22c55e;
}
.task-list-title svg {
  color: var(--color-text-muted);
}
.task-list.is-collapsed .task-list-title svg {
  color: #22c55e;
}

.task-list-count {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: 11px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.task-list-chevron {
  transition: transform var(--transition-fast);
}
.task-list-chevron.is-open {
  transform: rotate(180deg);
}

/* 展开动画 */
.task-list-expand-enter-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.task-list-expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.task-list-expand-enter-from,
.task-list-expand-leave-to {
  max-height: 0;
  opacity: 0;
}
.task-list-expand-enter-to,
.task-list-expand-leave-from {
  max-height: 600px;
  opacity: 1;
}

.task-list-body {
  border-top: 1px solid var(--color-border);
  padding: var(--space-2) 0;
}

/* 单个任务项 */
.task-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px var(--space-3);
  font-size: 13px;
  color: var(--color-text-muted);
  transition: all 0.3s ease;
}
.task-item.is-running {
  color: var(--color-text-primary);
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.06), transparent);
}
.task-item.is-done {
  color: var(--color-text-secondary);
}

.task-item-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 1.5px solid var(--color-border);
  transition: all 0.4s ease;
}
.task-item.is-running .task-item-icon {
  border-color: #6366f1;
  background: rgba(99, 102, 241, 0.1);
  color: #818cf8;
}
.task-item.is-done .task-item-icon {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.08);
  color: #22c55e;
}

/* 旋转动画 */
.task-spinner {
  animation: taskSpin 0.8s linear infinite;
}
@keyframes taskSpin {
  to { transform: rotate(360deg); }
}

.task-item-label {
  line-height: 1;
  transition: color 0.3s ease;
}

/* ========== 消息列表 ========== */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
  scroll-behavior: smooth;
}

.chat-messages::-webkit-scrollbar { width: 6px; }
.chat-messages::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: var(--radius-full);
}
.chat-messages::-webkit-scrollbar-track { background-color: transparent; }

.chat-messages.is-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ========== 空状态 ========== */
.chat-empty {
  text-align: center;
  max-width: 480px;
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.empty-illustration { margin-bottom: var(--space-6); }
.empty-title {
  font-size: 24px; font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}
.empty-text {
  font-size: 15px; color: var(--color-text-secondary);
  line-height: 1.6; margin-bottom: var(--space-8);
}
.empty-suggestions {
  display: flex; flex-wrap: wrap; gap: var(--space-3); justify-content: center;
}
.suggestion-chip {
  padding: var(--space-2) var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  font-size: 13px; color: var(--color-text-secondary);
  cursor: pointer; transition: all var(--transition-fast);
}
.suggestion-chip:hover {
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.3);
  color: var(--color-primary-light);
}

/* 骨架屏加载效果 */
.suggestion-chip--skeleton {
  animation: skeletonPulse 1.5s ease-in-out infinite;
  pointer-events: none;
  min-width: 160px;
}
@keyframes skeletonPulse {
  0%, 100% { background: var(--color-surface); opacity: 0.5; }
  50% { background: var(--color-surface-elevated); opacity: 0.8; }
}

/* 刷新按钮 */
.suggestion-refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}
.suggestion-refresh-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.3);
  color: var(--color-primary-light);
}
.suggestion-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.spinning {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ========== 消息项 ========== */
.message-item {
  margin-bottom: var(--space-5);
  display: flex;
  animation: messageIn 0.3s ease-out;
}
@keyframes messageIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.message-item:last-child { margin-bottom: 0; }
.message-user { justify-content: flex-end; }
.message-assistant { justify-content: flex-start; }
.message-status, .message-error { justify-content: center; }

/* ========== 消息气泡 ========== */
.message-bubble {
  max-width: 72%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-xl);
  font-size: 15px; line-height: 1.6;
  word-break: break-word; white-space: pre-wrap;
}
.message-bubble--user {
  background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
  color: white; border-bottom-right-radius: var(--radius-sm);
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}
.message-bubble--assistant {
  background-color: var(--color-surface);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border);
  border-bottom-left-radius: var(--radius-sm);
}

/* Markdown 渲染样式 */
.markdown-body :deep(p) { margin: 0 0 var(--space-2); }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: var(--space-2) 0; padding-left: var(--space-5); }
.markdown-body :deep(li) { margin-bottom: var(--space-1); }
.markdown-body :deep(code) {
  background: rgba(99, 102, 241, 0.1);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 13px;
}
.markdown-body :deep(pre) {
  background: #0d0d0f;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  overflow-x: auto;
  margin: var(--space-2) 0;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  color: #e2e8f0;
}
.markdown-body :deep(strong) { font-weight: 600; }
.markdown-body :deep(em) { font-style: italic; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) {
  margin: var(--space-4) 0 var(--space-2);
  font-weight: 600;
}
.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { font-size: 16px; }
.markdown-body :deep(h3) { font-size: 14px; }
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: var(--space-2) 0;
  font-size: 13px;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--color-surface-elevated);
  font-weight: 600;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  padding-left: var(--space-3);
  margin: var(--space-2) 0;
  color: var(--color-text-secondary);
}

/* ========== 状态 ========== */
.message-status-text {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-full);
  font-size: 13px; color: var(--color-primary-light);
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

/* ========== SQL 代码块 ========== */
.message-sql {
  max-width: 88%;
  background: #0d0d0f;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden; box-shadow: var(--shadow-md);
}
.sql-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background: rgba(99, 102, 241, 0.05);
  border-bottom: 1px solid var(--color-border);
}
.sql-label {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: 12px; font-weight: 500; color: var(--color-primary-light);
  letter-spacing: 0.5px; text-transform: uppercase;
}
.sql-copy-btn {
  display: flex; align-items: center; gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: transparent; border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); font-size: 12px;
  color: var(--color-text-muted); cursor: pointer;
  transition: all var(--transition-fast);
}
.sql-copy-btn:hover {
  background: var(--color-surface); border-color: var(--color-border-light);
  color: var(--color-text-secondary);
}
.sql-code {
  margin: 0; padding: var(--space-4);
  font-family: var(--font-mono); font-size: 13px;
  line-height: 1.7; color: #e2e8f0;
  white-space: pre-wrap; word-break: break-word;
  overflow-x: auto; tab-size: 2;
}

/* ========== 结果表格 ========== */
.message-result { max-width: 92%; width: 100%; }
.result-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--space-3);
}
.result-label {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: 13px; font-weight: 500; color: var(--color-text-primary);
}
.result-count { font-size: 12px; color: var(--color-text-muted); }
.result-table-wrapper {
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); overflow: hidden;
}

/* ========== 错误 ========== */
.message-error-text {
  display: inline-flex; align-items: center; gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-lg);
  font-size: 14px; color: #f87171; max-width: 82%; line-height: 1.5;
}
.error-icon { display: flex; align-items: center; justify-content: center; flex-shrink: 0; }

/* ========== 思考/工具卡片 ========== */
.message-system-card { justify-content: flex-start; }
.thinking-card, .tool-card {
  max-width: 82%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-primary);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  padding: var(--space-2) var(--space-3);
  cursor: pointer; transition: all var(--transition-fast); user-select: none;
  margin-bottom: var(--space-2);
}
.thinking-card:hover, .tool-card:hover {
  border-color: var(--color-border-light);
  border-left-color: var(--color-primary-light);
  background: var(--color-surface-elevated);
}
.tool-card.tool_result {
  border-left-color: #22c55e;
  background: rgba(34, 197, 94, 0.03);
}
.tool-card.tool_result:hover { border-left-color: #22c55e; }
.thinking-header, .tool-header {
  display: flex; align-items: center; gap: var(--space-2); font-size: 12px;
}
.thinking-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px; height: 24px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.1);
  color: var(--color-primary-light);
  flex-shrink: 0;
}
.tool-icon { font-size: 13px; flex-shrink: 0; }
.thinking-label {
  color: var(--color-text-primary);
  font-weight: 600;
  font-size: 13px;
}
.thinking-phase {
  color: var(--color-text-muted);
  font-size: 11px;
  padding: 1px 8px;
  background: var(--color-surface-elevated);
  border-radius: var(--radius-full);
}
.tool-label { color: var(--color-text-secondary); font-weight: 500; }
.tool-meta {
  color: var(--color-text-muted); font-size: 11px; margin-left: auto;
  max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.thinking-chevron, .tool-chevron {
  flex-shrink: 0; color: var(--color-text-muted);
  transition: transform var(--transition-fast); margin-left: auto;
}
.thinking-chevron.is-open, .tool-chevron.is-open { transform: rotate(180deg); }
.thinking-body {
  margin-top: var(--space-2); padding: var(--space-3);
  background: rgba(99, 102, 241, 0.03);
  border-radius: var(--radius-sm);
  font-size: 13px; color: var(--color-text-secondary);
  line-height: 1.6; white-space: pre-wrap;
}

/* ========== 错误行 + 重试 ========== */
.message-error-row {
  display: flex; flex-direction: column; align-items: center;
  gap: var(--space-3); width: 100%;
}
.error-code { font-family: var(--font-mono); font-size: 11px; color: #fca5a5; opacity: 0.8; }
.retry-btn {
  display: inline-flex; align-items: center; gap: var(--space-1);
  padding: var(--space-2) var(--space-4);
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-full);
  color: var(--color-primary-light); font-size: 13px;
  cursor: pointer; transition: all var(--transition-fast);
}
.retry-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.25); border-color: var(--color-primary);
}
.retry-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ========== 导出按钮 ========== */
.result-actions { display: flex; align-items: center; gap: var(--space-2); }
.export-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; background: transparent;
  border: 1px solid var(--color-border); border-radius: var(--radius-sm);
  font-size: 12px; color: var(--color-text-muted);
  cursor: pointer; transition: all var(--transition-fast);
}
.export-btn:hover {
  background: var(--color-surface-elevated); border-color: var(--color-border-light);
  color: var(--color-text-secondary);
}
.export-btn--excel:hover {
  background: rgba(34, 197, 94, 0.08); border-color: rgba(34, 197, 94, 0.3);
  color: #22c55e;
}

/* ========== 图表 ========== */
.message-chart { max-width: 92%; width: 100%; }
.chart-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--space-3);
}
.chart-label {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: 13px; font-weight: 500; color: var(--color-text-primary);
}
.chart-type-tag {
  padding: 2px 8px; background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2); border-radius: var(--radius-full);
  font-size: 11px; color: var(--color-primary-light); text-transform: capitalize;
}
.chart-container {
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); overflow: hidden; padding: var(--space-3);
}
.chart-empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: var(--space-3); height: 160px;
  color: var(--color-text-muted); font-size: 13px;
}

/* ========== 追问建议 ========== */
.followup-bar {
  display: flex; align-items: center; gap: var(--space-2);
  margin-top: var(--space-1); padding: var(--space-2) 0;
  animation: fadeIn 0.3s ease-out;
}
.followup-label { font-size: 12px; color: var(--color-text-muted); white-space: nowrap; }
.followup-chip {
  padding: 4px 12px; background: rgba(99, 102, 241, 0.06);
  border: 1px solid rgba(99, 102, 241, 0.15); border-radius: var(--radius-full);
  font-size: 12px; color: var(--color-primary-light);
  cursor: pointer; transition: all var(--transition-fast);
}
.followup-chip:hover {
  background: rgba(99, 102, 241, 0.15); border-color: var(--color-primary);
  color: var(--color-primary);
}
</style>
