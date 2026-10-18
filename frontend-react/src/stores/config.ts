/**
 * stores/config.ts —— 模型/配置中心状态(zustand)
 * LLM provider 列表(含 thinking_mode/capabilities/context_window)、模式默认映射
 */
import { create } from 'zustand'
import { api } from '@/api/client'
import { useChatStore } from './chat'

export interface LlmProvider {
  id: string
  name: string
  model: string
  api_base: string
  api_key_env?: string
  api_key?: string
  enabled: boolean
  is_default: boolean
  key_mode: string
  temperature: number
  max_tokens: number
  /* 上下文窗口(tokens):读数条「上下文已用」的分母,模型选择器/配置中心可配 */
  context_window?: number
  /* 思考模式开关(全模态参数体系,admin 配置) */
  thinking_mode?: boolean
  capabilities?: { tools?: boolean; image_input?: boolean; thinking?: boolean }
  params?: {
    top_p?: number
    presence_penalty?: number
    frequency_penalty?: number
    reasoning_effort?: string
    seed?: number | null
  }
}

/** 运行时参数补丁(模型选择器内联配置用) */
export interface ProviderRuntimePatch {
  context_window?: number
  reasoning_effort?: string
}

interface ConfigStore {
  providers: LlmProvider[]
  modeDefaults: Record<string, string>
  loaded: boolean
  loadProviders: () => Promise<void>
  /** 当前所选模型是否具备思考能力(供前端「思考模式」开关禁用判断) */
  syncThinkingMode: (modelId: string) => void
  /** 更新 provider 的上下文窗口 / 思考强度(写入 llm_providers.json) */
  updateProviderRuntime: (id: string, patch: ProviderRuntimePatch) => Promise<void>
}

export const useConfigStore = create<ConfigStore>((set, get) => ({
  providers: [],
  modeDefaults: {},
  loaded: false,

  loadProviders: async () => {
    try {
      const data = await api<{ providers: LlmProvider[]; mode_defaults: Record<string, string> }>('/config/llm')
      set({ providers: data.providers || [], modeDefaults: data.mode_defaults || {}, loaded: true })
      /* 加载后同步上下文窗口:当前所选模型 > 默认模型(读数条分母联动) */
      const providers = data.providers || []
      const chat = useChatStore.getState()
      const active = providers.find(p => p.id === chat.model) || providers.find(p => p.is_default)
      if (active?.context_window) {
        useChatStore.getState().setContextWindow(active.context_window!)
      }
    } catch (e) {
      console.error('[config] 加载模型列表失败:', e)
    }
  },

  syncThinkingMode: (modelId: string) => {
    const p = get().providers.find(x => x.id === modelId)
    /* 能力派生:provider 未声明时按支持处理(与后端 _thinking_capable 的
       Qwen 家族判定互补,前端只做禁用提示,最终以后端注入为准) */
    const capable = p?.thinking_mode ?? p?.capabilities?.thinking ?? true
    useChatStore.setState({ thinkingCapable: capable })
  },

  updateProviderRuntime: async (id, patch) => {
    await api(`/config/llm/${encodeURIComponent(id)}/runtime`, { method: 'PATCH', body: patch })
    set(s => ({
      providers: s.providers.map(p => {
        if (p.id !== id) return p
        const next: LlmProvider = { ...p }
        if (patch.context_window !== undefined) next.context_window = patch.context_window
        if (patch.reasoning_effort !== undefined) {
          next.params = { ...(p.params || {}), reasoning_effort: patch.reasoning_effort }
        }
        return next
      }),
    }))
    /* 上下文窗口变化后,读数条「上下文已用」的分母随之联动(下一次对话生效) */
    if (patch.context_window !== undefined) {
      const current = useChatStore.getState().model
      if (current === id) {
        useChatStore.setState(s => ({ contextUsage: { ...s.contextUsage, window: patch.context_window! } }))
      }
    }
  },
}))
