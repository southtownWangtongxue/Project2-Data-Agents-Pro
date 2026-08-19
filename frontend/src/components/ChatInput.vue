<script setup lang="ts">
/**
 * ChatInput.vue — 集成式输入框（参考千问/ChatGLM 设计）
 *
 * 布局：功能标签栏（模式切换）| 输入区 + 联网开关 | 发送按钮
 */
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  loading: boolean
  modelValue?: string        // 当前模式
  webSearch?: boolean        // 联网搜索
}>()

const emit = defineEmits<{
  send: [text: string]
  cancel: []
  'update:modelValue': [value: string]
  'update:webSearch': [value: boolean]
}>()

const inputText = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const isFocused = ref(false)

/* ── 命令面板（阶段3 A1，对齐 Harness / 命令）────────── */
const store = useChatStore()

interface CommandItem {
  name: string
  desc: string
  run: () => void
}

const commands: CommandItem[] = [
  { name: '/goal', desc: '设置会话长期目标（用法: /goal 目标文本）', run: () => {} },
  { name: '/export', desc: '导出当前会话日志 (JSONL)', run: () => store.exportSession() },
  { name: '/clear', desc: '清空当前会话并新建', run: () => store.newSession() },
  { name: '/fork', desc: '分支当前会话为新会话', run: () => store.forkSession() },
  { name: '/help', desc: '查看可用命令', run: () => showHelp() },
]

const showCommands = ref(false)

const filteredCommands = computed(() => {
  const q = inputText.value.trim().toLowerCase()
  if (!q.startsWith('/')) return []
  const kw = q.slice(1).toLowerCase()
  return commands.filter((c) => c.name.toLowerCase().includes('/' + kw) || c.name.includes(kw))
})

function showHelp() {
  const lines = commands.map((c) => `${c.name} — ${c.desc}`).join('\n')
  // 以提示文本形式插入一条系统消息
  const appEl = document.querySelector('#app') as HTMLElement | null
  if (appEl && appEl.__vue_app__) {
    const pinia = appEl.__vue_app__.config.globalProperties.$pinia
    const chat = pinia && pinia._s.get('chat')
    if (chat) {
      chat.messages.push({
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 9),
        role: 'system',
        type: 'text',
        content: `可用命令：\n${lines}`,
      })
    }
  }
}

function runCommand(cmd: CommandItem) {
  if (cmd.name === '/goal') {
    // 保留输入，让用户继续输入目标文本（如 "/goal 分析销售趋势"）
    showCommands.value = false
    nextTick(() => inputRef.value?.focus())
    return
  }
  showCommands.value = false
  inputText.value = ''
  cmd.run()
  nextTick(() => inputRef.value?.focus())
}

/* 模式配置 */
const modes = [
  { key: 'data',   icon: '📊', label: '数据分析', desc: '查询数据库、生成图表' },
  { key: 'report', icon: '📝', label: '研究报告', desc: '深度调研、撰写报告' },
  { key: 'doc',    icon: '📖', label: '文档智读', desc: '解析文档、提取知识' },
  { key: 'task',   icon: '🤖', label: '通用任务', desc: '代码、翻译、日常问答' },
]

const currentMode = computed({
  get: () => props.modelValue || 'data',
  set: (v: string) => emit('update:modelValue', v),
})

const webSearchEnabled = computed({
  get: () => props.webSearch ?? false,
  set: (v: boolean) => emit('update:webSearch', v),
})

/* 模式选择下拉（click 展开，对齐 Harness） */
const showModeMenu = ref(false)

function toggleModeMenu() {
  showModeMenu.value = !showModeMenu.value
}

function selectMode(key: string) {
  currentMode.value = key
  showModeMenu.value = false
  nextTick(() => inputRef.value?.focus())
}

/* 点击外部关闭模式菜单 */
function onDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.mode-selector')) showModeMenu.value = false
}

/* 联网搜索 */
function toggleWebSearch() {
  webSearchEnabled.value = !webSearchEnabled.value
}

/* 自动增高 */
function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

/* 发送 */
function handleSend() {
  const text = inputText.value.trim()
  if (!text || props.loading) return
  emit('send', text)
  inputText.value = ''
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      inputRef.value.focus()
    }
  })
}

/* 快捷键 */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    // 命令面板打开且有匹配命令时，Enter 直接执行第一个命令
    if (showCommands.value && filteredCommands.value.length > 0) {
      const cmd = filteredCommands.value[0]
      // /goal 特殊处理：解析 "/goal 目标文本" 作为会话长期目标
      if (cmd.name === '/goal') {
        const goalText = inputText.value.replace(/^\/goal\s*/i, '').trim()
        if (goalText) {
          store.setSessionGoal(goalText).then((ok) => {
            if (ok) {
              inputText.value = ''
              showCommands.value = false
            }
          })
        }
        return
      }
      runCommand(cmd)
      return
    }
    handleSend()
  }
}

