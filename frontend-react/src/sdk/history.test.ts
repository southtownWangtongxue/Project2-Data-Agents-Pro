/**
 * sdk/history.test.ts —— 历史投影映射单测
 * 覆盖 2026-10 修复的 tool_chain/thinking/reasoning 映射与未知类型兜底。
 */
import { describe, expect, it } from 'vitest'
import { mapProjectedMessage, mapProjectedMessages } from './history'

describe('mapProjectedMessage', () => {
  it('tool_chain → tool 消息（done + collapsed，历史工具卡可见）', () => {
    const msg = mapProjectedMessage({
      role: 'system',
      type: 'tool_chain',
      toolName: 'run_sql',
      toolMeta: { result: '查询成功 · 12 行' },
      collapsed: true,
    })
    expect(msg.kind).toBe('tool')
    expect(msg.role).toBe('system')
    expect(msg.toolName).toBe('run_sql')
    expect(msg.toolPhase).toBe('done')
    expect(msg.toolMeta).toEqual({ result: '查询成功 · 12 行' })
    expect(msg.collapsed).toBe(true)
  })

  it('thinking → thinking 消息（agent/phase/content，默认展开态=false）', () => {
    const msg = mapProjectedMessage({
      role: 'system',
      type: 'thinking',
      agent: 'sql_coder',
      phase: 'generating',
      content: '正在生成SQL查询...',
    })
    expect(msg.kind).toBe('thinking')
    expect(msg.agent).toBe('sql_coder')
    expect(msg.phase).toBe('generating')
    expect(msg.content).toBe('正在生成SQL查询...')
    expect(msg.collapsed).toBe(false)
  })

  it('reasoning → reasoning 消息（collapsed 默认 true）', () => {
    const msg = mapProjectedMessage({
      role: 'assistant',
      type: 'reasoning',
      content: '先统计各表行数……',
    })
    expect(msg.kind).toBe('reasoning')
    expect(msg.role).toBe('assistant')
    expect(msg.content).toBe('先统计各表行数……')
    expect(msg.collapsed).toBe(true)
  })

  it('sql/result/chart/error/text 映射为同名 kind', () => {
    expect(mapProjectedMessage({ role: 'assistant', type: 'sql', sql: 'SELECT 1' }).kind).toBe('sql')
    const result = mapProjectedMessage({ role: 'assistant', type: 'result', data: [{ a: 1 }], columns: ['a'] })
    expect(result.kind).toBe('result')
    expect(result.data).toEqual([{ a: 1 }])
    expect(result.columns).toEqual(['a'])
    expect(mapProjectedMessage({ role: 'assistant', type: 'chart', chartConfig: { x: 1 } }).chartConfig).toEqual({ x: 1 })
    expect(mapProjectedMessage({ role: 'assistant', type: 'error', content: 'boom' }).kind).toBe('error')
    expect(mapProjectedMessage({ role: 'user', type: 'text', content: 'hi' }).kind).toBe('text')
  })

  it('未知类型 → text 兜底，不抛错（旧后端无新投影类型时兼容）', () => {
    const msg = mapProjectedMessage({ role: 'assistant', type: 'some_future_type', content: 'x' })
    expect(msg.kind).toBe('text')
    expect(msg.content).toBe('x')
  })

  it('user 消息 role 归一化；其余缺省按 assistant', () => {
    expect(mapProjectedMessage({ role: 'user', type: 'text', content: 'q' }).role).toBe('user')
    expect(mapProjectedMessage({ type: 'text', content: 'a' }).role).toBe('assistant')
  })

  it('批量映射保持顺序', () => {
    const list = mapProjectedMessages([
      { role: 'user', type: 'text', content: 'q' },
      { role: 'system', type: 'tool_chain', toolName: 'run_sql' },
      { role: 'system', type: 'thinking', agent: 'analyst', phase: 'analyzing', content: 't' },
      { role: 'assistant', type: 'text', content: 'a' },
    ])
    expect(list.map(m => m.kind)).toEqual(['text', 'tool', 'thinking', 'text'])
    expect(list.every((m, i) => typeof m.id === 'string' && m.id.length > 0)).toBe(true)
    expect(mapProjectedMessages(undefined)).toEqual([])
  })
})
