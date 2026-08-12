<script setup lang="ts">
/**
 * XSender.vue — 基于 Ant Design X Vue 的输入区（Ultramodern 风格重构）
 *
 * 官方 API 依据：docs/plans/2026-08-05-ant-design-x-vue-integration.md §2.3
 * - v-model:value + :loading + @submit + @cancel + prefix/header 插槽
 * - 模式切换 + 联网搜索移入 <Sender.Header> 弹出面板（官方样板间方案），prefix 仅留模型选择器
 * - loading=true 时 Sender 自动将发送按钮切换为停止按钮（触发 @cancel）
 */
import { ref, onMounted } from 'vue'
import { Sender } from 'ant-design-x-vue'
import { useChatStore } from '@/stores/chat'
import apiClient from '@/api/client'

const store = useChatStore()

const input = ref('')

/* 工作模式 + 联网搜索 */
const currentMode = ref('data')
const webSearchEnabled = ref(false)

/* Sender.Header 面板开关 */
const headerOpen = ref(false)

const modes = [
  { key: 'data', label: '数据分析', icon: '📊' },
  { key: 'report', label: '研究报告', icon: '📝' },
  { key: 'doc', label: '文档智读', icon: '📖' },
  { key: 'task', label: '通用任务', icon: '🤖' },
]

/* ── 模型选择（与全局 LLM 配置双向同步）── */
interface ChatModel {
  id: string
  name: string
  desc: string
  tag: string
}
const models = ref<ChatModel[]>([])
const modelsLoading = ref(false)
const showModelMenu = ref(false)
let modelMenuTimer: ReturnType<typeof setTimeout> | null = null

async function loadModels() {
  modelsLoading.value = true
  try {
    const data = await apiClient.get('/config/llm') as { providers: any[] }
    const providers = (data.providers || []).filter(p => p.enabled !== false)
    models.value = providers.map((p: any) => ({
      id: p.id,
      name: p.name || p.model || p.id,
      desc: `${p.model || ''} · ${p.api_base || ''}`,
      tag: p.is_default ? '默认' : '',
    }))
    const valid = models.value.some(m => m.id === store.currentModel)
    const def = models.value.find(m => m.tag === '默认') || models.value[0]
    if (!valid && def) {
      store.setCurrentModel(def.id)
    }
  } catch {
    models.value = []
  } finally {
    modelsLoading.value = false
  }
}

function onModelEnter() {
  if (modelMenuTimer) { clearTimeout(modelMenuTimer); modelMenuTimer = null }
  showModelMenu.value = true
}
function onModelLeave() {
  modelMenuTimer = setTimeout(() => { showModelMenu.value = false }, 150)
}
function selectModel(id: string) {
  store.setCurrentModel(id)
  showModelMenu.value = false
}

onMounted(loadModels)

function onSubmit(text: string) {
  if (!text.trim() || store.isLoading) return
  store.sendMessage(text.trim(), currentMode.value, webSearchEnabled.value)
  input.value = ''
}

function onCancel() {
  store.stopGeneration()
}
</script>

