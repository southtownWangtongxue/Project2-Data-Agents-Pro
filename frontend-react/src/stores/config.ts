/**
 * stores/config.ts —— 模型/配置中心状态(zustand)
 * LLM provider 列表(含 thinking_mode/capabilities 预览)、模式默认映射
 */
import { create } from 'zustand'
import { api } from '@/api/client'
import { useChatStore } from './chat'

export interface LlmProvider {
  id: string
  name: string
  model: string
  api_base: string
  enabled: boolean
  is_default: boolean
  key_mode: string
  temperature: number
  max_tokens: number
  /* 思考模式开关(全模态参数体系,admin 配置) */
  thinking_mode?: boolean
  capabilities?: { tools?: boolean; image_input?: boolean; thinking?: boolean }
  params?: Record<string, unknown>
}

interface ConfigStore {
  providers: LlmProvider[]
  modeDefaults: Record<string, string>
  loaded: boolean
  loadProviders: () => Promise<void>
  /** 当前所选模型是否开启思考模式(前端 ReasoningBlock 展示开关) */
  syncThinkingMode: (modelId: string) => void
}

export const useConfigStore = create<ConfigStore>((set, get) => ({
  providers: [],
  modeDefaults: {},
  loaded: false,

  loadProviders: async () => {
    try {
      const data = await api<{ providers: LlmProvider[]; mode_defaults: Record<string, string> }>('/config/llm')
      set({ providers: data.providers || [], modeDefaults: data.mode_defaults || {}, loaded: true })
    } catch (e) {
      console.error('[config] 加载模型列表失败:', e)
    }
  },

  syncThinkingMode: (modelId: string) => {
    const p = get().providers.find(x => x.id === modelId)
    const enabled = p?.thinking_mode ?? p?.capabilities?.thinking ?? true
    useChatStore.setState({ thinkingModeEnabled: enabled })
  },
}))
