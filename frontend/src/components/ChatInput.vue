<script setup lang="ts">
/**
 * ChatInput.vue (Phase E.6) — 底部输入区组件
 *
 * 功能：
 *   - 自适应高度的 textarea
 *   - Enter 发送 / Shift+Enter 换行
 *   - 发送按钮（loading 状态下显示 spinner）
 *   - 底部提示文字
 */
import { ref } from 'vue'

const props = defineProps<{
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'cancel'): void
}>()

const inputText = ref('')

function handleSend() {
  const text = inputText.value.trim()
  if (!text || props.loading) return
  emit('send', text)
  inputText.value = ''
}

function handleStop() {
  emit('cancel')
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (props.loading) return
    handleSend()
  }
}
</script>

<template>
  <footer class="chat-input-area">
    <div class="input-wrapper">
      <div class="input-container">
        <textarea
          v-model="inputText"
          class="input-field"
          placeholder="输入您的问题，按 Enter 发送..."
          rows="1"
          @keydown="handleKeydown"
        ></textarea>
        <!-- 加载中：显示停止按钮 -->
        <button
          v-if="loading"
          class="stop-btn"
          title="停止生成"
          @click="handleStop"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <rect x="4" y="4" width="16" height="16" rx="2"/>
          </svg>
        </button>
        <!-- 正常：发送按钮 -->
        <button
          v-else
          class="send-btn"
          :disabled="!inputText.trim()"
          @click="handleSend"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <p class="input-hint">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        Shift + Enter 换行 · 支持自然语言查询
      </p>
    </div>
  </footer>
</template>

<style scoped>
.chat-input-area {
  flex-shrink: 0;
  padding: var(--space-4) var(--space-6) var(--space-6);
  background: linear-gradient(to top, var(--color-bg) 0%, transparent 10%);
}

.input-wrapper {
  max-width: 800px;
  margin: 0 auto;
}

.input-container {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  transition: all var(--transition-fast);
}

.input-container:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.input-field {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  outline: none;
  font-family: var(--font-sans);
  font-size: 15px;
  color: var(--color-text-primary);
  resize: none;
  line-height: 1.5;
  max-height: 120px;
}

.input-field::placeholder {
  color: var(--color-text-muted);
}

.input-field:disabled {
  opacity: 0.6;
}

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
  border: none;
  border-radius: var(--radius-lg);
  color: white;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 停止按钮 */
.stop-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--color-error);
  border: none;
  border-radius: var(--radius-lg);
  color: white;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.stop-btn:hover {
  background: #dc2626;
  box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);
  transform: scale(1.05);
}

.input-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
  font-size: 12px;
  color: var(--color-text-muted);
}
</style>
