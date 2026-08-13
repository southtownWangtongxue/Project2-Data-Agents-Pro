<script setup lang="ts">
/**
 * LlmConfig.vue — LLM 模型管理
 * 重构：精简统计卡片、优化表格布局、模式名称中文显示、表单防空+自动生成ID
 */
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import apiClient from '@/api/client'

interface LLMProvider {
  id: string; name: string; api_base: string; api_key_env: string
  api_key: string; key_mode: string
  model: string; temperature: number; max_tokens: number
  is_default: boolean; enabled: boolean
}

/* 模式中文名称映射 */
const modeDisplayNames: Record<string, string> = {
  data: '📊 数据分析', report: '📝 研究报告',
  doc: '📖 文档智读', task: '🤖 通用任务',
}

/* 生成模型 ID：取名称拼音首字母 + 小写化 */
function generateId(name: string): string {
  return name.toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9\-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

const providers = ref<LLMProvider[]>([])
const modeDefaults = ref<Record<string, string>>({})
const dialogVisible = ref(false)
const editing = ref<LLMProvider | null>(null)
const form = ref<LLMProvider>({ id: '', name: '', api_base: '', api_key_env: '', api_key: '', key_mode: 'env', model: '', temperature: 0.3, max_tokens: 4096, is_default: false, enabled: true })
const submitting = ref(false)

/* 统计数据 */
const stats = computed(() => ({
  total: providers.value.length,
  enabled: providers.value.filter(p => p.enabled).length,
}))

/* 默认模型名称 */
const defaultProviderName = computed(() => {
  const d = providers.value.find(p => p.is_default)
  return d?.name || '未设置'
})

/* 加载 */
async function load() {
  try {
    const data = await apiClient.get('/config/llm')
    providers.value = data.providers
    modeDefaults.value = data.mode_defaults
  } catch { ElMessage.error('加载失败') }
}

/* 新增 */
function openAdd() {
  editing.value = null;
  (form.value as any) = { id: '', name: '', api_base: '', api_key_env: '', api_key: '', key_mode: 'env', model: '', temperature: 0.3, max_tokens: 4096, is_default: false, enabled: true }
  dialogVisible.value = true
}

/* 编辑 */
function openEdit(p: LLMProvider) {
  editing.value = p
  form.value = { ...p }
  dialogVisible.value = true
}

/* 名称变化时自动填充 ID（仅新增模式） */
watch(() => form.value.name, (val) => {
  if (!editing.value && val) {
    form.value.id = generateId(val)
    form.value.model = form.value.id
  }
})

/* 保存 */
async function save() {
  const f = form.value
  if (!f.name.trim()) { ElMessage.warning('请输入模型名称'); return }
  if (!f.api_base.trim()) { ElMessage.warning('请输入 API 地址'); return }
  if (!f.model.trim()) { ElMessage.warning('请输入模型标识名'); return }
  if (f.key_mode === 'env' && !f.api_key_env.trim()) { ElMessage.warning('请输入环境变量名'); return }
  if (f.key_mode === 'direct' && !f.api_key.trim()) { ElMessage.warning('请输入 API Key'); return }
  if (!editing.value && !f.id.trim()) { ElMessage.warning('模型 ID 不能为空'); return }
  // 检查 ID 重复（新增时）
  if (!editing.value && providers.value.some(p => p.id === f.id)) {
    ElMessage.warning(`模型 ID "${f.id}" 已存在，请修改名称后重试`)
    return
  }
  submitting.value = true
  try {
    if (editing.value) {
      await apiClient.put(`/config/llm/${editing.value.id}`, f)
    } else {
      await apiClient.post('/config/llm', f)
    }
    dialogVisible.value = false
    await load()
    ElMessage.success('保存成功')
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
  finally { submitting.value = false }
}

/* 删除 */
async function remove(p: LLMProvider) {
  if (!p.id) { ElMessage.warning('模型 ID 不能为空'); return }
  try {
    await ElMessageBox.confirm(`确认删除模型 "${p.name}"？此操作不可撤销。`, '删除确认', {
      confirmButtonText: '确定删除', cancelButtonText: '取消',
      type: 'warning', confirmButtonClass: 'el-button--danger',
    })
    await apiClient.delete(`/config/llm/${p.id}`)
    await load()
    ElMessage.success('已删除')
  } catch { /* cancelled */ }
}

/* 切换启用 */
async function toggleEnabled(p: LLMProvider) {
  if (!p.id) { ElMessage.warning('模型 ID 不能为空'); await load(); return }
  await apiClient.put(`/config/llm/${p.id}`, { ...p, enabled: !p.enabled })
  await load()
}

onMounted(load)
</script>

<template>
  <div class="admin-page-container">
    <!-- 页面头部 -->
    <div class="admin-page-header">
      <div>
        <h2 class="admin-page-title">
          <span class="admin-page-title-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
              <polyline points="3.27,6.96 12,12.01 20.73,6.96"/>
              <line x1="12" y1="22.08" x2="12" y2="12"/>
            </svg>
          </span>
          LLM 模型管理
        </h2>
        <p class="admin-page-desc">配置和管理大语言模型提供商，支持多模型切换与参数调优</p>
      </div>
      <el-button type="primary" @click="openAdd" size="large">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 6px;">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新增模型
      </el-button>
    </div>

    <!-- 统计卡片（仅总数 + 已启用） -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">总模型数</div>
        <div class="stat-value">{{ stats.total }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已启用</div>
        <div class="stat-value" style="color: var(--color-success);">{{ stats.enabled }}</div>
      </div>
    </div>

    <!-- 模型列表表格 -->
    <div class="content-card table-card">
      <el-table :data="providers" stripe style="width:100%" table-layout="auto">
        <!-- 模型信息列 -->
        <el-table-column label="模型" min-width="200">
          <template #default="{ row }">
            <div class="model-info">
              <div class="model-info-top">
                <span class="provider-name">{{ row.name }}</span>
                <el-tag v-if="row.is_default" type="primary" size="small" effect="dark">默认</el-tag>
              </div>
              <code class="model-ident">{{ row.model }}</code>
            </div>
          </template>
        </el-table-column>
        <!-- API 地址 -->
        <el-table-column label="API 地址" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="api-url">{{ row.api_base }}</span>
          </template>
        </el-table-column>
        <!-- 密钥 -->
        <el-table-column label="密钥" min-width="160">
          <template #default="{ row }">
            <div class="key-display">
              <span v-if="row.key_mode === 'direct'" class="key-tag direct">🔑 直接密钥</span>
              <span v-else class="key-tag env">🌐 环境变量</span>
              <code class="env-var">{{ row.key_mode === 'direct' ? '••••••••' : (row.api_key_env || '-') }}</code>
            </div>
          </template>
        </el-table-column>
        <!-- 参数 -->
        <el-table-column label="参数" width="110" align="center">
          <template #default="{ row }">
            <div class="param-stack">
              <span class="param-row"><span class="param-key">温度</span><span class="param-val">{{ row.temperature }}</span></span>
              <span class="param-row"><span class="param-key">Token</span><span class="param-val">{{ (row.max_tokens / 1000).toFixed(1) }}k</span></span>
            </div>
          </template>
        </el-table-column>
        <!-- 启用状态 -->
        <el-table-column label="启用" width="65" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="toggleEnabled(row)" size="small" />
          </template>
        </el-table-column>
        <!-- 操作 -->
        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!providers.length" class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
        </svg>
        <p>暂无已配置的模型</p>
        <el-button type="primary" @click="openAdd" style="margin-top: 12px;">添加第一个模型</el-button>
      </div>
    </div>

    <!-- 模式默认模型映射 — 紧凑垂直列表 -->
    <div v-if="Object.keys(modeDefaults).length" class="mode-bar">
      <span class="mode-bar-title">模式映射</span>
      <div class="mode-bar-items">
        <div v-for="(value, key) in modeDefaults" :key="key" class="mode-bar-item">
          <span class="mode-bar-mode">{{ modeDisplayNames[key] || key }}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
          <span class="mode-bar-provider">{{ providers.find(p => p.id === value)?.name || value }}</span>
        </div>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑模型' : '新增模型'"
      width="720px"
      :close-on-click-modal="false"
      class="llm-dialog"
    >
      <div class="dialog-body">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-title">基本信息</div>
          <div class="form-grid-2col">
            <div class="form-item">
              <label>模型名称 <span class="required">*</span></label>
              <el-input v-model="form.name" placeholder="如：Qwen-Max、GPT-4o" maxlength="32" show-word-limit clearable />
            </div>
            <div class="form-item">
              <label>模型标识 <span class="required">*</span></label>
              <el-input v-model="form.model" placeholder="实际调用的模型名，如：qwen-max、gpt-4o" clearable />
            </div>
            <div class="form-item span-2">
              <label>API 地址 <span class="required">*</span></label>
              <el-input v-model="form.api_base" placeholder="如：https://dashscope.aliyuncs.com/compatible-mode/v1" clearable />
            </div>
            <div class="form-item span-2">
              <label>密钥配置 <span class="required">*</span></label>
              <div class="key-mode-row">
                <el-radio-group v-model="form.key_mode" size="small">
                  <el-radio-button value="env">环境变量</el-radio-button>
                  <el-radio-button value="direct">直接输入</el-radio-button>
                </el-radio-group>
              </div>
              <el-input
                v-if="form.key_mode === 'env'"
                v-model="form.api_key_env"
                placeholder="如：DASHSCOPE_API_KEY、OPENAI_API_KEY"
                clearable
              />
              <el-input
                v-else
                v-model="form.api_key"
                placeholder="sk-xxx...（密钥将安全存储）"
                type="password"
                show-password
                clearable
              />
            </div>
          </div>
        </div>

        <!-- 参数配置 -->
        <div class="form-section">
          <div class="section-title">参数配置</div>
          <div class="form-row">
            <div class="form-item compact">
              <label>温度 (Temperature)</label>
              <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" :precision="1" controls-position="right" />
            </div>
            <div class="form-item compact">
              <label>最大 Token</label>
              <el-input-number v-model="form.max_tokens" :min="256" :max="128000" :step="256" controls-position="right" />
            </div>
          </div>
        </div>

        <!-- 开关选项 -->
        <div class="form-section switches">
          <div class="switch-row" @click="form.is_default = !form.is_default">
            <div class="switch-info">
              <span class="switch-label">设为默认模型</span>
              <span v-if="form.is_default && defaultProviderName !== form.name && defaultProviderName !== '未设置'" class="switch-hint">
                将替换「{{ defaultProviderName }}」
              </span>
            </div>
            <el-switch v-model="form.is_default" :active-value="true" :inactive-value="false" />
          </div>
          <div class="switch-row">
            <span class="switch-label">启用状态</span>
            <el-switch v-model="form.enabled" :active-value="true" :inactive-value="false" />
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="submitting">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* ── 模型信息列 ── */
.model-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.model-info-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.provider-name {
  font-weight: 600;
  color: var(--color-text-primary);
  font-size: 14px;
}
.model-ident {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-muted);
  background: rgba(113, 113, 122, 0.12);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  width: fit-content;
}

/* ── API 地址 ── */
.api-url {
  font-size: 13px;
  color: var(--color-text-secondary);
  word-break: break-all;
}

/* ── 密钥列 ── */
.key-display {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}
.key-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
}
.key-tag.env {
  color: var(--color-warning);
  background: rgba(245, 158, 11, 0.08);
}
.key-tag.direct {
  color: var(--color-success);
  background: rgba(34, 197, 94, 0.08);
}
.env-var {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-warning);
  background: rgba(245, 158, 11, 0.08);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

/* ── 密钥模式切换 ── */
.key-mode-row {
  margin-bottom: 4px;
}

/* ── 参数堆叠 ── */
.param-stack {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}
.param-key {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}
.param-val {
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  font-weight: 600;
}

/* ── 表格撑满 ── */
.table-card { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.table-card .el-table { flex: 1; }

/* ── 模式映射紧凑横条 ── */
.mode-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: rgba(24,24,27,0.5);
  border: 1px solid rgba(63,63,70,0.3);
  border-radius: var(--radius-md);
  flex-shrink: 0;
}
.mode-bar-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  flex-shrink: 0;
}
.mode-bar-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
}
.mode-bar-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}
.mode-bar-item svg { color: var(--color-text-muted); flex-shrink: 0; }
.mode-bar-mode { font-weight: 500; color: var(--color-text-primary); }
.mode-bar-provider { color: var(--color-primary-light); font-weight: 600; }

/* ── 表单提示 ── */
.form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--color-text-muted);
}

/* ── 弹窗分组卡片式布局 ── */
.dialog-body { padding: 0 4px; }
.form-section {
  margin-bottom: 20px;
}
.form-section:last-child {
  margin-bottom: 0;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 14px;
  padding-left: 10px;
  border-left: 3px solid var(--color-primary);
}
.form-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.form-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px 20px;
}
.form-grid-2col .span-2 {
  grid-column: 1 / -1;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-item label {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}
.form-item .required {
  color: #f56c6c;
}
/* 参数行：两列 */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.form-item.compact .el-input-number { width: 100%; }

/* 开关区 */
.switches {
  background: rgba(24,24,27,0.5);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  border: 1px solid rgba(63,63,70,0.3);
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  cursor: default;
}
.switch-row + .switch-row {
  border-top: 1px solid rgba(63,63,70,0.25);
}
.switch-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.switch-label {
  font-size: 14px;
  color: var(--color-text-primary);
  font-weight: 500;
}
.switch-hint {
  font-size: 12px;
  color: var(--color-warning);
  background: rgba(245,158,11,0.08);
  padding: 2px 8px;
  border-radius: 4px;
}
</style>