/* 输入变化：更新命令面板显隐 */
function onInput() {
  autoResize()
  showCommands.value = !props.loading && inputText.value.trim().startsWith('/')
}

/* Esc 关闭模式菜单 */
function onDocKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') showModeMenu.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onDocKeydown)
  // 新建/切换会话后（组件通过 :key 重建）自动聚焦，避免首次 Enter 被吞
  nextTick(() => inputRef.value?.focus())
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onDocKeydown)
})
</script>

<template>
  <div class="chat-input-wrapper" :class="{ 'is-focused': isFocused }">
    <!-- 功能标签栏（模式切换） -->
    <div class="input-toolbar">
      <div class="mode-selector">
        <button class="mode-trigger" :class="{ 'is-open': showModeMenu }" @click="toggleModeMenu">
          <span class="mode-trigger-icon">{{ modes.find(m => m.key === currentMode)?.icon }}</span>
          <span class="mode-trigger-label">{{ modes.find(m => m.key === currentMode)?.label }}</span>
          <svg class="mode-trigger-chevron" :class="{ 'is-open': showModeMenu }"
            width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <Transition name="mode-menu">
          <div v-if="showModeMenu" class="mode-menu">
            <div class="mode-menu-header">Agent 预设</div>
            <div
              v-for="m in modes" :key="m.key"
              class="mode-menu-item"
              :class="{ 'is-active': currentMode === m.key }"
              @click="selectMode(m.key)"
            >
              <span class="mode-menu-icon">{{ m.icon }}</span>
              <div class="mode-menu-body">
                <span class="mode-menu-title">{{ m.label }}</span>
                <span class="mode-menu-desc">{{ m.desc }}</span>
              </div>
              <svg v-if="currentMode === m.key" class="mode-menu-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
            </div>
          </div>
        </Transition>
      </div>

      <div class="toolbar-divider"></div>

      <!-- 联网搜索开关 -->
      <button
        class="web-search-btn"
        :class="{ active: webSearchEnabled }"
        @click="toggleWebSearch"
        title="开启后 Agent 可联网搜索最新信息"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/>
          <path d="m21 21-4.3-4.3"/>
          <path d="M11 8v6M8 11h6" stroke-width="1.5" v-if="webSearchEnabled"/>
        </svg>
        <span>联网搜索</span>
      </button>
    </div>

    <!-- 命令面板（/ 命令，阶段3 A1） -->
    <Transition name="cmd-menu">
      <div v-if="showCommands" class="cmd-palette">
        <div class="cmd-palette-header">命令</div>
        <div
          v-for="cmd in filteredCommands" :key="cmd.name"
          class="cmd-item"
          @mousedown.prevent="runCommand(cmd)"
        >
          <span class="cmd-name">{{ cmd.name }}</span>
          <span class="cmd-desc">{{ cmd.desc }}</span>
        </div>
        <div v-if="filteredCommands.length === 0" class="cmd-empty">没有匹配的命令</div>
      </div>
    </Transition>

    <!-- 输入区域 -->
    <div class="input-area">
      <textarea
        ref="inputRef"
        v-model="inputText"
        class="input-textarea"
        placeholder="用自然语言描述您的需求，按 Enter 发送，Shift+Enter 换行，输入 / 查看命令..."
        rows="1"
        @keydown="onKeydown"
        @input="onInput"
        @focus="isFocused = true"
        @blur="isFocused = false"
        :disabled="loading"
      />

      <div class="input-actions">
        <button
          v-if="!loading"
          class="send-btn"
          :class="{ 'can-send': inputText.trim().length > 0 }"
          @click="handleSend"
          :disabled="!inputText.trim()"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
        <button v-else class="cancel-btn" @click="emit('cancel')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <line x1="9" y1="9" x2="15" y2="15"/>
            <line x1="15" y1="9" x2="9" y2="15"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-input-wrapper {
  position: relative;
  margin: 0 var(--space-4) var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  transition: all 0.2s ease;
  overflow: visible;
}
.chat-input-wrapper.is-focused {
  border-color: rgba(99, 102, 241, 0.4);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08), 0 4px 20px rgba(0,0,0,0.15);
}

/* ========== 功能标签栏 ========== */
.input-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) 0;
}

/* 模式选择器 */
.mode-selector {
  position: relative;
}

