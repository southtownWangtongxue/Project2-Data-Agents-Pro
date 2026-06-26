import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/* 路由配置 */
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { title: '首页', requiresAuth: true },
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/Chat.vue'),
    meta: { title: '智能对话', requiresAuth: true },
  },
  {
    path: '/approval',
    name: 'Approval',
    component: () => import('@/views/Approval.vue'),
    meta: { title: '审批管理', requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/* 全局路由守卫：认证检查 + 页面标题设置 */
router.beforeEach((to, _from, next) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} - DataAgent Pro` : 'DataAgent Pro'

  // 登录页：已登录则跳转对话页
  if (to.path === '/login') {
    const token = localStorage.getItem('token')
    if (token) {
      return next('/chat')
    }
    return next()
  }

  // 需要认证的页面
  if (to.meta.requiresAuth) {
    const token = localStorage.getItem('token')
    if (!token) {
      return next('/login')
    }
  }

  next()
})

export default router
