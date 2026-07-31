<script setup lang="ts">
/**
 * ScheduleConfig.vue — 定时任务管理 (NL2Cron + APScheduler)
 * 重新设计：深色主题 + 任务卡片 + 可视化时间线
 */
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import apiClient from '@/api/client'

interface Task {
  id: string; name: string; prompt: string; cron: string; mode: string; enabled: boolean
}

const tasks = ref<Task[]>([])
const dialogVisible = ref(false)
const form = ref({ name: '', prompt: '', cron: '', mode: 'task', enabled: true })

/* 模式映射 */
const modeConfig: Record<string, { label: string; color: string }> = {
  data: { label: '数据分析', color: '#6366f1' },
  report: { label: '报告生成', color: '#f59e0b' },
  task: { label: '通用任务', color: '#22c55e' },
}

/* 解析 Cron 为可读描述 */
function parseCron(cron: string): string {
  if (!cron) return '-'
  const parts = cron.split(/\s+/)
  if (parts.length !== 5) return cron
  
  // 简单解析常见模式
  const [minute, hour, , monthDay, weekDay] = parts
  if (minute === '*' && hour === '*') return '每分钟'
  if (hour === '*' && minute === '0') return '每小时整点'
  if (monthDay === '*' && weekDay === '*') return `每天 ${hour}:${minute.padStart(2, '0')}`
  
  return cron
}

/* 获取下次执行时间的模拟显示 */
function getNextRun(task: Task): string {
  if (!task.cron || !task.enabled) return '-'
  return parseCron(task.cron)
}

async function load() {
  try {
    const data = await apiClient.get('/schedule/list')
    tasks.value = data.tasks || []
  } catch { /* empty */ }
}

async function create() {
  try {
    const resp = await apiClient.post('/schedule/create', form.value)
    ElMessage.success(`创建成功，cron 表达式：${resp.cron}`)
    dialogVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  }
}

async function remove(task: Task, idx: number) {
  tasks.value.splice(idx, 1)
  await apiClient.delete(`/schedule/${task.id}`)
  ElMessage.success('已删除')
}

async function toggle(task: Task) {
  await apiClient.put(`/schedule/${task.id}/toggle`, { enabled: !task.enabled })
  await load()
}

function openAdd() {
  form.value = { name: '', prompt: '', cron: '', mode: 'task', enabled: true }
  dialogVisible.value = true
}

onMounted(load)
</script>