.mode-trigger {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: var(--font-sans);
}
.mode-trigger:hover,
.mode-trigger.is-open {
  background: var(--color-surface-elevated);
  border-color: rgba(99, 102, 241, 0.3);
  color: var(--color-text-primary);
}

.mode-trigger-icon {
  font-size: 13px;
  line-height: 1;
}
.mode-trigger-label {
  font-weight: 500;
}
.mode-trigger-chevron {
  transition: transform 0.2s ease;
  opacity: 0.5;
  margin-left: 2px;
}
.mode-trigger-chevron.is-open {
  transform: rotate(180deg);
}

/* 模式下拉菜单 */
.mode-menu {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  min-width: 220px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 -8px 32px rgba(0,0,0,0.35), 0 0 0 1px rgba(0,0,0,0.1);
  overflow: hidden;
  z-index: 50;
  padding: var(--space-1) 0;
}

.mode-menu-header {
  padding: var(--space-1) var(--space-3);
  font-size: 11px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.mode-menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  transition: all 0.15s ease;
}
.mode-menu-item:hover {
  background: var(--color-surface-elevated);
}
.mode-menu-item.is-active {
  background: rgba(99, 102, 241, 0.06);
}

.mode-menu-icon {
  font-size: 16px;
  line-height: 1;
  flex-shrink: 0;
}
.mode-menu-body {
  flex: 1;
  min-width: 0;
}
.mode-menu-title {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 1px;
}
.mode-menu-desc {
  display: block;
  font-size: 11px;
  color: var(--color-text-muted);
}
.mode-menu-check {
  flex-shrink: 0;
  margin-left: var(--space-2);
}

/* 过渡动画 */
.mode-menu-enter-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.mode-menu-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}
.mode-menu-enter-from {
  opacity: 0;
  transform: translateY(6px) scale(0.96);
}
.mode-menu-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.96);
}

/* ========== 命令面板（阶段3 A1）========== */
.cmd-palette {
  position: absolute;
  bottom: calc(100% + 8px);
  left: var(--space-3);
  right: var(--space-3);
  max-height: 240px;
  overflow-y: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 -8px 32px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(0, 0, 0, 0.1);
  z-index: 50;
  padding: var(--space-1) 0;
}
.cmd-palette-header {
  padding: var(--space-1) var(--space-3);
  font-size: 11px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.cmd-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  transition: all 0.15s ease;
}
.cmd-item:hover {
  background: var(--color-surface-elevated);
}
.cmd-name {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--color-primary-light);
  flex-shrink: 0;
}
.cmd-desc {
  font-size: 12px;
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cmd-empty {
  padding: var(--space-3);
  font-size: 12px;
  color: var(--color-text-muted);
  text-align: center;
}
.cmd-menu-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.cmd-menu-leave-active { transition: opacity 0.1s ease, transform 0.1s ease; }
.cmd-menu-enter-from { opacity: 0; transform: translateY(6px) scale(0.98); }
.cmd-menu-leave-to { opacity: 0; transform: translateY(6px) scale(0.98); }

/* 分隔线 */
.toolbar-divider {
  width: 1px;
  height: 16px;
  background: var(--color-border);
  margin: 0 2px;
}

/* 联网搜索按钮 */
.web-search-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}
.web-search-btn:hover {
  background: var(--color-surface-elevated);
  color: var(--color-text-secondary);
}
.web-search-btn.active {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.25);
  color: var(--color-primary-light);
}
.web-search-btn svg {
  flex-shrink: 0;
}

/* ========== 输入区域 ========== */
.input-area {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-3);
}

.input-textarea {
  flex: 1;
  min-height: 24px;
  max-height: 200px;
  padding: 8px 0;
  background: transparent;
  border: none;
  outline: none;
  font-size: 15px;
  line-height: 1.5;
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  resize: none;
  overflow-y: auto;
}
.input-textarea::placeholder {
  color: var(--color-text-muted);
  font-size: 14px;
}
.input-textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.input-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding-bottom: 2px;
}

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-lg);
  border: none;
  background: var(--color-surface-elevated);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}
.send-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.15);
  color: var(--color-primary-light);
}
.send-btn.can-send {
  background: linear-gradient(135deg, #6366f1, #818cf8);
  color: white;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.35);
}
.send-btn.can-send:hover {
  background: linear-gradient(135deg, #5558e0, #727aec);
  box-shadow: 0 3px 12px rgba(99, 102, 241, 0.45);
  transform: translateY(-1px);
}
.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.cancel-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
  animation: cancelIn 0.2s ease;
}
@keyframes cancelIn {
  from { opacity: 0; transform: scale(0.8); }
  to { opacity: 1; transform: scale(1); }
}
.cancel-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
}
</style>
