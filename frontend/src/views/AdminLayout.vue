<script setup lang="ts">
/**
 * AdminLayout - 配置中心独立布局
 * 左侧边栏导航 + 右侧内容区
 * 设计风格对标通义千问：深色主题 + 流畅动效
 */
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

/* 侧边栏折叠状态 */
const collapsed = ref(false)

/* 导航菜单配置 */
interface MenuConfig {
  path: string
  label: string
  icon: string
  description: string
}

const menuItems: MenuConfig[] = [
  {
    path: '/admin/llm',
    label: 'LLM 模型',
    icon: 'model',
    description: '管理大语言模型提供商与参数',
  },
  {
    path: '/admin/skills',
    label: 'Skill 技能',
    icon: 'skill',
    description: '控制各模式可用技能开关',
  },
  {
    path: '/admin/mcp',
    label: 'MCP 服务',
    icon: 'mcp',
    description: 'Model Context Protocol 服务器',
  },
  {
    path: '/admin/knowledge',
    label: '知识库',
    icon: 'knowledge',
    description: '文档上传、向量化与语义搜索',
  },
  {
    path: '/admin/schedule',
    label: '定时任务',
    icon: 'schedule',
    description: 'NL2Cron 自然语言定时调度',
  },
]

/* 当前激活的菜单项 */
const activeMenu = computed(() => route.path)

/* 导航跳转 */
function navigateTo(path: string) {
  router.push(path)
}
</script>

<template>
  <div class="admin-layout">
    <!-- 左侧边栏 -->
    <aside class="sidebar" :class="{ collapsed }">
      <!-- 侧边栏头部 -->
      <div class="sidebar-header">
        <div class="sidebar-logo">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <rect width="24" height="24" rx="6" fill="url(#adminLogoGrad)"/>
            <path d="M7 8h10M7 12h7M7 16h9" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
            <defs>
              <linearGradient id="adminLogoGrad" x1="0" y1="0" x2="24" y2="24">
                <stop stop-color="#6366f1"/>
                <stop offset="1" stop-color="#818cf8"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <span v-show="!collapsed" class="sidebar-title">配置中心</span>
        <button class="collapse-btn" @click="collapsed = !collapsed" :title="collapsed ? '展开' : '收起'">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :style="{ transform: collapsed ? 'rotate(180deg)' : '' }">
            <polyline points="15,18 9,12 15,6"/>
          </svg>
        </button>
      </div>

      <!-- 导航菜单 -->
      <nav class="sidebar-nav">
        <div class="nav-section-label" v-show="!collapsed">系统配置</div>
        <button
          v-for="item in menuItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: activeMenu === item.path }"
          :title="collapsed ? item.label : ''"
          @click="navigateTo(item.path)"
        >
          <span class="nav-icon-wrapper">
            <!-- LLM Model Icon -->
            <svg v-if="item.icon === 'model'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
              <polyline points="3.27,6.96 12,12.01 20.73,6.96"/>
              <line x1="12" y1="22.08" x2="12" y2="12"/>
            </svg>
            <!-- Skill Icon -->
            <svg v-else-if="item.icon === 'skill'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13,2 3,14 12,14 11,22 21,10 12,10 13,2"/>
            </svg>
            <!-- MCP Icon -->
            <svg v-else-if="item.icon === 'mcp'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            <!-- Knowledge Icon -->
            <svg v-else-if="item.icon === 'knowledge'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
              <line x1="8" y1="6" x2="16" y2="6"/>
              <line x1="8" y1="10" x2="14" y2="10"/>
            </svg>
            <!-- Schedule Icon -->
            <svg v-else-if="item.icon === 'schedule'" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
          </span>
          <Transition name="fade-slide">
            <span v-show="!collapsed" class="nav-text">{{ item.label }}</span>
          </Transition>
          <!-- 活跃指示器 -->
          <span v-if="activeMenu === item.path && !collapsed" class="active-indicator"></span>
        </button>
      </nav>

      <!-- 侧边栏底部 -->
      <div class="sidebar-footer" v-show="!collapsed">
        <div class="footer-info">
          <span class="status-dot"></span>
          <span>系统运行正常</span>
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <main class="content-area">
      <!-- 页面内容 + 过渡动画 -->
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.admin-layout {
  display: flex;
  height: 100%;
  background-color: var(--color-bg);
}

/* === Sidebar === */
.sidebar {
  width: 240px;
  min-width: 240px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(24, 24, 27, 0.95) 0%, rgba(15, 15, 17, 0.98) 100%);
  border-right: 1px solid var(--color-border);
  transition: all var(--transition-slow);
  overflow: hidden;
}

.sidebar.collapsed {
  width: 64px;
  min-width: 64px;
}

/* Sidebar Header */
.sidebar-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4);
  border-bottom: 1px solid rgba(63, 63, 70, 0.5);
  flex-shrink: 0;
  height: 60px;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  margin-left: auto;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.collapse-btn:hover {
  background-color: rgba(255, 255, 255, 0.08);
  color: var(--color-text-secondary);
}

.collapse-btn svg {
  transition: transform var(--transition-normal);
}

/* Navigation */
.sidebar-nav {
  flex: 1;
  padding: var(--space-3) var(--space-3);
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-1);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  margin-bottom: 2px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  position: relative;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.nav-item:hover {
  background-color: rgba(99, 102, 241, 0.08);
  color: var(--color-text-primary);
}

.nav-item.active {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--color-primary-light);
}

.nav-item .nav-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  transition: background-color var(--transition-fast);
}

.nav-item:hover .nav-icon-wrapper {
  background-color: rgba(99, 102, 241, 0.1);
}

.nav-item.active .nav-icon-wrapper {
  background-color: rgba(99, 102, 241, 0.2);
}

.nav-text {
  flex: 1;
  text-align: left;
}

.active-indicator {
  position: absolute;
  right: 8px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--color-primary-light);
  box-shadow: 0 0 8px rgba(129, 140, 248, 0.6);
  animation: pulse-glow 2s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 1; box-shadow: 0 0 8px rgba(129, 140, 248, 0.6); }
  50% { opacity: 0.7; box-shadow: 0 0 4px rgba(129, 140, 248, 0.3); }
}

/* Sidebar Footer */
.sidebar-footer {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid rgba(63, 63, 70, 0.5);
  flex-shrink: 0;
}

.footer-info {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 12px;
  color: var(--color-text-muted);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--color-success);
  animation: pulse-status 2s ease-in-out infinite;
}

@keyframes pulse-status {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* === Content Area === */
.content-area {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  background-color: var(--color-bg);
  position: relative;
}

/* === Page Transition Animation === */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: all var(--transition-normal);
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(12px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Nav text transition for collapse */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all var(--transition-fast);
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

/* === Scrollbar for sidebar === */
.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: var(--radius-full);
}
</style>
