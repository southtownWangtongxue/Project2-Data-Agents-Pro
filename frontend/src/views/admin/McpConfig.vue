<script setup lang="ts">
/**
 * McpConfig.vue — MCP 服务管理
 * 重新设计：深色主题 + 统计卡片 + 优化表格布局
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import apiClient from '@/api/client'

interface McpServer {
  id: string; name: string; command: string; args: string[]; enabled: boolean
}

const servers = ref<McpServer[]>([])
const dialogVisible = ref(false)
const form = ref({ id: '', name: '', command: 'npx', args: '' as string, enabled: false })
const testing = ref(false)
const testResult = ref<{ type: 'success' | 'error' | null; message: string }>({ type: null, message: '' })

/* 统计数据 */
const stats = computed(() => ({
  total: servers.value.length,
  enabled: servers.value.filter(s => s.enabled).length,
}))

async function load() {
  try { const data = await apiClient.get('/config/mcp'); servers.value = data.servers } catch { ElMessage.error('加载失败') }
}

function openAdd() {
  form.value = { id: '', name: '', command: 'npx', args: '', enabled: false }
  testResult.value = { type: null, message: '' }
  dialogVisible.value = true
}

/* 解析启动参数为数组（与保存逻辑一致） */
function parseArgs(raw: string): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed
  } catch {
    /* 非 JSON 则按空格拆分 */
  }
  return raw.split(/\s+/).filter(Boolean)
}

/* 连接测试：保存前验证 MCP 服务端点的连通性 */
async function testConnection() {
  if (!form.value.command.trim()) {
    ElMessage.warning('请先填写启动命令')
    return
  }
  testing.value = true
  testResult.value = { type: null, message: '' }
  try {
    const data = await apiClient.post('/config/mcp/test', {
      command: form.value.command.trim(),
      args: parseArgs(form.value.args),
    }) as { success: boolean; message: string }
    testResult.value = { type: data.success ? 'success' : 'error', message: data.message }
  } catch (e: any) {
    testResult.value = { type: 'error', message: e.response?.data?.message || e.response?.data?.detail || '测试失败' }
  } finally {
    testing.value = false
  }
}

async function save() {
  try {
    // Parse args as JSON array or split by spaces
    let parsedArgs: string[]
    try {
      parsedArgs = JSON.parse(form.value.args || '[]')
    } catch {
      parsedArgs = form.value.args.split(/\s+/).filter(Boolean)
    }
    
    await apiClient.post('/config/mcp', {
      ...form.value,
      args: parsedArgs,
    })
    dialogVisible.value = false
    await load()
    ElMessage.success('服务器添加成功')
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
}

async function remove(s: McpServer, idx: number) {
  await apiClient.delete(`/config/mcp/${s.id}`)
  servers.value.splice(idx, 1)
  ElMessage.success('已删除')
}

onMounted(load)
</script>

<template>
  <div class="admin-page-container">
    <!-- 页面头部 -->
    <div class="admin-page-header">
      <div>
        <h2 class="admin-page-title">
          <span class="admin-page-title-icon" style="background: linear-gradient(135deg, #06b6d4, #0891b2);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </span>
          MCP 服务管理
        </h2>
        <p class="admin-page-desc">Model Context Protocol 服务器配置，扩展 AI Agent 的工具能力边界</p>
      </div>
      <el-button type="primary" @click="openAdd" size="large">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 6px;">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新增服务
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">总服务数</div>
        <div class="stat-value">{{ stats.total }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已启用</div>
        <div class="stat-value" style="color: #06b6d4;">{{ stats.enabled }}</div>
      </div>
    </div>

    <!-- 服务器列表 -->
    <div class="content-card">
      <el-table :data="servers" stripe style="width:100%">
        <el-table-column prop="name" label="名称" width="160">
          <template #default="{ row }">
            <div class="server-name-cell">
              <div class="server-avatar">{{ row.name?.[0]?.toUpperCase() || '?' }}</div>
              <span class="server-name">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="140">
          <template #default="{ row }">
            <code class="server-id">{{ row.id }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="command" label="启动命令" width="110">
          <template #default="{ row }">
            <code class="command-code">{{ row.command }}</code>
          </template>
        </el-table-column>
        <el-table-column label="参数" min-width="200">
          <template #default="{ row }">
            <code class="args-code">{{ row.args?.length ? row.args.join(' ') : '-' }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="dark" round>
              {{ row.enabled ? '运行中' : '已停止' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row, $index }">
            <el-button link type="danger" @click="remove(row, $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div v-if="!servers.length" class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
          <circle cx="12" cy="12" r="3"/>
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
        </svg>
        <p>暂无 MCP 服务器配置</p>
        <el-button type="primary" @click="openAdd" style="margin-top: 12px;">添加第一个服务器</el-button>
      </div>
    </div>

    <!-- 新增弹窗 -->
    <el-dialog v-model="dialogVisible" title="新增 MCP 服务器" width="520px">
      <el-form label-width="80px">
        <el-form-item label="服务 ID"><el-input v-model="form.id" placeholder="filesystem" /></el-form-item>
        <el-form-item label="显示名称"><el-input v-model="form.name" placeholder="文件系统" /></el-form-item>
        <el-form-item label="启动命令"><el-input v-model="form.command" placeholder="npx" /></el-form-item>
        <el-form-item label="启动参数">
          <el-input 
            v-model="form.args" 
            placeholder='["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]'
            type="textarea"
            :rows="2"
          />
          <div style="font-size: 11px; color: var(--color-text-muted); margin-top: 4px;">
            支持 JSON 数组或空格分隔的字符串格式
          </div>
        </el-form-item>
        <el-form-item label="启用状态"><el-switch v-model="form.enabled" /></el-form-item>

        <!-- 连接测试结果 -->
        <div v-if="testResult.type" class="mcp-test-result" :class="testResult.type">
          <span class="mcp-test-icon">{{ testResult.type === 'success' ? '✓' : '✕' }}</span>
          <span>{{ testResult.message }}</span>
        </div>
      </el-form>
      <template #footer>
        <el-button :loading="testing" @click="testConnection">
          <svg v-if="!testing" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;vertical-align:-2px;">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          {{ testing ? '测试中...' : '连接测试' }}
        </el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* Server name cell */
.server-name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.server-avatar {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #06b6d4, #0891b2);
  border-radius: var(--radius-md);
  color: white;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.server-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--color-text-primary);
}

.server-id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-primary-light);
  background: rgba(99, 102, 241, 0.1);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.command-code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-warning);
  background: rgba(245, 158, 11, 0.08);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.args-code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-secondary);
}

/* 连接测试结果 */
.mcp-test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  font-size: 13px;
  line-height: 1.4;
}
.mcp-test-result.success {
  color: var(--color-success);
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.25);
}
.mcp-test-result.error {
  color: #f87171;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.25);
}
.mcp-test-icon {
  flex-shrink: 0;
  font-weight: 700;
}
</style>
