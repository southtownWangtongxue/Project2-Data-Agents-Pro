/**
 * bits/Markdown.tsx —— 全站 Markdown 渲染封装(基于 @ant-design/x-markdown)
 *
 * 2026-10 重做(问题5):正文气泡 / 思考卡 / 工具卡统一走本组件,提供:
 * - 代码块:头栏(语言标签 + 一键复制)+ highlight.js 语法高亮(驾驶舱暗色配色)
 * - 表格:外层横向滚动,防撑破气泡
 * - 外链:新窗口打开(openLinksInNewTab)
 * - 安全:escapeRawHtml 转义原始 HTML(防 XSS),内置 DOMPurify 双保险
 * - 流式:streaming 配置透传;流式中跳过高亮(未闭合语法),完成后高亮终态
 *
 * 遵循 x-markdown 开发规则:components 映射为 module 级稳定对象,避免内联
 * 对象导致重渲染与打字动画重置。
 */
import { useMemo, useState, type ComponentType } from 'react'
import { XMarkdown, type ComponentProps as XComponentProps } from '@ant-design/x-markdown'
import hljs from 'highlight.js/lib/core'
import { format as formatSql } from 'sql-formatter'
import Icon from '@/components/bits/Icon'
import SpotlightCard from '@/components/bits/reactbits/SpotlightCard'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'
import java from 'highlight.js/lib/languages/java'
import go from 'highlight.js/lib/languages/go'
import plaintext from 'highlight.js/lib/languages/plaintext'

/* 按需注册常用语言(整包不入库,仅注册清单内语言) */
const LANGUAGES: Array<[string, Parameters<typeof hljs.registerLanguage>[1]]> = [
  ['javascript', javascript],
  ['typescript', typescript],
  ['python', python],
  ['sql', sql],
  ['json', json],
  ['bash', bash],
  ['xml', xml],
  ['css', css],
  ['markdown', markdown],
  ['yaml', yaml],
  ['java', java],
  ['go', go],
  ['plaintext', plaintext],
]
for (const [name, def] of LANGUAGES) {
  if (!hljs.getLanguage(name)) hljs.registerLanguage(name, def)
}

/** 从 htmlparser2 domNode 递归提取纯文本(代码块内容) */
function extractText(node: unknown): string {
  if (node == null) return ''
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (typeof node === 'object') {
    const n = node as { data?: unknown; children?: unknown }
    if (typeof n.data === 'string') return n.data
    if (n.children) return extractText(n.children)
  }
  return ''
}

/** 代码块:头栏(语言 + 复制)+ 高亮;流式中仅纯文本,完成后高亮 */
function CodeBlock({ code, lang, streamStatus, label }: { code: string; lang?: string; streamStatus: 'loading' | 'done'; label?: string }) {
  const [copied, setCopied] = useState(false)

  const highlighted = useMemo(() => {
    if (streamStatus !== 'done' || !code) return null
    /* SQL 自动格式化(需求:sql 内容做自动格式化和换行):
       高亮前先 pretty-print(关键字大写 + 子句换行缩进),解析失败用原文 */
    let source = code
    if (lang === 'sql') {
      try {
        source = formatSql(code, { language: 'sql', keywordCase: 'upper', linesBetweenQueries: 1 })
      } catch (e) {
        console.error('[Markdown] SQL 格式化失败,使用原文:', e)
      }
    }
    try {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(source, { language: lang }).value
      }
      return hljs.highlightAuto(source).value
    } catch (e) {
      console.error('[Markdown] 代码高亮失败:', e)
      return null
    }
  }, [code, lang, streamStatus])

  const copy = () => {
    navigator.clipboard
      .writeText(code)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      })
      .catch(e => console.error('[Markdown] 复制失败:', e))
  }

  return (
    <SpotlightCard
      className="md-codeblock my-2"
      spotlightColor="#8B6FFF"
      intensity={0.14}
      spotlightSize={320}
      proximity={90}
      borderGlow={0.55}
      style={{
        ['--spotlight-card-surface' as string]: 'var(--code-bg)',
        ['--spotlight-card-border' as string]: 'var(--border)',
        borderRadius: 10,
      }}
    >
      <div
        className="flex items-center justify-between px-3 py-1.5 text-[11px]"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--cockpit-800)' }}
      >
        <span className="mono text-[var(--text-3)]">{label || lang || 'code'}</span>
        <button
          type="button"
          onClick={copy}
          className="mono cursor-pointer border-none bg-transparent transition-colors hover:text-[var(--text-1)] flex items-center gap-1"
          style={{ color: copied ? 'var(--success)' : 'var(--text-3)' }}
        >
          <Icon name={copied ? 'check' : 'copy'} size={11} />
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="m-0 p-3 overflow-x-auto text-[12px] leading-relaxed" style={{ background: 'transparent' }}>
        {highlighted ? (
          <code className="hljs" dangerouslySetInnerHTML={{ __html: highlighted }} />
        ) : (
          <code className="mono" style={{ color: 'var(--text-2)' }}>{code}</code>
        )}
      </pre>
    </SpotlightCard>
  )
}

/** 独立代码块(SQLCard 等富卡复用):终态高亮 + 语言标签 */
export function HighlightedCode({ code, lang, label }: { code: string; lang: string; label?: string }) {
  return <CodeBlock code={code} lang={lang} streamStatus="done" label={label} />
}

/** module 级稳定 components 映射(x-markdown 规则:避免内联对象) */
const MD_COMPONENTS: Record<string, ComponentType<XComponentProps>> = {
  code: function MarkdownCode({ domNode, streamStatus, lang, block }: XComponentProps) {
    const code = extractText(domNode)
    if (!block) {
      /* 行内代码:轻量徽章,不走头栏 */
      return <code className="mono text-[0.92em] px-1.5 py-0.5 rounded" style={{ background: 'var(--cockpit-700)', color: 'var(--brand-light)' }}>{code}</code>
    }
    return <CodeBlock code={code} lang={lang} streamStatus={streamStatus} />
  },
  table: function MarkdownTable({ children }: XComponentProps) {
    /* 表格外层横向滚动,防宽表撑破气泡 */
    return <div className="md-table-wrap my-2 overflow-x-auto" style={{ border: '1px solid var(--border)', borderRadius: 10 }}>{children}</div>
  },
}

export interface MarkdownProps {
  content: string
  /** 流式配置(透传 XMarkdown.streaming) */
  streaming?: {
    hasNextChunk?: boolean
    enableAnimation?: boolean
    tail?: boolean | { content?: string }
    animationConfig?: { fadeDuration?: number; easing?: string }
  }
  className?: string
}

export default function Markdown({ content, streaming, className }: MarkdownProps) {
  return (
    <XMarkdown
      className={className}
      content={content}
      components={MD_COMPONENTS}
      streaming={streaming}
      openLinksInNewTab
      escapeRawHtml
    />
  )
}
