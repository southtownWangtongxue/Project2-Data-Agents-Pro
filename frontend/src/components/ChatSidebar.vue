<script setup lang="ts">
/**
 * ChatSidebar.vue (Phase E.6) — 持久侧边栏组件
 *
 * 功能：
 *   - 新建会话按钮
 *   - 缓存列表（按时间倒序），点击恢复历史消息
 *   - 双击标题 → 内联编辑
 *   - hover 显示删除按钮
 *   - 当前活跃会话高亮（左侧色条 + 背景）
 *   - 相对时间显示
 */
import { ref, computed } from 'vue'
import { useChatStore, type SessionInfo } from '@/stores/chat'

const store = useChatStore()

/* 会话搜索关键字（对齐 Harness 工作区搜索框） */
const searchQuery = ref('')

/* 按关键字过滤后的会话（标题/问题模糊匹配） */
const filteredSessions = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return store.sessions
  return store.sessions.filter(s =>
    (s.title || '').toLowerCase().includes(q) ||
    (s.question || '').toLowerCase().includes(q)
  )
})

/* 会话分组（阶段3 A9：按日期分组，对齐 Harness 会话树分组） */
const groupedSessions = computed(() => {
  const groups: { label: string; items: SessionInfo[] }[] = []
  const today: SessionInfo[] = []
  const earlier: SessionInfo[] = []
  const todayStr = new Date().toDateString()
  for (const s of filteredSessions.value) {
    const d = s.created_at ? new Date(s.created_at).toDateString() : ''
    if (d === todayStr) today.push(s)
    else earlier.push(s)
  }
  if (today.length) groups.push({ label: '今天', items: today })
  if (earlier.length) groups.push({ label: '更早', items: earlier })
  return groups
})

/* 是否存在匹配结果（搜索无结果提示用） */
const hasFiltered = computed(() => filteredSessions.value.length > 0)

const emit = defineEmits<{
  (e: 'select', threadId: string): void
}>()

/* 内联编辑状态 */
const editingThreadId = ref('')
const editingTitle = ref('')

/* 删除确认状态 */
const deletingSession = ref<SessionInfo | null>(null)

function handleClick(session: SessionInfo) {
  if (editingThreadId.value) return  // 编辑中不触发
  emit('select', session.thread_id)
}

function startEdit(session: SessionInfo, event: MouseEvent) {
  event.stopPropagation()
  editingThreadId.value = session.thread_id
  editingTitle.value = session.title || session.question?.slice(0, 20) || '无标题'
}

function confirmEdit() {
  if (editingThreadId.value && editingTitle.value.trim()) {
    store.editSessionTitle(editingThreadId.value, editingTitle.value.trim())
  }
  editingThreadId.value = ''
  editingTitle.value = ''
}

function cancelEdit() {
  editingThreadId.value = ''
  editingTitle.value = ''
}

function handleDelete(session: SessionInfo, event: MouseEvent) {
  event.stopPropagation()
  deletingSession.value = session
}

function confirmDelete() {
  if (!deletingSession.value) return
  const threadId = deletingSession.value.thread_id
  store.deleteSession(threadId)
  // 如果删除的是当前活跃会话，清空消息区
  if (store.currentThreadId === threadId) {
    store.clearMessages()
  }
  deletingSession.value = null
}

function cancelDelete() {
  deletingSession.value = null
}

function relativeTime(dateStr: string): string {
  if (!dateStr) return ''
  const then = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - then.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 30) return `${diffDay}天前`
  return then.toLocaleDateString('zh-CN')
}
</script>

<template>
  <aside class="chat-sidebar">
    <!-- 顶部：新建会话 -->
    <div class="sidebar-top">
      <button class="sidebar-new-btn" @click="store.newSession(); $emit('select', '')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新建会话
      </button>

      <!-- 搜索框（对齐 Harness 搜索会话） -->
      <div class="sidebar-search">
        <svg class="sidebar-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/>
          <path d="m21 21-4.3-4.3"/>
        </svg>
        <input
          v-model="searchQuery"
          class="sidebar-search-input"
          type="text"
          placeholder="搜索会话…"
        />
        <button v-if="searchQuery" class="sidebar-search-clear" @click="searchQuery = ''" title="清除">×</button>
      </div>
    </div>

    <!-- 会话列表（按日期分组） -->
    <div class="sidebar-list" v-if="store.sessions.length && hasFiltered">
      <template v-for="g in groupedSessions" :key="g.label">
        <div class="sidebar-group-label">{{ g.label }} ({{ g.items.length }})</div>
        <div
          v-for="s in g.items"
          :key="s.thread_id"
          class="sidebar-item"
          :class="{ 'is-active': store.currentThreadId === s.thread_id }"
          @click="handleClick(s)"
        >
          <div class="sidebar-item-content">
            <!-- 内联编辑 -->
            <div v-if="editingThreadId === s.thread_id" class="sidebar-edit-wrap" @click.stop>
              <input
                v-model="editingTitle"
                class="sidebar-edit-input"
                ref="editInputRef"
                @keydown.enter="confirmEdit()"
                @keydown.escape="cancelEdit()"
                @blur="confirmEdit()"
              />
            </div>
            <template v-else>
              <div class="sidebar-item-title" @dblclick="startEdit(s, $event)">
                {{ s.title || s.question?.slice(0, 30) || '无标题' }}
              </div>
              <div class="sidebar-item-meta">
                {{ s.message_count }} 条 · {{ relativeTime(s.created_at) }}
              </div>
            </template>
          </div>
          <button
            v-if="editingThreadId !== s.thread_id"
            class="sidebar-item-delete"
            @click="handleDelete(s, $event)"
            title="删除会话"
          >×</button>
        </div>
      </template>
    </div>

    <!-- 搜索无结果 -->
    <div v-else-if="store.sessions.length && !hasFiltered" class="sidebar-empty">
      <p>无匹配会话</p>
      <p class="sidebar-empty-hint">换个关键词试试</p>
    </div>

    <!-- 空状态 -->
    <div v-else class="sidebar-empty">
      <p>暂无会话记录</p>
      <p class="sidebar-empty-hint">开始一段对话吧</p>
    </div>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <div v-if="deletingSession" class="confirm-overlay" @click.self="cancelDelete">
        <div class="confirm-dialog">
          <div class="confirm-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <h3 class="confirm-title">确认删除</h3>
          <p class="confirm-body">
            删除会话「<strong>{{ deletingSession.title || deletingSession.question?.slice(0, 30) || '无标题' }}</strong>」后<strong>无法恢复</strong>，确定要删除吗？
          </p>
          <div class="confirm-actions">
            <button class="confirm-btn confirm-btn-cancel" @click="cancelDelete">取消</button>
            <button class="confirm-btn confirm-btn-danger" @click="confirmDelete">确认删除</button>
          </div>
        </div>
      </div>
    </Teleport>
  </aside>
