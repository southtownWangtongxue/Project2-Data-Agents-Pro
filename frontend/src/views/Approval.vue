<script setup lang="ts">
/**
 * 审批管理页面
 * 展示高危 SQL 审批任务列表
 * 设计风格：深色主题 + Apple 极简美学
 */
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useApprovalStore } from '@/stores/approval'
import type { ApprovalTask } from '@/stores/approval'

const store = useApprovalStore()

/* 审批操作加载中标记 */
const approvingMap = ref<Record<string, boolean>>({})

/* 格式化时间戳为可读字符串 */
function formatTime(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/* 截断过长的 SQL 语句 */
function shortSQL(sql: string): string {
  if (sql.length > 80) return sql.slice(0, 80) + '...'
  return sql
}

/* 根据状态返回样式 */
function statusConfig(status: string) {
  switch (status) {
    case 'pending':
      return { type: 'warning', label: '待审批', bg: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b', border: 'rgba(245, 158, 11, 0.3)' }
    case 'approved':
      return { type: 'success', label: '已通过', bg: 'rgba(34, 197, 94, 0.15)', color: '#22c55e', border: 'rgba(34, 197, 94, 0.3)' }
    case 'rejected':
      return { type: 'danger', label: '已驳回', bg: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', border: 'rgba(239, 68, 68, 0.3)' }
    default:
      return { type: 'info', label: status, bg: 'rgba(161, 161, 170, 0.15)', color: '#a1a1aa', border: 'rgba(161, 161, 170, 0.3)' }
  }
}

/* 复制完整 SQL 到剪贴板 */
async function copySQL(sql: string) {
  try {
    await navigator.clipboard.writeText(sql)
    ElMessage.success('SQL 已复制到剪贴板')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = sql
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    ElMessage.success('SQL 已复制到剪贴板')
  }
}

/* 执行"通过"审批操作 */
async function doApprove(task: ApprovalTask) {
  ElMessageBox.prompt('请输入审批备注（可选）', '确认通过', {
    confirmButtonText: '确认通过',
    cancelButtonText: '取消',
    inputPlaceholder: '审批备注...',
  }).then(async ({ value }) => {
    approvingMap.value[task.threadId] = true
    try {
      await store.approveTask(task.threadId, value || undefined)
      ElMessage.success(`任务已通过审批`)
    } catch {
      ElMessage.error('审批请求失败，请稍后重试')
    } finally {
      approvingMap.value[task.threadId] = false
    }
  }).catch(() => {})
}

/* 执行"驳回"审批操作 */
async function doReject(task: ApprovalTask) {
  ElMessageBox.prompt('请输入驳回理由（可选）', '确认驳回', {
    confirmButtonText: '确认驳回',
    cancelButtonText: '取消',
    type: 'error',
    inputPlaceholder: '驳回理由...',
  }).then(async ({ value }) => {
    approvingMap.value[task.threadId] = true
    try {
      await store.rejectTask(task.threadId, value || undefined)
      ElMessage.success(`任务已驳回`)
    } catch {
      ElMessage.error('驳回请求失败，请稍后重试')
    } finally {
      approvingMap.value[task.threadId] = false
    }
  }).catch(() => {})
}

/* 清除已完成任务 */
function handleRemove(task: ApprovalTask) {
  store.removeTask(task.threadId)
  ElMessage.success('任务已移除')
}

/* 判断某行是否正在执行审批操作 */
function isApprovingTask(threadId: string): boolean {
  return !!approvingMap.value[threadId]
}
</script>

<template>
  <div class="approval-container">
    <!-- 页面标题 -->
    <header class="approval-header">
      <div class="header-content">
        <div class="header-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
        <div class="header-text">
          <h1 class="approval-title">高危 SQL 审批管理</h1>
          <p class="approval-subtitle">管理待审批的数据操作请求，确保数据安全</p>
        </div>
      </div>
      <div class="header-stats">
        <div class="stat-item">
          <span class="stat-value stat-pending">{{ store.tasks.filter(t => t.status === 'pending').length }}</span>
          <span class="stat-label">待审批</span>
        </div>
        <div class="stat-divider"></div>
        <div class="stat-item">
          <span class="stat-value stat-total">{{ store.tasks.length }}</span>
          <span class="stat-label">总计</span>
        </div>
      </div>
    </header>

    <!-- 任务列表表格 -->
    <div class="approval-table-wrapper">
      <!-- 空状态 -->
      <div v-if="store.tasks.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
            <rect x="8" y="8" width="48" height="48" rx="12" fill="rgba(99, 102, 241, 0.1)" stroke="#6366f1" stroke-width="2"/>
            <path d="M24 32l8 8 16-16" stroke="#6366f1" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h3 class="empty-title">暂无待审批任务</h3>
        <p class="empty-text">所有数据操作请求均已处理完毕</p>
      </div>

      <!-- 任务列表 -->
      <div v-else class="task-list">
        <div
          v-for="task in store.tasks"
          :key="task.threadId"
          class="task-card"
          :class="{ 'is-pending': task.status === 'pending' }"
        >
          <div class="task-header">
            <div class="task-id">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/>
                <line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              {{ task.threadId }}
            </div>
            <span
              class="task-status"
              :style="{
                background: statusConfig(task.status).bg,
                color: statusConfig(task.status).color,
                borderColor: statusConfig(task.status).border
              }"
            >
              <span class="status-dot" v-if="task.status === 'pending'"></span>
              {{ statusConfig(task.status).label }}
            </span>
          </div>

          <div class="task-body">
            <div class="task-question">
              <div class="field-label">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
                用户问题
              </div>
              <p class="field-value">{{ task.question }}</p>
            </div>

            <div class="task-sql">
              <div class="field-label">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="16 18 22 12 16 6"/>
                  <polyline points="8 6 2 12 8 18"/>
                </svg>
                SQL 语句
              </div>
              <div class="sql-block">
                <code>{{ shortSQL(task.sql) }}</code>
                <button class="copy-btn" @click="copySQL(task.sql)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="task-reason">
              <div class="field-label">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
                危险原因
              </div>
              <p class="field-value warning">{{ task.reason }}</p>
            </div>
          </div>

          <div class="task-footer">
            <div class="task-time">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              {{ formatTime(task.createdAt) }}
            </div>
            
            <div class="task-actions">
              <template v-if="task.status === 'pending'">
                <button
                  class="action-btn action-reject"
                  :disabled="isApprovingTask(task.threadId)"
                  @click="doReject(task)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                  驳回
                </button>
                <button
                  class="action-btn action-approve"
                  :disabled="isApprovingTask(task.threadId)"
                  @click="doApprove(task)"
                >
                  <svg v-if="!isApprovingTask(task.threadId)" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  <span v-else class="btn-spinner"></span>
                  通过
                </button>
              </template>
              <template v-else>
                <button class="action-btn action-remove" @click="handleRemove(task)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                  移除
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* === 整体布局 === */
.approval-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: calc(100vh - 64px);
  background-color: var(--color-bg);
}

/* === 页面标题栏 === */
.approval-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-6);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

