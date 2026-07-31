<script setup lang="ts">
/**
 * KnowledgeConfig.vue — 知识库管理
 * 重新设计：深色主题 + 文件上传区优化 + 搜索结果美化
 */
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import apiClient from '@/api/client'

const documents = ref<any[]>([])
const uploading = ref(false)
const searchQuery = ref('')
const searchResults = ref<any[]>([])
const searching = ref(false)
const uploadProgress = ref(0)

/* 支持的文件类型 */
const acceptTypes = '.pdf,.docx,.md,.txt'

async function load() {
  try { const data = await apiClient.get('/knowledge/list'); documents.value = data.documents || [] } catch { /* empty */ }
}

async function handleUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  
  // 验证文件大小 (最大 50MB)
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.warning('文件大小不能超过 50MB')
    input.value = ''
    return
  }

  uploading.value = true
  uploadProgress.value = 0
  
  // 模拟进度
  const progressInterval = setInterval(() => {
    if (uploadProgress.value < 90) {
      uploadProgress.value += Math.random() * 15
    }
  }, 300)

  try {
    const form = new FormData()
    form.append('file', file)
    await apiClient.post('/knowledge/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    clearInterval(progressInterval)
    uploadProgress.value = 100
    ElMessage.success(`"${file.name}" 上传成功，正在向量化...`)
    setTimeout(async () => {
      uploading.value = false
      uploadProgress.value = 0
      await load()
    }, 500)
  } catch (err: any) {
    clearInterval(progressInterval)
    uploading.value = false
    uploadProgress.value = 0
    ElMessage.error(err.response?.data?.detail || '上传失败')
    input.value = ''
  }
}

async function onSearch() {
  if (!searchQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  
  searching.value = true
  searchResults.value = []
  
  try {
    const data = await apiClient.post(`/knowledge/search?query=${encodeURIComponent(searchQuery.value)}&top_k=5`)
    searchResults.value = data.results || []
  } catch { ElMessage.error('搜索失败') }
  finally { searching.value = false }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

onMounted(load)
</script>

<template>
  <div class="admin-page-container">
    <!-- 页面头部 -->
    <div class="admin-page-header">
      <div>
        <h2 class="admin-page-title">
          <span class="admin-page-title-icon" style="background: linear-gradient(135deg, #22c55e, #16a34a);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
              <line x1="8" y1="6" x2="16" y2="6"/>
              <line x1="8" y1="10" x2="14" y2="10"/>
            </svg>
          </span>
          知识库管理
        </h2>
        <p class="admin-page-desc">上传文档自动解析、切片并向量化存储，支持语义检索与 RAG 增强</p>
      </div>
    </div>

    <!-- 统计 & 操作区 -->
    <div class="actions-row">
      <div class="stats-mini">
        <div class="stat-mini">
          <span class="stat-mini-label">文档总数</span>
          <span class="stat-mini-value">{{ documents.length }}</span>
        </div>
        <div class="stat-mini">
          <span class="stat-mini-label">总切片</span>
          <span class="stat-mini-value">{{ documents.reduce((sum, d) => sum + (d.chunks || 0), 0) }}</span>
        </div>
        <div class="stat-mini">
          <span class="stat-mini-label">总大小</span>
          <span class="stat-mini-value">{{ formatFileSize(documents.reduce((sum, d) => sum + (d.size || 0), 0)) }}</span>
        </div>
      </div>

      <div class="action-buttons">
        <el-upload
          :show-file-list="false"
          :before-upload="() => false"
          @change="handleUpload"
          :accept="acceptTypes"
          :disabled="uploading"
        >
          <el-button type="primary" :loading="uploading" size="large">
            <svg v-if="!uploading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 6px;">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17,8 12,3 7,8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            {{ uploading ? `解析中 ${Math.round(uploadProgress)}%` : '上传文档' }}
          </el-button>
        </el-upload>
        
        <div class="search-input-wrapper">
          <el-input
            v-model="searchQuery"
            placeholder="搜索文档内容..."
            clearable
            @keyup.enter="onSearch"
            style="width: 260px;"
          >
            <template #prefix>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--color-text-muted);">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
            </template>
          </el-input>
          <el-button @click="onSearch" :loading="searching" :type="searchQuery.trim() ? 'primary' : 'default'" size="default">
            搜索
          </el-button>
        </div>
      </div>
    </div>

    <!-- 上传进度 -->
    <div v-if="uploading" class="progress-container">
      <el-progress :percentage="Math.round(uploadProgress)" :stroke-width="6" status="active" :show-text="false" />
    </div>

    <div class="content-grid">
      <!-- 已上传文档列表 -->
      <div class="content-card doc-list-card">
        <h3 class="section-title">
          已上传文档
          <el-badge :value="documents.length" :max="99" type="primary" style="margin-left: 8px;" />
        </h3>
        
        <div v-if="documents.length" class="doc-list">
          <div v-for="(doc, i) in documents" :key="i" class="doc-item">
            <div class="doc-icon" :class="getDocIconClass(doc.name)">
              {{ getDocIcon(doc.name) }}
            </div>
            <div class="doc-info">
              <div class="doc-name">{{ doc.name }}</div>
              <div class="doc-meta">
                <span>{{ doc.chunks }} 个切片</span>
                <span class="meta-divider">|</span>
                <span>{{ formatFileSize(doc.size) }}</span>
              </div>
            </div>
            <div class="doc-status">
              <el-tag type="success" size="small" effect="dark" round>已索引</el-tag>
            </div>
          </div>
        </div>
        <div v-else class="empty-state compact">
          <p>暂无文档，请上传 PDF/Word/Markdown/文本 文件开始构建知识库</p>
        </div>
      </div>

      <!-- 搜索结果 -->
      <div v-if="searchResults.length" class="content-card search-result-card">
        <h3 class="section-title">
          搜索结果
          <el-badge :value="searchResults.length" type="warning" style="margin-left: 8px;" />
        </h3>
        <div class="result-list">
          <div v-for="(r, i) in searchResults" :key="i" class="result-item">
            <div class="result-score">
              <el-progress 
                type="circle" 
                :percentage="Math.round((r.score || 0) * 100)"
                :width="42"
                :stroke-width="5"
                :color="r.score > 0.8 ? '#22c55e' : r.score > 0.5 ? '#f59e0b' : '#ef4444'"
              />
            </div>
            <div class="result-content">
              <p class="result-text">{{ (r.text || r.content)?.slice(0, 250) }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
function getDocIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'pdf': return 'PDF'
    case 'docx': case 'doc': return 'DOC'
    default: return 'TXT'
  }
}

function getDocIconClass(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()
  return ext === 'pdf' ? 'pdf' : ext === 'docx' || ext === 'doc' ? 'word' : 'text'
}
</script>

<style scoped>
/* Actions Row */
.actions-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-5);
  gap: var(--space-4);
  flex-wrap: wrap;
}