<template>
  <div class="admin-page-container">
    <!-- 页面头部 -->
    <div class="admin-page-header">
      <div>
        <h2 class="admin-page-title">
          <span class="admin-page-title-icon" style="background: linear-gradient(135deg, #ec4899, #db2777);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
          </span>
          定时任务管理
        </h2>
        <p class="admin-page-desc">使用自然语言定义定时任务，支持 NL2Cron 自动解析与手动编辑</p>
      </div>
      <el-button type="primary" @click="openAdd" size="large">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 6px;">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新建任务
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">总任务数</div>
        <div class="stat-value">{{ tasks.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">运行中</div>
        <div class="stat-value" style="color: var(--color-success);">{{ tasks.filter(t => t.enabled).length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">暂停</div>
        <div class="stat-value" style="color: var(--color-warning);">{{ tasks.filter(t => !t.enabled).length }}</div>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="content-card">
      <div v-if="tasks.length" class="task-timeline">
        <div v-for="(task, i) in tasks" :key="task.id" class="task-item" :class="{ active: task.enabled }">
          <!-- 时间线指示器 -->
          <div class="timeline-indicator">
            <div class="timeline-dot" :class="{ pulse: task.enabled }"></div>
            <div v-if="i < tasks.length - 1" class="timeline-line"></div>
          </div>
          
          <!-- 任务内容 -->
          <div class="task-body">
            <div class="task-main">
              <div class="task-header-row">
                <h4 class="task-name">{{ task.name }}</h4>
                <div class="task-actions">
                  <el-switch
                    :model-value="task.enabled"
                    @change="toggle(task)"
                    size="small"
                  />
                  <el-button link type="danger" size="small" @click="remove(task, i)">
                    删除
                  </el-button>
                </div>
              </div>
              
              <p class="task-prompt">{{ task.prompt }}</p>
              
              <div class="task-meta">
                <div class="meta-tag-group">
                  <el-tag
                    size="small"
                    :effect="'dark'"
                    :style="{ backgroundColor: modeConfig[task.mode]?.color || '#71717a', borderColor: modeConfig[task.mode]?.color || '#71717a' }"
                  >
                    {{ modeConfig[task.mode]?.label || task.mode }}
                  </el-tag>
                  
                  <el-tag size="small" type="info" effect="plain" class="cron-tag">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 4px; vertical-align: middle;">
                      <circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/>
                    </svg>
                    {{ parseCron(task.cron) }}
                  </el-tag>
                  
                  <code v-if="task.cron" class="cron-expression">{{ task.cron }}</code>
                </div>
                
                <div class="next-run" v-if="task.enabled && task.cron">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--color-text-muted);">
                    <circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/>
                  </svg>
                  下次执行: {{ getNextRun(task) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div v-else class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12,6 12,12 16,14"/>
        </svg>
        <p>暂无定时任务</p>
        <el-button type="primary" @click="openAdd" style="margin-top: 12px;">创建第一个定时任务</el-button>
      </div>
    </div>

    <!-- 新建弹窗 -->
    <el-dialog v-model="dialogVisible" title="新建定时任务" width="500px">
      <el-form label-width="80px">
        <el-form-item label="任务名">
          <el-input v-model="form.name" placeholder="如：每日销售日报" maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item label="任务描述">
          <el-input
            v-model="form.prompt"
            type="textarea"
            :rows="3"
            placeholder="用自然语言描述定时任务，例如：&#10;• 每天早上9点给我发销售日报&#10;• 每周一汇总上周用户增长数据&#10;• 每月1号自动生成运营报告"
          />
        </el-form-item>
        <el-form-item label="执行模式">
          <el-select v-model="form.mode" placeholder="选择模式">
            <el-option label="数据分析" value="data" />
            <el-option label="报告生成" value="report" />
            <el-option label="通用任务" value="task" />
          </el-select>
        </el-form-item>
        <el-form-item label="Cron（可选）">
          <el-input v-model="form.cron" placeholder="留空则由 LLM 自动从描述生成">
            <template #suffix>
              <span style="font-size: 11px; color: var(--color-text-muted);">可选</span>
            </template>
          </el-input>
          <div style="font-size: 11px; color: var(--color-text-muted); margin-top: 4px; line-height: 1.5;">
            示例：0 9 * * * （每天9点）、0 9 * * 1-5 （工作日9点）
          </div>
        </el-form-item>
        <el-form-item label="立即启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="create">创建任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* Task timeline layout */
.task-timeline {
  position: relative;
  display: flex;
  flex-direction: column;
}

.task-item {
  display: flex;
  gap: var(--space-4);
  padding-bottom: var(--space-5);
  position: relative;
  transition: all var(--transition-fast);
}

.task-item:last-child {
  padding-bottom: 0;
}

.task-item.active .task-body {
  border-left-color: rgba(99, 102, 241, 0.4);
}

/* Timeline indicator */
.timeline-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  padding-top: 8px;
}

.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: var(--color-border);
  border: 2px solid var(--color-surface-elevated);
  z-index: 1;
  transition: all var(--transition-normal);
}

.timeline-dot.pulse {
  background-color: var(--color-primary);
  box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15);
  animation: dot-pulse 2s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15); }
  50% { box-shadow: 0 0 0 8px rgba(99, 102, 241, 0.08); }
}

.timeline-line {
  width: 2px;
  flex: 1;
  background: linear-gradient(180deg, var(--color-border), var(--color-border-light));
  border-radius: 1px;
  margin-top: 4px;
}

/* Task body */
.task-body {
  flex: 1;
  background: rgba(24, 24, 27, 0.5);
  border: 1px solid rgba(63, 63, 70, 0.35);
  border-left: 3px solid transparent;
  border-radius: 0 var(--radius-lg) var(--radius-lg) var(--radius-lg);
  padding: var(--space-4) var(--space-5);
  transition: all var(--transition-fast);
}

.task-body:hover {
  background: rgba(24, 24, 27, 0.7);
  border-color: rgba(99, 102, 241, 0.15);
}

.task-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.task-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.task-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.task-prompt {
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  margin: 0 0 var(--space-3);
  max-height: 40px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* Meta tags */
.task-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.meta-tag-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.cron-tag {
  font-family: var(--font-mono) !important;
  font-size: 11px !important;
}

.cron-expression {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-muted);
  background: rgba(39, 39, 42, 0.6);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(63, 63, 70, 0.4);
}

.next-run {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
