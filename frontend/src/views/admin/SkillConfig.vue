<script setup lang="ts">
/**
 * SkillConfig.vue — Skill 技能管理（动态安装 / 卸载 / 启用）
 *
 * 参考 Claude Code / Codex / CodeBuddy 的技能管理模式：
 * - 每个 Skill 是一个 SKILL.md 规范的文件夹实体（含真实执行脚本）
 * - 内置技能（builtin）仅支持启用/禁用；文件系统技能（folder）支持安装/卸载 + 启用/禁用
 * - 安装 = 从目录库复制文件夹到 skills 实体目录；卸载 = 删除文件夹
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import apiClient from '@/api/client'

interface Skill {
  id: string; name: string; description: string; icon: string
  enabled: boolean; modes: string[]; is_global: boolean; params: Record<string, any>
  type: string; installed: boolean
}

const skills = ref<Skill[]>([])
const filterMode = ref('all')
const loadingId = ref<string | null>(null)

/* 图标映射（icon 为 key 时查表，为 emoji 时直接显示） */
const iconMap: Record<string, string> = {
  database: '🗄️', search: '🔍', chart: '📈', bell: '🔔',
}
function iconOf(s: Skill): string {
  return iconMap[s.icon] || s.icon || '🔧'
}

/* 模式映射 */
const modeMap: Record<string, string> = {
  data: '数据分析', report: '研究报告', doc: '文档智读', task: '通用任务', all: '全部',
}

/* 统计数据 */
const stats = computed(() => ({
  total: skills.value.length,
  installed: skills.value.filter(s => s.installed).length,
  enabled: skills.value.filter(s => s.installed && s.enabled).length,
}))

/* 筛选后的技能列表 */
const filteredSkills = computed(() => {
  if (filterMode.value === 'all') return skills.value
  return skills.value.filter(s => s.modes.includes(filterMode.value) || s.is_global)
})

async function load() {
  try { const data = await apiClient.get('/config/skills'); skills.value = data.skills } catch { ElMessage.error('加载失败') }
}

/* 启用 / 禁用（生命周期） */
async function toggle(s: Skill) {
  if (loadingId.value) return
  loadingId.value = s.id
  try {
    await apiClient.put(`/config/skills/${s.id}`, { enabled: !s.enabled })
    s.enabled = !s.enabled
    ElMessage.success(s.enabled ? '已启用' : '已禁用')
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '操作失败') }
  finally { loadingId.value = null }
}

/* 安装：从目录库复制文件夹到 skills 实体目录 */
async function install(s: Skill) {
  if (loadingId.value) return
  loadingId.value = s.id
  try {
    await apiClient.post('/config/skills/install', { id: s.id })
    s.installed = true
    s.enabled = true
    ElMessage.success(`已安装「${s.name}」`)
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '安装失败') }
  finally { loadingId.value = null }
}

/* 卸载：删除 skills 实体目录 */
async function uninstall(s: Skill) {
  if (loadingId.value) return
  loadingId.value = s.id
  try {
    await apiClient.post('/config/skills/uninstall', { id: s.id })
    s.installed = false
    s.enabled = false
    ElMessage.success(`已卸载「${s.name}」`)
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '卸载失败') }
  finally { loadingId.value = null }
}

onMounted(load)
</script>

