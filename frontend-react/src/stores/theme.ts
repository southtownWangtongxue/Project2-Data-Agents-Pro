/**
 * stores/theme.ts —— 主题模式(zustand + localStorage + <html data-theme>)
 * 暗色为默认;x-markdown 的 dark.css / light.css 通过 html 上的 class 切换。
 */
import { create } from 'zustand'
import type { ThemeMode } from '@/theme/tokens'

const STORAGE_KEY = 'uiThemeMode'

function readInitial(): ThemeMode {
  const saved = localStorage.getItem(STORAGE_KEY)
  return saved === 'light' ? 'light' : 'dark'
}

function applyDom(mode: ThemeMode) {
  const root = document.documentElement
  root.dataset.theme = mode
  /* x-markdown 主题样式以 class 作用域,需与 antd 算法保持一致 */
  root.classList.toggle('x-markdown-dark', mode === 'dark')
  root.classList.toggle('x-markdown-light', mode === 'light')
}

interface ThemeStore {
  mode: ThemeMode
  setMode: (m: ThemeMode) => void
  toggle: () => void
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  mode: readInitial(),
  setMode: m => {
    localStorage.setItem(STORAGE_KEY, m)
    applyDom(m)
    set({ mode: m })
  },
  toggle: () => get().setMode(get().mode === 'dark' ? 'light' : 'dark'),
}))

/** 首屏在 React 挂载前同步一次,避免主题闪烁 */
applyDom(readInitial())