.header-content {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  background: rgba(99, 102, 241, 0.1);
  border-radius: var(--radius-lg);
  color: var(--color-primary-light);
}

.approval-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-1);
}

.approval-subtitle {
  font-size: 13px;
  color: var(--color-text-muted);
}

.header-stats {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-5);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
}

.stat-pending {
  color: #f59e0b;
}

.stat-total {
  color: var(--color-text-primary);
}

.stat-label {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: var(--space-1);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-divider {
  width: 1px;
  height: 32px;
  background: var(--color-border);
}

/* === 表格容器 === */
.approval-table-wrapper {
  flex: 1;
  padding: var(--space-6);
  overflow-y: auto;
}

.approval-table-wrapper::-webkit-scrollbar {
  width: 6px;
}

.approval-table-wrapper::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: var(--radius-full);
}

/* === 空状态 === */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-16) var(--space-6);
  text-align: center;
}

.empty-icon {
  margin-bottom: var(--space-6);
}

.empty-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.empty-text {
  font-size: 14px;
  color: var(--color-text-muted);
}

/* === 任务列表 === */
.task-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 900px;
  margin: 0 auto;
}

.task-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  overflow: hidden;
  transition: all var(--transition-normal);
}

.task-card:hover {
  border-color: var(--color-border-light);
}

.task-card.is-pending {
  border-left: 3px solid #f59e0b;
}

.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid var(--color-border);
}

.task-id {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}

.task-status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  border: 1px solid;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.task-body {
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.task-question,
.task-sql,
.task-reason {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.field-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.field-value {
  font-size: 14px;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.field-value.warning {
  color: #fbbf24;
}

.sql-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: #0d0d0f;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.sql-block code {
  font-family: var(--font-mono);
  font-size: 13px;
  color: #e2e8f0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-1);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.copy-btn:hover {
  background: var(--color-surface-elevated);
  color: var(--color-text-secondary);
}

.task-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--color-border);
  background: rgba(255, 255, 255, 0.01);
}

.task-time {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 12px;
  color: var(--color-text-muted);
}

.task-actions {
  display: flex;
  gap: var(--space-3);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border: 1px solid;
  border-radius: var(--radius-lg);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-approve {
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.3);
  color: #22c55e;
}

.action-approve:hover:not(:disabled) {
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.5);
}

.action-reject {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.action-reject:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
}

.action-remove {
  background: transparent;
  border-color: var(--color-border);
  color: var(--color-text-muted);
}

.action-remove:hover:not(:disabled) {
  background: var(--color-surface-elevated);
  border-color: var(--color-border-light);
  color: var(--color-text-secondary);
}

.btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(34, 197, 94, 0.3);
  border-top-color: #22c55e;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* === Responsive === */
@media (max-width: 768px) {
  .approval-header {
    flex-direction: column;
    gap: var(--space-4);
    align-items: flex-start;
  }
  
  .header-stats {
    width: 100%;
    justify-content: center;
  }
  
  .task-footer {
    flex-direction: column;
    gap: var(--space-3);
    align-items: stretch;
  }
  
  .task-time {
    justify-content: center;
  }
  
  .task-actions {
    justify-content: center;
  }
}
</style>
