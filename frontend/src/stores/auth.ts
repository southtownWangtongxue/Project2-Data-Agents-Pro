import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '@/api/client'
import type { AxiosError } from 'axios'

/* 用户信息 */
export interface UserInfo {
  user_name: string
  nick_name: string
  user_type: string
}

/* 登录响应 */
interface LoginResponse {
  access_token: string
  user_name: string
  nick_name: string
  user_type: string
}

export const useAuthStore = defineStore('auth', () => {
  /* 当前用户 */
  const user = ref<UserInfo | null>(null)

  /* JWT Token（同步到 localStorage） */
  const token = ref<string>(localStorage.getItem('token') || '')

  /* 是否已登录 */
  const isLoggedIn = computed(() => !!token.value && !!user.value)

  /* 是否 Admin */
  const isAdmin = computed(() => user.value?.user_type === '00')

  /**
   * 登录 —— 调用后端 /auth/login，保存 token 和用户信息
   */
  async function login(userName: string, password: string): Promise<void> {
    const data = await apiClient.post('/auth/login', {
      user_name: userName,
      password,
    }) as LoginResponse

    token.value = data.access_token
    user.value = {
      user_name: data.user_name,
      nick_name: data.nick_name,
      user_type: data.user_type,
    }

    localStorage.setItem('token', data.access_token)
  }

  /**
   * 从 token 中恢复用户信息
   */
  async function fetchUser(): Promise<void> {
    if (!token.value) return

    try {
      const data = await apiClient.get('/auth/me') as UserInfo
      user.value = data
    } catch {
      logout()
    }
  }

  /**
   * 退出登录
   */
  function logout(): void {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  return {
    user,
    token,
    isLoggedIn,
    isAdmin,
    login,
    fetchUser,
    logout,
  }
})