</template>

<style scoped>
.chat-sidebar {
  width: 280px;
  min-width: 280px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  overflow: hidden;
}

/* 顶部新建按钮 */
.sidebar-top {
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.sidebar-new-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-4);
  background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.sidebar-new-btn:hover {
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
  transform: translateY(-1px);
}

/* 搜索框（对齐 Harness 搜索会话） */
.sidebar-search {
  position: relative;
  margin-top: var(--space-3);
}

.sidebar-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-muted);
  pointer-events: none;
}

.sidebar-search-input {
  width: 100%;
  padding: 6px 28px 6px 30px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-text-primary);
  outline: none;
  transition: border-color var(--transition-fast);
  font-family: var(--font-sans);
}

.sidebar-search-input:focus {
  border-color: rgba(99, 102, 241, 0.4);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.08);
}

.sidebar-search-clear {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.sidebar-search-clear:hover {
  color: var(--color-text-primary);
}

/* 会话列表 */
.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.sidebar-list::-webkit-scrollbar {
  width: 4px;
}

.sidebar-list::-webkit-scrollbar-thumb {
  background-color: var(--color-border);
  border-radius: var(--radius-full);
}

/* 分组标题（阶段3 A9） */
.sidebar-group-label {
  padding: var(--space-2) var(--space-3) var(--space-1);
  font-size: 11px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* 会话项 */
.sidebar-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-bottom: 2px;
  border-left: 3px solid transparent;
  /* 浏览器级渲染跳过（轻量虚拟滚动：超长列表只渲染可视区附近的 DOM） */
  content-visibility: auto;
  contain-intrinsic-size: 48px;
}

.sidebar-item:hover {
  background: var(--color-surface-elevated);
}

.sidebar-item.is-active {
  background: rgba(99, 102, 241, 0.08);
  border-left-color: var(--color-primary);
}

.sidebar-item-content {
  flex: 1;
  min-width: 0;
}

.sidebar-item-title {
  font-size: 13px;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: default;
  transition: color var(--transition-fast);
}

.sidebar-item:hover .sidebar-item-title {
  color: var(--color-primary-light);
}

.sidebar-item-meta {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

/* 删除按钮 */
.sidebar-item-delete {
  background: none;
  border: none;
  color: var(--color-text-muted);
  font-size: 18px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  opacity: 0;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.sidebar-item:hover .sidebar-item-delete {
  opacity: 1;
}

.sidebar-item-delete:hover {
  color: var(--color-error);
  background: rgba(239, 68, 68, 0.1);
}

/* 内联编辑 */
.sidebar-edit-wrap {
  width: 100%;
}

.sidebar-edit-input {
  width: 100%;
  padding: 4px 8px;
  background: var(--color-bg);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--color-text-primary);
  outline: none;
  font-family: var(--font-sans);
}

/* 空状态 */
.sidebar-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8);
  color: var(--color-text-muted);
  font-size: 13px;
  text-align: center;
  gap: var(--space-2);
}

.sidebar-empty-hint {
  font-size: 12px;
  opacity: 0.6;
}

/* 删除确认弹窗 */
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.confirm-dialog {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  padding: var(--space-8);
  max-width: 400px;
  width: 90%;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: confirmFadeIn 0.2s ease;
}

@keyframes confirmFadeIn {
  from { opacity: 0; transform: scale(0.95) translateY(-8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}

.confirm-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin: 0 auto var(--space-4);
  background: rgba(239, 68, 68, 0.1);
  border-radius: var(--radius-full);
  color: var(--color-error);
}

.confirm-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.confirm-body {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin-bottom: var(--space-6);
}

.confirm-body strong {
  color: var(--color-text-primary);
}

.confirm-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: center;
}

.confirm-btn {
  padding: var(--space-2) var(--space-6);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all var(--transition-fast);
}

.confirm-btn-cancel {
  background: var(--color-surface-elevated);
  color: var(--color-text-secondary);
  border-color: var(--color-border);
}

.confirm-btn-cancel:hover {
  background: var(--color-border);
}

.confirm-btn-danger {
  background: var(--color-error);
  color: white;
}

.confirm-btn-danger:hover {
  background: #dc2626;
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
}
</style>