.stats-mini {
  display: flex;
  gap: var(--space-5);
}

.stat-mini {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-mini-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.stat-mini-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.search-input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Progress */
.progress-container {
  margin-bottom: var(--space-4);
  padding: 0 var(--space-4);
}

/* Content grid */
.content-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-5);
}

@media (min-width: 900px) {
  .content-grid {
    grid-template-columns: 1fr 1fr;
  }
}

/* Document list card */
.doc-list-card .doc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 12px 14px;
  background: rgba(24, 24, 27, 0.5);
  border: 1px solid rgba(63, 63, 70, 0.3);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.doc-item:hover {
  border-color: rgba(99, 102, 241, 0.25);
  background: rgba(99, 102, 241, 0.05);
}

.doc-icon {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: -0.02em;
  flex-shrink: 0;
}

.doc-icon.pdf { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.doc-icon.word { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
.doc-icon.text { background: rgba(34, 197, 94, 0.15); color: #4ade80; }

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-meta {
  display: flex;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

.meta-divider { color: var(--color-border); }

.doc-status { flex-shrink: 0; }

/* Empty state compact */
.empty-state.compact {
  padding: var(--space-8) var(--space-4);
}

/* Search result card */
.result-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.result-item {
  display: flex;
  gap: var(--space-3);
  padding: 14px;
  background: rgba(24, 24, 27, 0.5);
  border: 1px solid rgba(63, 63, 70, 0.3);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.result-item:hover {
  border-color: rgba(99, 102, 241, 0.25);
}

.result-score {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  padding-top: 4px;
}

.result-content {
  flex: 1;
  min-width: 0;
}

.result-text {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin: 0;
  word-break: break-word;
}
</style>
