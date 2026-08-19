<script setup lang="ts">
/**
 * TrajectoryView.vue — 会话轨迹时间线（阶段4 B2，对齐 Harness Trajectory）
 *
 * 展示会话的完整事件轨迹（含过程态事件 plan/clarification/tool_chain），
 * 数据来自 GET /chat/sessions/{thread_id}/trajectory。
 */
import { ref, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import apiClient from '@/api/client'

interface TrajectoryEvent {
  id: number
  event_type: string
  role: string | null
  content: string
  node_index: number | null
  created_at: string | null
}

const store = useChatStore()
const events = ref<TrajectoryEvent[]>([])
const loading = ref(false)

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

async function load() {
  if (!store.currentThreadId) return
  loading.value = true
  try {
    const data = await apiClient.get(`/chat/sessions/${store.currentThreadId}/trajectory`) as {
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

onMounted(load)

defineExpose({ load, events, loading })
</script>

<template>
  <div class="trajectory-view">
    <div class="trajectory-header">
      <span>会话轨迹</span>
      <span v-if="events.length" class="trajectory-count">{{ events.length }} 个事件</span>
    </div>
    <div v-if="loading" class="trajectory-loading">加载中...</div>
    <div v-else-if="!events.length" class="trajectory-empty">暂无轨迹数据</div>
    <div v-else class="trajectory-list">
      <div v-for="evt in events" :key="evt.id" class="trajectory-item">
        <div class="trajectory-item-dot" :style="{ background: metaOf(evt.event_type).dot }"></div>
        <div class="trajectory-item-body">
          <div class="trajectory-item-head">
            <span class="trajectory-item-label">{{ metaOf(evt.event_type).label }}</span>
            <span class="trajectory-item-time">{{ timeOf(evt.created_at) }}</span>
            <span v-if="evt.node_index !== null" class="trajectory-item-node">轮 {{ evt.node_index + 1 }}</span>
          </div>
          <div v-if="evt.content" class="trajectory-item-content">{{ evt.content }}</div>
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
</style>