<template>
  <div class="admin-page-container">
    <!-- 页面头部 -->
    <div class="admin-page-header">
      <div>
        <h2 class="admin-page-title">
          <span class="admin-page-title-icon" style="background: linear-gradient(135deg, #f59e0b, #d97706);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13,2 3,14 12,14 11,22 21,10 12,10 13,2"/>
            </svg>
          </span>
          Skill 技能管理
        </h2>
        <p class="admin-page-desc">安装 / 卸载技能实体（SKILL.md + 执行脚本），并控制各技能的启用状态</p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">总技能数</div>
        <div class="stat-value">{{ stats.total }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已安装</div>
        <div class="stat-value" style="color: var(--color-primary-light);">{{ stats.installed }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已启用</div>
        <div class="stat-value" style="color: var(--color-success);">{{ stats.enabled }}</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <span class="filter-label">筛选模式：</span>
      <el-radio-group v-model="filterMode" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="data">数据分析</el-radio-button>
        <el-radio-button value="report">研究报告</el-radio-button>
        <el-radio-button value="doc">文档智读</el-radio-button>
        <el-radio-button value="task">通用任务</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 技能卡片网格 -->
    <div class="skill-grid">
      <TransitionGroup name="card-list">
        <div v-for="s in filteredSkills" :key="s.id" class="skill-card" :class="{ enabled: s.installed && s.enabled }">
          <div class="skill-header">
            <div class="skill-icon-wrapper">
              <span class="skill-emoji">{{ iconOf(s) }}</span>
            </div>
            <span class="skill-status" :class="s.installed ? 'on' : 'off'">
              {{ s.installed ? '已安装' : '未安装' }}
            </span>
          </div>

          <h3 class="skill-name">{{ s.name }}</h3>
          <p class="skill-desc">{{ s.description }}</p>

          <div class="skill-tags">
            <el-tag v-if="s.is_global" type="warning" size="small" effect="dark" round>全局</el-tag>
            <el-tag v-for="m in s.modes" :key="m" size="small" effect="plain" round>{{ modeMap[m] || m }}</el-tag>
            <el-tag v-if="s.type === 'builtin'" type="info" size="small" effect="plain" round>内置</el-tag>
          </div>

          <!-- 操作区 -->
          <div class="skill-actions">
            <!-- folder 类型：未安装 → 安装 -->
            <el-button
              v-if="s.type === 'folder' && !s.installed"
              type="primary" size="small" :loading="loadingId === s.id"
              @click="install(s)"
            >安装</el-button>

            <!-- folder 类型：已安装 → 卸载 -->
            <el-button
              v-else-if="s.type === 'folder' && s.installed"
              type="danger" link size="small" :loading="loadingId === s.id"
              @click="uninstall(s)"
            >卸载</el-button>

            <!-- 已安装（folder 或 builtin）→ 启用开关 -->
            <el-switch
              v-if="s.installed"
              :model-value="s.enabled"
              @change="toggle(s)"
              size="small"
              :active-color="'#6366f1'"
              :disabled="loadingId === s.id"
            />
          </div>
        </div>
      </TransitionGroup>
    </div>

    <div v-if="!filteredSkills.length" class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <polygon points="13,2 3,14 12,14 11,22 21,10 12,10 13,2"/>
      </svg>
      <p>{{ filterMode !== 'all' ? '该模式下暂无可用技能' : '暂无已配置的技能' }}</p>
    </div>
  </div>
</template>

<style scoped>
/* Filter bar */
.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  padding: var(--space-3) var(--space-4);
  background: rgba(24, 24, 27, 0.5);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(63, 63, 70, 0.4);
}

.filter-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

/* Skill grid */
.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

/* Skill card */
.skill-card {
  background: linear-gradient(145deg, rgba(24, 24, 27, 0.95), rgba(24, 24, 27, 0.7));
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  opacity: 0.55;
  transition: all var(--transition-normal);
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.skill-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--color-primary), transparent);
  opacity: 0;
  transition: opacity var(--transition-normal);
}

.skill-card:hover {
  border-color: rgba(99, 102, 241, 0.25);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.skill-card.enabled {
  opacity: 1;
  background: linear-gradient(145deg, rgba(24, 24, 27, 0.98), rgba(28, 28, 32, 0.85));
}

.skill-card.enabled::before {
  opacity: 1;
}

/* Skill header */
.skill-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-3);
}

.skill-icon-wrapper {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(99, 102, 241, 0.1);
  border-radius: var(--radius-lg);
}

.skill-emoji {
  font-size: 22px;
  line-height: 1;
}

.skill-name {
  margin: 0 0 var(--space-2) !important;
  font-size: 16px !important;
  font-weight: 600 !important;
  color: var(--color-text-primary) !important;
}

.skill-desc {
  font-size: 13px !important;
  color: var(--color-text-muted) !important;
  line-height: 1.5 !important;
  margin-bottom: var(--space-3) !important;
  min-height: 40px;
}

/* Status badge */
.skill-status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  white-space: nowrap;
}
.skill-status.on {
  color: var(--color-success);
  background: rgba(34, 197, 94, 0.12);
}
.skill-status.off {
  color: var(--color-text-muted);
  background: rgba(113, 113, 122, 0.15);
}

/* Tags */
.skill-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}

/* Actions */
.skill-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: auto;
  padding-top: var(--space-3);
  border-top: 1px solid rgba(63, 63, 70, 0.4);
}

/* Card list transitions */
.card-list-enter-active,
.card-list-leave-active {
  transition: all var(--transition-normal);
}

.card-list-enter-from {
  opacity: 0;
  transform: scale(0.96) translateY(8px);
}

.card-list-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(-8px);
}

.card-list-move {
  transition: transform var(--transition-normal);
}
</style>
