---
name: deepseek-harness 源码研读笔记落盘
overview: 将 DeepSeek Harness 源码研读结论（核心工作机制、界面交互设计、web 布局动效、与前后端分离架构对比）整理为一份结构化 markdown 笔记，落盘到项目 docs 目录。
todos:
  - id: write-notes-doc
    content: 撰写并落盘 docs/reference/deepseek-harness-notes.md 结构化研读笔记
    status: completed
  - id: register-nav
    content: 在 docs/.vitepress/config.mts 新增 reference 侧边栏分组并注册导航
    status: completed
    dependencies:
      - write-notes-doc
  - id: verify-doc
    content: 校验文档落盘完整性与 config.mts 语法/链接一致性
    status: completed
    dependencies:
      - register-nav
---

## 产品概述

将已完成的 DeepSeek Harness 开源项目源码与官方文档研读结论，整理为一份结构清晰的中文 markdown 笔记，落盘到本项目 `docs/reference/` 目录，作为后续开发/集成 DeepSeek Harness 的参考文档，并在 VitePress 文档站点侧边栏注册导航以便访问。

## 核心特性

- **核心工作机制分析**：深入源码层面，阐释意图识别的实现原理与流程（inbox 队列 + waterfall 事件链 + 数据驱动控制）、harness 之间的调用协同方式（agent 创建/恢复、子代理 provider、因果归因边界）、系统提示词的构建与传递机制（PromptSection 按 order 组装、工具 schema 注入、persona/工具指引分层）。
- **界面交互设计分析**：工具调用过程（presentCall/presentResult 纯函数卡片：generic/terminal/diff/search/read/web）与思考内容（reasoning 块与 text 隔离）在用户页面的展示形式；长链接会话的事件溯源执行逻辑与状态管理（append-only SessionEvent 唯一真源、surface 派生、JSONL/SQLite 持久化）。
- **前端布局与动效对比**：梳理 React 18 + Vite 6 技术栈与 30+ UI 子包结构，并与本项目 DataAgent Pro（Vue3 + Element Plus 前后端分离）做优缺点对比。
- **关键默认值与限制**：汇总沙箱、上下文压缩、流式协议、平台限制、Developer Preview 风险、密钥明文存储等易踩坑点。

## 交付物

- 新建 `docs/reference/deepseek-harness-notes.md`（结构化中文笔记）。
- 修改 `docs/.vitepress/config.mts`（新增 reference 侧边栏分组）。

## 技术栈

- 文档格式：Markdown（中文撰写，遵循项目现有 docs 风格——分层架构、代码块、对比表格）。
- 文档站点：VitePress（项目已有 `docs/.vitepress/config.mts` 侧边栏配置）。

## 实现方式

### 落盘策略

- 新建 `docs/reference/` 子目录存放研读笔记，与现有 `guide/`、`api/`、`advanced/`、`develop/` 目录并列，职责清晰（reference 定位为外部技术研读参考）。
- 文档正文复用已完成的源码研读结论（见上下文 relative_history 与历史对话），按四个用户要求维度组织为四个一级章节，补充"关键默认值与限制"章节。

### 文档结构设计

1. **核心工作机制**：意图识别（无传统 NLP 模块，靠 inbox 队列 `next-turn`/`next-step` + `send/steer/inject` + `agent/pre-step` waterfall 决策）、harness 协同（`ctx.agents.create/resume`、`withInitiator` 因果归因、subagent 各 provider）、系统提示词构建（`PromptSection` 的 order 约定 -100/0/100-199、作用域遮蔽、`system-prompt/assemble` waterfall、工具 schema 注入与 `TOOL_ORDER_REST` 保留名、`{{var}}` 插值）。
2. **界面交互设计**：工具调用展示（`presentCall`/`presentResult` 纯函数、六类卡片、已完成视图替换待执行视图）、思考内容展示（`ContentBlockMap.reasoning` 与 text 隔离、`reasoning-delta` 流式）、长链接会话（事件溯源 append-only 日志、`seq=log.length` 连续、surface 派生仅三种事件投影为消息、JSONL/SQLite 持久化、Fork API）。
3. **前端布局与动效**：React 18.2 + Vite 6 + TypeScript、无第三方状态管理/动画库、`packages/client` 30+ UI 子包（ui-layout/ui-sidebar/ui-conversation/ui-trajectory 等）；与 DataAgent Pro（Vue3 + Element Plus + Pinia + SSE）做优缺点对比表。
4. **关键默认值与限制**：沙箱 read-only、compaction 阈值、StreamChunk 流式协议、平台限制（不支持 Windows agent）、Developer Preview 兼容性风险、密钥明文存储等。

### 导航注册

在 `docs/.vitepress/config.mts` 的 `sidebar` 中新增 `/reference/` 分组，链接指向 `/reference/deepseek-harness-notes`，标题如"DeepSeek Harness 研读笔记"。

## 实现要点

- 遵循项目现有 docs 风格：中文、分层架构描述、代码块标注语言、对比用表格。
- 文档内容全部来自已完成的真实源码研读（web_fetch 获取的官方文档与 GitHub API），不虚构 API/行为。
- 导航链接与文件路径保持一致，`read_lints` 校验 config.mts 无语法错误。