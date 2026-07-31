---
name: summarizer
description: 对长文本生成简洁的中文摘要，提炼核心要点
icon: 📝
modes: [all]
is_global: true
---
# 文本摘要技能

当用户提供大段文本（文章、报告、对话记录）并希望快速了解核心内容时，使用本技能生成要点摘要。

## 使用场景
- 长文档/报告摘要
- 多轮对话要点提炼
- 研报核心观点提取

## 执行方式
调用 `summarize_text(text, max_length)`：
- text: 待摘要的文本
- max_length: 摘要最大字数（默认 200）