<template>
  <div class="xsender-root">
    <Sender
      v-model:value="input"
      :loading="store.isLoading"
      placeholder="用自然语言描述您的需求，Enter 发送，Shift+Enter 换行..."
      @submit="onSubmit"
      @cancel="onCancel"
    >
      <!-- header 弹出面板：模式切换 + 联网搜索（不占用输入框空间） -->
      <template #header>
        <Sender.Header
          class="xsender-header"
          title="对话设置"
          :closable="true"
          :open="headerOpen"
          @open-change="(v: boolean) => (headerOpen = v)"
          force-render
        >
          <div class="xsender-settings">
            <div class="xsender-settings-row">
              <span class="xsender-settings-label">工作模式</span>
              <div class="xsender-modes">
                <button
                  v-for="m in modes" :key="m.key"
                  class="xsender-mode" :class="{ 'is-active': currentMode === m.key }"
                  :title="m.label"
                  @click="currentMode = m.key"
                >{{ m.icon }}<span class="xsender-mode-label">{{ m.label }}</span></button>
              </div>
            </div>
            <div class="xsender-settings-row">
              <span class="xsender-settings-label">联网搜索</span>
              <button
                class="xsender-search" :class="{ 'is-on': webSearchEnabled }"
                @click="webSearchEnabled = !webSearchEnabled"
              >🔍<span class="xsender-mode-label">{{ webSearchEnabled ? '已开启' : '已关闭' }}</span></button>
            </div>
          </div>
        </Sender.Header>
      </template>

      <!-- prefix：模型选择器 + 设置（模式/联网搜索）触发按钮 -->
      <template #prefix>
        <div class="xsender-prefix">
          <button
            class="xsender-settings-btn" :class="{ 'is-open': headerOpen }"
            title="工作模式与联网搜索"
            @click="headerOpen = !headerOpen"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>
          <div class="xsender-model" @mouseenter="onModelEnter" @mouseleave="onModelLeave">
            <button class="xsender-model-trigger" :class="{ 'is-open': showModelMenu }">
              <span class="xsender-model-name">{{ models.find(m => m.id === store.currentModel)?.name || (modelsLoading ? '加载中...' : '选择模型') }}</span>
              <svg class="xsender-model-chevron" :class="{ 'is-open': showModelMenu }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            <Transition name="xsender-menu">
              <div v-if="showModelMenu" class="xsender-model-menu" @mouseenter="onModelEnter" @mouseleave="onModelLeave">
                <div class="xsender-model-menu-header">模型</div>
                <div
                  v-for="m in models" :key="m.id"
                  class="xsender-model-menu-item"
                  :class="{ 'is-active': store.currentModel === m.id }"
                  @click="selectModel(m.id)"
                >
                  <div class="xsender-model-menu-body">
                    <div class="xsender-model-menu-title-row">
                      <span class="xsender-model-menu-title">{{ m.name }}</span>
                      <span v-if="m.tag" class="xsender-model-menu-tag">{{ m.tag }}</span>
                    </div>
                    <span class="xsender-model-menu-desc">{{ m.desc }}</span>
                  </div>
                  <svg v-if="store.currentModel === m.id" class="xsender-model-menu-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary)" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </template>
    </Sender>
  </div>
</template>

<style scoped>
.xsender-root {
  flex-shrink: 0;
  width: 100%;
  padding: 12px 32px 20px;
}
.xsender-prefix {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* 设置按钮（打开 Header 面板） */
.xsender-settings-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 999px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.xsender-settings-btn:hover,
.xsender-settings-btn.is-open {
  background: rgba(112, 86, 248, 0.12);
  color: var(--color-primary-light);
}
/* 模型选择器 */
.xsender-model {
  position: relative;
}
.xsender-model-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(112, 86, 248, 0.1);
  border: 1px solid rgba(112, 86, 248, 0.25);
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-primary-light);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.xsender-model-trigger:hover,
.xsender-model-trigger.is-open {
  background: rgba(112, 86, 248, 0.2);
  border-color: rgba(112, 86, 248, 0.4);
}
.xsender-model-name {
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.xsender-model-chevron {
  transition: transform var(--transition-fast);
  opacity: 0.6;
  flex-shrink: 0;
}
.xsender-model-chevron.is-open { transform: rotate(180deg); }
.xsender-model-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  min-width: 300px;
  max-width: 360px;
  background: var(--color-surface-elevated);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  z-index: 100;
  padding: 4px 0;
}
.xsender-model-menu-header {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.xsender-model-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.xsender-model-menu-item:hover {
  background: rgba(255, 255, 255, 0.04);
}
.xsender-model-menu-item.is-active {
  background: rgba(112, 86, 248, 0.12);
}
.xsender-model-menu-body { flex: 1; min-width: 0; }
.xsender-model-menu-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}
.xsender-model-menu-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}
.xsender-model-menu-tag {
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(112, 86, 248, 0.12);
  color: var(--color-primary-light);
}
.xsender-model-menu-desc {
  display: block;
  font-size: 11px;
  color: var(--color-text-muted);
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.xsender-model-menu-check { flex-shrink: 0; }
.xsender-menu-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.xsender-menu-leave-active { transition: opacity 0.1s ease, transform 0.1s ease; }
.xsender-menu-enter-from { opacity: 0; transform: translateY(-4px) scale(0.98); }
.xsender-menu-leave-to { opacity: 0; transform: translateY(-4px) scale(0.98); }

/* ── Header 面板：模式 + 联网搜索 ── */
.xsender-header {
  max-width: 700px;
  margin: 0 auto;
}
.xsender-settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}
.xsender-settings-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.xsender-settings-label {
  font-size: 12px;
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 56px;
}
.xsender-modes {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.xsender-mode,
.xsender-search {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}
.xsender-mode:hover,
.xsender-search:hover {
  background: rgba(255, 255, 255, 0.04);
}
.xsender-mode.is-active {
  background: rgba(112, 86, 248, 0.12);
  color: var(--color-primary-light);
  border-color: rgba(112, 86, 248, 0.25);
}
.xsender-search.is-on {
  background: rgba(34, 197, 94, 0.08);
  color: #22c55e;
  border-color: rgba(34, 197, 94, 0.3);
}
</style>
