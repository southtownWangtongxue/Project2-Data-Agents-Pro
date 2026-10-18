/**
 * SQLCard.tsx —— SQL 代码卡
 *
 * 2026-10 重做(需求 6):自绘纯文本 <pre> 改为 Markdown 封装的代码块
 * (highlight.js 语法高亮 + 语言标签 + 一键复制),与正文代码块视觉/行为一致。
 */
import { HighlightedCode } from '@/components/bits/Markdown'
import type { Msg } from '@/sdk/protocol'

export default function SQLCard({ msg }: { msg: Msg }) {
  if (!msg.sql) return null
  return (
    <div className="w-full min-w-0">
      <HighlightedCode code={msg.sql} lang="sql" label="SQL" />
    </div>
  )
}
