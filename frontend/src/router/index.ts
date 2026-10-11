import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { ElMessage } from 'element-plus'

/**
 * 从 localStorage 的 JWT 中解析 user_type。
 *
 * 路由配置（redirect）与守卫会在「pinia 安装之前」就被求值，
 * 此时调用 useAuthStore() 会抛 “getActivePinia() was called but there was no
 * active Pinia”（曾导致 /admin 直接空白）。这里直接解析服务端签发的 JWT，
 * 与既有守卫读取 localStorage token 的做法保持一致，且不依赖 store 生命周期。
 */
function getUserTypeFromToken(): string {
  const token = localStorage.getItem('token') || ''
  try {
    const payload = token.split('.')[1]
    if (!payload) return ''
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
    const claims = JSON.parse(atob(padded)) as { user_type?: string }
    return claims.user_type || ''
  } catch {
    return ''
  }
}

/* 是否管理员（user_type=00，与后端 require_admin 判定一致） */
function isAdminUser(): boolean {
  return getUserTypeFromToken() === '00'
}

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
  {
    path: '/admin',
    component: () => import('@/views/AdminLayout.vue'),
    meta: { title: '配置中心', requiresAuth: true },
    // 默认落地页按角色分流，避免非管理员一进入就撞上管理员专属页签
    redirect: () => (isAdminUser() ? '/admin/llm' : '/admin/knowledge'),
    children: [
      {
        path: 'llm',
        name: 'LlmConfig',
        component: () => import('@/views/admin/LlmConfig.vue'),
        meta: { title: 'LLM 模型管理', requiresAdmin: true },
      },
      {
        path: 'skills',
        name: 'SkillConfig',
        component: () => import('@/views/admin/SkillConfig.vue'),
        meta: { title: 'Skill 技能管理', requiresAdmin: true },
      },
      {
        path: 'mcp',
        name: 'McpConfig',
        component: () => import('@/views/admin/McpConfig.vue'),
        meta: { title: 'MCP 服务管理', requiresAdmin: true },
      },
      {
        path: 'knowledge',
        name: 'KnowledgeConfig',
        component: () => import('@/views/admin/KnowledgeConfig.vue'),
        meta: { title: '知识库管理' },
      },
      {
        path: 'schedule',
        name: 'ScheduleConfig',
        component: () => import('@/views/admin/ScheduleConfig.vue'),
        meta: { title: '定时任务管理' },
      },
    ],
  },
  {
    // 兜底路由：未匹配的路径（含已下线的 /chat-x）重定向到对话页，
    // 避免出现「仅剩导航头、内容区全白」的空白页面。
    path: '/:pathMatch(.*)*',
    redirect: '/chat',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/* 全局路由守卫：认证检查 + 管理员校验 + 页面标题设置 */
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

  // 需要管理员权限的页面（配置中心中与后端 require_admin 对齐的页签）。
  // 后端 /config/* 对非管理员返回 403，仅靠页面内降级会表现为「加载失败 + 空列表」，
  // 因此在路由层直接拦截并跳转到对全员开放的知识库页。
  if (to.meta.requiresAdmin) {
    if (!isAdminUser()) {
      ElMessage.warning('该页面仅管理员可访问，已跳转至知识库')
      return next('/admin/knowledge')
    }
  }

  next()
})

export default router
