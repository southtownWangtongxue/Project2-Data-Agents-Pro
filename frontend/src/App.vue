<script setup lang="ts">
/**
 * App 根组件
 * 采用全屏 Flex 布局：顶部标题栏（含导航链接 + 用户信息）+ 中间内容区（路由页面）
 * 设计风格：深色主题 + Apple 极简美学
 */
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

/* 构建导航项，active 根据当前路由计算 */
interface NavItem {
  path: string
  label: string
  icon: string
}

const authNavItems: NavItem[] = [
  { path: '/', label: '首页', icon: 'home' },
  { path: '/chat', label: '智能对话', icon: 'chat' },
  { path: '/chat-x', label: 'AI 对话 (X)', icon: 'chatx' },
  { path: '/approval', label: '审批管理', icon: 'approval' },
  { path: '/admin', label: '配置中心', icon: 'admin' },
]

/* 退出登录 */
function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-container">
    <!-- 顶部标题栏 -->
    <header class="app-header">
      <div class="header-left">
        <div class="logo">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <rect width="28" height="28" rx="6" fill="url(#logoGradient)"/>
            <path d="M8 10h12M8 14h8M8 18h10" stroke="white" stroke-width="2" stroke-linecap="round"/>
            <defs>
              <linearGradient id="logoGradient" x1="0" y1="0" x2="28" y2="28">
                <stop stop-color="#6366f1"/>
                <stop offset="1" stop-color="#818cf8"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h1 class="app-title">DataAgent Pro</h1>
      </div>

      <nav v-if="auth.isLoggedIn" class="app-nav">
        <router-link
          v-for="item in authNavItems"
          :key="item.path"
          :to="item.path"
          class="nav-link"
          :class="{ active: item.path === '/admin' ? route.path.startsWith('/admin') : route.path === item.path }"
        >
          <span class="nav-icon">
            <svg v-if="item.icon === 'home'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
              <polyline points="9,22 9,12 15,12 15,22"/>
            </svg>
            <svg v-else-if="item.icon === 'chat'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <svg v-else-if="item.icon === 'chatx'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2a7 7 0 0 0-7 7c0 2.4 1.2 4.5 3 5.7V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.3c1.8-1.2 3-3.3 3-5.7a7 7 0 0 0-7-7z"/>
              <circle cx="9" cy="9" r="1"/><circle cx="15" cy="9" r="1"/>
              <path d="M9.5 12.5a2.5 2.5 0 0 0 5 0"/>
            </svg>
            <svg v-else-if="item.icon === 'approval'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M9 11l3 3L22 4"/>
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
            </svg>
            <svg v-else-if="item.icon === 'admin'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>

      <div v-if="auth.isLoggedIn" class="header-right">
        <span class="user-info">
          <span class="user-avatar">{{ (auth.user?.nick_name || auth.user?.user_name || 'U')[0].toUpperCase() }}</span>
          <span class="user-name">{{ auth.user?.nick_name || auth.user?.user_name }}</span>
        </span>
        <button class="icon-btn" title="退出登录" @click="handleLogout">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16,17 21,12 16,7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </button>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style>
/* === Import Design System === */
@import './styles/design-system.css';

/* === Global Reset === */
html, body, #app {
  height: 100%;
  width: 100%;
  overflow: hidden;
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.app-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background-color: var(--color-bg);
}

/* === Header === */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 var(--space-6);
  background-color: rgba(24, 24, 27, 0.8);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.logo {
  display: flex;
  align-items: center;
  justify-content: center;
}

.app-title {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--color-text-primary), var(--color-text-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* === Navigation === */
.app-nav {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.nav-link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: all var(--transition-fast);
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.7;
  transition: opacity var(--transition-fast);
}

.nav-label {
  transition: color var(--transition-fast);
}

.nav-link:hover {
  background-color: rgba(99, 102, 241, 0.1);
  color: var(--color-text-primary);
}

.nav-link:hover .nav-icon {
  opacity: 1;
}

.nav-link.active {
  background-color: rgba(99, 102, 241, 0.15);
  color: var(--color-primary-light);
}

.nav-link.active .nav-icon {
  opacity: 1;
}

/* === Header Right === */
.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  background-color: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.15);
}

.user-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark));
  color: white;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: var(--radius-md);
  background-color: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.icon-btn:hover {
  background-color: rgba(255, 255, 255, 0.05);
  color: var(--color-text-primary);
}

/* === Main Content === */
.app-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background-color: var(--color-bg);
}
</style>
