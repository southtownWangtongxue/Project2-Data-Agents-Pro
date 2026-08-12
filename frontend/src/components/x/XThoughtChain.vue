<script setup lang="ts">
/**
 * XThoughtChain.vue — 基于 Ant Design X Vue 的思维链（P5）
 *
 * 官方 API 依据：docs/plans/2026-08-05-ant-design-x-vue-integration.md §2.5
 * - <ThoughtChain :items :collapsible>；ThoughtChainItem 无 children 字段
 * - status: 'pending' | 'success' | 'error'
 *
 * 用法：接收单条 thinking/tool 类消息，渲染为单节点思维链
 * （多条消息聚合会导致与消息流重复，单节点贴合逐条展示场景）。
 */
import { computed } from 'vue'
import { ThoughtChain, type ThoughtChainProps } from 'ant-design-x-vue'
import type { ChatMessage } from '@/stores/chat'

const props = defineProps<{ msg: ChatMessage }>()

/* 工具元信息 -> 可读摘要 */
function toolContent(m: ChatMessage): string {
  const meta = m.toolMeta || {}
  const parts: string[] = []
  if (meta.input) parts.push(`输入: ${String(meta.input)}`)
  if (meta.result) parts.push(`结果: ${String(meta.result)}`)
  if (meta.sql) parts.push(`SQL: ${String(meta.sql)}`)
  if (parts.length) return parts.join('\n')
  if (m.content) return m.content
  return ''
}

/* 单条消息 -> ThoughtChainItem */
const items = computed<NonNullable<ThoughtChainProps['items']>>(() => {
  const m = props.msg
  const title =
    m.type === 'thinking'
      ? `${m.agent || ''} · ${m.phase || '思考中'}`
      : m.toolName || m.agent || '工具'
  const status =
    m.type === 'tool_result' || m.type === 'tool_chain' ? 'success' : 'pending'
  return [
    {
      key: m.id,
      title,
      status: status as 'success' | 'pending',
      content: toolContent(m) || undefined,
    },
  ]
})
</script>

<template>
  <ThoughtChain :items="items" :collapsible="true" size="small" />
</template>
