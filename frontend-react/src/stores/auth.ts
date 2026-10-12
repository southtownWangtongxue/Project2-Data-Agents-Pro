/**
 * stores/auth.ts —— 认证状态(zustand)
 */
import { create } from 'zustand'
import { api, setToken, getToken } from '@/api/client'

interface AuthState {
  user: { user_name: string; user_type: string; nick_name?: string } | null
  loading: boolean
  login: (userName: string, password: string) => Promise<void>
  logout: () => void
  restore: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: false,
  login: async (userName: string, password: string) => {
    set({ loading: true })
    try {
      const data = await api<{ access_token: string }>('/auth/login', {
        method: 'POST',
        body: { user_name: userName, password },
      })
      setToken(data.access_token)
      const me = await api<{ user_name: string; user_type: string; nick_name?: string }>('/auth/me')
      set({ user: me, loading: false })
    } finally {
      set({ loading: false })
    }
  },
  logout: () => {
    setToken(null)
    set({ user: null })
    window.location.href = '/login'
  },
  restore: async () => {
    if (!getToken()) return
    try {
      const me = await api<{ user_name: string; user_type: string; nick_name?: string }>('/auth/me')
      set({ user: me })
    } catch {
      setToken(null)
    }
  },
}))
