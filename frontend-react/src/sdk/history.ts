/**
 * sdk/history.ts —— 历史会话投影消息 → 领域 Msg 映射（纯函数，可单测）
 *
 * 后端 get_session_messages 的 messages 来源：
 *   1. 事件溯源投影（_project）：user_message/sql/result/analysis/chart/error/
 *      tool_chain/thinking/reasoning（2026-10 新增后两类，修复重启后思考内容丢失）
 *   2. Redis checkpoint 回退：sql/result/analysis/chart/error/text
 *   3. 节点题兜底：text
 *
 * 映射规则（与 sdk/reducer.ts 的实时事件语义对齐，保证历史与直播一致）：
 *   - tool_chain → kind 'tool'（toolPhase='done'，collapsed=true）
 *   - thinking   → kind 'thinking'（agent/phase/content，collapsed=false）
 *   - reasoning  → kind 'reasoning'（content，collapsed=true）
 *   - sql/result/chart/error/text → 同名 kind
 *   - 未知类型 → text 兜底，不抛错（协议只增，旧后端兼容）
 */
import type { Msg } from './protocol'

/** 后端投影消息的原始形态（字段均为可选，按 type 分发） */
export interface ProjectedMessage {
  role?: string
  type?: string
  content?: string
  sql?: string
  data?: any[]
  columns?: string[]
  chartConfig?: Record<string, unknown>
  /* tool_chain */
  toolName?: string
  toolMeta?: Record<string, unknown>
  collapsed?: boolean
  /* thinking */
  agent?: string
  phase?: string
  /* 轮次标记(多轮对话节点切换;旧数据无此字段) */
  turn_index?: number
}

let _seq = 0
function msgId(): string {
  _seq += 1
  return `h_${Date.now().toString(36)}_${_seq}`
}

/** 单条投影消息 → 领域 Msg；无法识别时返回 null（由调用方决定兜底） */
export function mapProjectedMessage(m: ProjectedMessage): Msg {
  const base: Msg = {
    id: msgId(),
    role: m.role === 'user' ? 'user' : 'assistant',
    kind: 'text',
    content: m.content,
    /* 轮次(旧数据无) —— 供 TurnNavigator 按轮次过滤渲染 */
    turnIndex: typeof m.turn_index === 'number' ? m.turn_index : undefined,
  }
  switch (m.type) {
    case 'sql':
      return { ...base, kind: 'sql', sql: m.sql }
    case 'result':
      return { ...base, kind: 'result', data: m.data || [], columns: m.columns || [] }
    case 'chart':
      return { ...base, kind: 'chart', chartConfig: m.chartConfig }
    case 'error':
      return { ...base, kind: 'error' }
    case 'tool_chain':
      return {
        ...base,
        role: 'system',
        kind: 'tool',
        toolName: m.toolName || '工具',
        toolPhase: 'done',
        toolMeta: m.toolMeta || undefined,
        collapsed: m.collapsed ?? true,
      }
    case 'thinking':
      return {
        ...base,
        role: 'system',
        kind: 'thinking',
        agent: m.agent,
        phase: m.phase,
        content: m.content || '',
        collapsed: m.collapsed ?? false,
      }
    case 'reasoning':
      return {
        ...base,
        kind: 'reasoning',
        content: m.content || '',
        collapsed: m.collapsed ?? true,
      }
    case 'text':
    default:
      /* 未知类型保持 text 兜底（协议只增，旧后端无 thinking/reasoning 投影） */
      return base
  }
}

/** 批量映射（顺序保持后端投影顺序）
 *
 * 2026-10-18:harnes 的 reasoning 是流式增量、事件溯源逐 chunk 落库,
 * 投影回来是 N 条碎片(实测一次对话 72 条 → 72 张「思考过程 · 2 字」卡)。
 * 这里把**相邻**的 reasoning 片段合并成一条,与实时 reducer 的累加语义对齐;
 * 顺带丢弃空 content 的碎片。
 */
export function mapProjectedMessages(list: ProjectedMessage[] | undefined | null): Msg[] {
  const out: Msg[] = []
  for (const m of (list || []).map(mapProjectedMessage)) {
    if (m.kind === 'reasoning') {
      const text = m.content || ''
      const last = out[out.length - 1]
      if (last && last.kind === 'reasoning') {
        last.content = (last.content || '') + text
        continue
      }
      if (!text) continue  /* 空碎片不单独成卡 */
      m.content = text
    }
    out.push(m)
  }
  return out
}
