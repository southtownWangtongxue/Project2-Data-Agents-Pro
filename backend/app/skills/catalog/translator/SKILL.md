---
name: translator
description: 将文本翻译为目标语言，支持中英互译及多语种
icon: 🌍
modes: [all]
is_global: true
---
# 翻译技能

当用户需要将文本翻译为另一种语言（如中文→英文、英文→中文）时使用本技能。

## 使用场景
- 中英互译
- 多语种内容本地化
- 外文资料快速理解

## 执行方式
调用 `translate_text(text, target_lang)`：
- text: 待翻译文本
- target_lang: 目标语言（如 "en" / "中文"）
