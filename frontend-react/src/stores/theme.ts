/**
 * stores/theme.ts —— 主题模式(2026-10-18 定版:只保留深色)
 *
 * 用户要求取消配色切换(dsh 参考只保留深色背景)。Store 保留 mode 字段
 * 以兼容既有读取方(AdminLayout 等),但恒为 dark;light 分支已移除。
 */
import { create } from 'zustand'
import type { ThemeMode } from '@/theme/tokens'

function applyDom() {
  const root = document.documentElement
  root.dataset.theme = 'dark'
  root.classList.add('x-markdown-dark')
  root.classList.remove('x-markdown-light')
}

interface ThemeStore {
  mode: ThemeMode
}

export const useThemeStore = create<ThemeStore>(() => ({
  mode: 'dark',
}))

/** 首屏在 React 挂载前同步一次,避免主题闪烁 */
applyDom()
