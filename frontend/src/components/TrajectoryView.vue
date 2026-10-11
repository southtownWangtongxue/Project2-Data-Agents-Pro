<script setup lang="ts">
/**
 * TrajectoryView.vue — 会话轨迹时间线（阶段4 B2，对齐 Harness Trajectory）
 *
 * 展示会话的完整事件轨迹（含过程态事件 plan/clarification/tool_chain），
 * 数据来自 GET /chat/sessions/{thread_id}/trajectory。
 *
 * R17 来源检查增强：
 * - 关键词搜索（按内容与事件类型过滤）
 * - 点击事件展开：完整正文 + payload JSON（按来源检查模型可见上下文）
 * - 手动刷新
 */
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import apiClient from '@/api/client'

interface TrajectoryEvent {
  id: number
  event_type: string
  role: string | null
  content: string
  payload: Record<string, unknown> | null
  run_id: string | null
  node_index: number | null
  created_at: string | null
}

const store = useChatStore()
const events = ref<TrajectoryEvent[]>([])
const loading = ref(false)
const keyword = ref('')
const expandedId = ref<number | null>(null)

/* 事件类型 → 展示标签/颜色 */
const typeMeta: Record<string, { label: string; dot: string }> = {
  user_message: { label: '用户', dot: '#3b82f6' },
  plan: { label: '计划', dot: '#8b5cf6' },
  clarification: { label: '澄清', dot: '#f59e0b' },
  sql: { label: 'SQL', dot: '#10b981' },
  result: { label: '结果', dot: '#06b6d4' },
  analysis: { label: '分析', dot: '#6366f1' },
  chart: { label: '图表', dot: '#ec4899' },
  error: { label: '错误', dot: '#ef4444' },
  tool_chain: { label: '工具', dot: '#64748b' },
}

function metaOf(type: string) {
  return typeMeta[type] || { label: type, dot: '#94a3b8' }
}

