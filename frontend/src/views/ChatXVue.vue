<script setup lang="ts">
/**
 * ChatXVue.vue — 基于 Ant Design X Vue 的 AI 对话页（Ultramodern 风格重构）
 *
 * 布局参考官方样板间：
 * - https://x.ant.design/docs/playground/ultramodern-cn?theme=dark（紫色品牌色、留白）
 * - https://antd-design-x-vue.netlify.app/playground/independent.html（三段式结构）
 * - 左侧 Sider 280px：Logo + 新建会话 + Conversations（顶部 AppHeader 已有用户信息，侧栏不再重复）
 * - 右侧主区：ChatList 居中（max-width 700px）+ Sender 输入区（居中 700px，模式移入 Header 面板）
 * - 空态：Welcome + Prompts 建议
 *
 * 数据层完全复用 stores/chat.ts（含 currentModel 模型路由）与 composables/useSSE.ts。
 */
import { onMounted } from 'vue'
import { XProvider } from 'ant-design-x-vue'
import { theme } from 'ant-design-vue'
import { useChatStore } from '@/stores/chat'
import XConversations from '@/components/x/XConversations.vue'
import XBubbleList from '@/components/x/XBubbleList.vue'
import XSender from '@/components/x/XSender.vue'
import XWelcome from '@/components/x/XWelcome.vue'

const store = useChatStore()

/* XProvider 主题：暗色算法 + 紫色品牌色 token
 * 关键：不传 darkAlgorithm 时，ant-design-x-vue 内部组件使用 antdv 默认浅色 token
 * （白底黑字），与页面深色背景冲突 → 必须显式启用暗色算法。 */
const xTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#7056f8',
    colorInfo: '#7056f8',
    colorBgBase: '#0a0a0a',
    colorBgContainer: '#0f0f11',
    colorBgElevated: '#1a1a1d',
    colorText: 'rgba(255, 255, 255, 0.88)',
    colorTextSecondary: 'rgba(255, 255, 255, 0.65)',
    colorBorder: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 8,
  },
}

onMounted(() => {
  store.loadSessions()
  store.loadSuggestions()
})
</script>

<template>
  <div class="chatx-root">
    <XProvider :theme="xTheme">
      <div class="chatx-layout">
        <!-- ── 左侧 Sider（280px，顶部 AppHeader 已含用户信息，此处不重复）── -->
        <aside class="chatx-sider">
          <div class="chatx-logo">
            <svg width="26" height="26" viewBox="0 0 28 28" fill="none">
              <rect width="28" height="28" rx="6" fill="url(#xLogoGradient)"/>
              <path d="M8 10h12M8 14h8M8 18h10" stroke="white" stroke-width="2" stroke-linecap="round"/>
              <defs>
                <linearGradient id="xLogoGradient" x1="0" y1="0" x2="28" y2="28">
                  <stop stop-color="#7056f8"/><stop offset="1" stop-color="#8b6fff"/>
                </linearGradient>
              </defs>
            </svg>
            <span class="chatx-logo-title">AI 对话</span>
          </div>

          <!-- 新建会话 -->
          <button class="chatx-new" @click="store.newSession()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>新建会话</span>
          </button>

          <XConversations />
        </aside>

        <!-- ── 右侧主区 ── -->
        <main class="chatx-main">
          <XWelcome v-if="store.messages.length === 0 && !store.isLoading" />
          <XBubbleList v-else />
          <XSender />
        </main>
      </div>
    </XProvider>
  </div>
</template>

<style scoped>
.chatx-root {
  height: 100%;
  max-height: calc(100vh - 64px);
  overflow: hidden;
  background-color: var(--color-bg);
}
.chatx-layout {
  display: flex;
  height: 100%;
}

/* ── 左侧 Sider ── */
.chatx-sider {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 0 12px;
  border-right: 1px solid var(--color-border);
  background: rgba(20, 20, 22, 0.6);
  backdrop-filter: blur(20px);
}
.chatx-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px 12px 12px;
  flex-shrink: 0;
}
.chatx-logo-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  letter-spacing: -0.01em;
}
/* 新建会话按钮（紫色主题） */
.chatx-new {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 40px;
  margin: 0 4px 12px;
  background: rgba(112, 86, 248, 0.1);
  border: 1px solid rgba(112, 86, 248, 0.25);
  border-radius: 12px;
  color: var(--color-primary-light);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}
.chatx-new:hover {
  background: rgba(112, 86, 248, 0.2);
  border-color: rgba(112, 86, 248, 0.4);
}

/* ── 右侧主区 ── */
.chatx-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
</style>