function timeOf(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`
}

/* R17：关键词过滤（内容 + 类型标签） */
const filteredEvents = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return events.value
  return events.value.filter((evt) => {
    const label = metaOf(evt.event_type).label.toLowerCase()
    return (
      (evt.content || '').toLowerCase().includes(kw) ||
      evt.event_type.toLowerCase().includes(kw) ||
      label.includes(kw)
    )
  })
})

function payloadText(evt: TrajectoryEvent): string {
  if (!evt.payload || !Object.keys(evt.payload).length) return ''
  try {
    return JSON.stringify(evt.payload, null, 2)
  } catch {
    return String(evt.payload)
  }
}

function toggleExpand(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

async function load() {
  if (!store.currentThreadId) return
  loading.value = true
  try {
    /* full=true：后端返回完整正文与 payload（来源检查需要） */
    const data = await apiClient.get(`/chat/sessions/${store.currentThreadId}/trajectory?full=true`) as {
      events: TrajectoryEvent[]
    }
    events.value = data.events || []
  } catch (err) {
    console.error('[trajectory] 加载轨迹失败:', err)
    events.value = []
  } finally {
    loading.value = false
  }
}

defineExpose({ load, events, loading })
</script>

<template>
  <div class="trajectory-view">
    <div class="trajectory-header">
      <span>会话轨迹</span>
      <span v-if="events.length" class="trajectory-count">
        {{ keyword ? `${filteredEvents.length}/${events.length}` : events.length }} 个事件
      </span>
      <button class="trajectory-refresh" title="刷新" @click="load">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>
    </div>
    <input
      v-model="keyword"
      class="trajectory-search"
      type="text"
      placeholder="搜索事件内容或类型..."
    />
    <div v-if="loading" class="trajectory-loading">加载中...</div>
    <div v-else-if="!events.length" class="trajectory-empty">暂无轨迹数据</div>
    <div v-else-if="!filteredEvents.length" class="trajectory-empty">无匹配事件</div>
    <div v-else class="trajectory-list">
      <div
        v-for="evt in filteredEvents"
        :key="evt.id"
        class="trajectory-item"
        :class="{ 'is-expanded': expandedId === evt.id }"
        @click="toggleExpand(evt.id)"
      >
        <div class="trajectory-item-dot" :style="{ background: metaOf(evt.event_type).dot }"></div>
        <div class="trajectory-item-body">
          <div class="trajectory-item-head">
            <span class="trajectory-item-label">{{ metaOf(evt.event_type).label }}</span>
            <span class="trajectory-item-time">{{ timeOf(evt.created_at) }}</span>
            <span v-if="evt.node_index !== null" class="trajectory-item-node">轮 {{ evt.node_index + 1 }}</span>
          </div>
          <div v-if="evt.content" class="trajectory-item-content">{{ evt.content }}</div>
          <!-- R17 来源检查：展开显示完整正文 + payload -->
          <div v-if="expandedId === evt.id" class="trajectory-item-detail" @click.stop>
            <div class="trajectory-detail-row">
              <span class="trajectory-detail-key">event_type</span>
              <code>{{ evt.event_type }}</code>
            </div>
            <div v-if="evt.run_id" class="trajectory-detail-row">
              <span class="trajectory-detail-key">run_id</span>
              <code>{{ evt.run_id }}</code>
            </div>
            <div v-if="evt.content" class="trajectory-detail-block">
              <span class="trajectory-detail-key">完整内容</span>
              <pre>{{ evt.content }}</pre>
            </div>
            <div v-if="payloadText(evt)" class="trajectory-detail-block">
              <span class="trajectory-detail-key">payload</span>
              <pre>{{ payloadText(evt) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trajectory-view {
  padding: var(--space-3);
  min-height: 100px;
}
.trajectory-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.trajectory-count {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-muted);
}
.trajectory-loading,
.trajectory-empty {
  padding: var(--space-6) 0;
  text-align: center;
  font-size: 12px;
  color: var(--color-text-muted);
}
.trajectory-list {
  position: relative;
}
.trajectory-list::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 4px;
  bottom: 4px;
  width: 2px;
  background: var(--color-border);
}
.trajectory-item {
  position: relative;
  display: flex;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
}
.trajectory-item-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 3px;
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.2);
}
.trajectory-item-body {
  flex: 1;
  min-width: 0;
}
.trajectory-item-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.trajectory-item-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.trajectory-item-time {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}
.trajectory-item-node {
  font-size: 10px;
  color: var(--color-text-muted);
  background: var(--color-surface-elevated);
  padding: 1px 6px;
  border-radius: var(--radius-full);
}
.trajectory-item-content {
  margin-top: 3px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* ── R17 来源检查增强 ── */
.trajectory-refresh {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}
.trajectory-refresh:hover {
  color: var(--color-primary-light);
  background: var(--color-surface-elevated);
}
.trajectory-search {
  width: 100%;
  margin-bottom: var(--space-3);
  padding: 5px 10px;
  font-size: 12px;
  color: var(--color-text-primary);
  background: var(--color-surface-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  outline: none;
  transition: border-color 0.15s ease;
}
.trajectory-search::placeholder {
  color: var(--color-text-muted);
}
.trajectory-search:focus {
  border-color: var(--color-primary);
}
.trajectory-item {
  cursor: pointer;
}
.trajectory-item.is-expanded .trajectory-item-content {
  -webkit-line-clamp: unset;
  display: block;
}
.trajectory-item-detail {
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 11px;
  cursor: default;
}
.trajectory-detail-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  padding: 2px 0;
}
.trajectory-detail-key {
  flex-shrink: 0;
  min-width: 72px;
  color: var(--color-text-muted);
}
.trajectory-detail-row code {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--color-primary-light);
  word-break: break-all;
}
.trajectory-detail-block {
  margin-top: var(--space-2);
}
.trajectory-detail-block pre {
  margin: 4px 0 0;
  padding: var(--space-2);
  max-height: 220px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.5;
  color: var(--color-text-secondary);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
