---
name: deepseek-harness 集成分析报告落盘
overview: 基于官方文档与 GitHub 源码的严格事实核查，产出一份严谨的 DeepSeek Harness 核心机制分析 + 与本项目架构差异对比 + 借鉴式集成改造方案（新版本形式）的分析报告，落盘到 docs/reference 目录；代码改造待报告确认后作为第二阶段另行实施。
todos:
  - id: align-report-boundary
    content: 使用 [skill:brainstorming] 对齐报告的事实分级标准、集成方案落点与分阶段边界
    status: completed
  - id: verify-project-code
    content: 使用 [subagent:code-explorer] 核对本项目后端与前端七维度实现要点，为差异对比表提供依据
    status: completed
    dependencies:
      - align-report-boundary
  - id: write-analysis-doc
    content: 撰写并落盘 docs/reference/deepseek-harness-integration-analysis.md（三部分：机制分析、差异对比、集成方案）
    status: completed
    dependencies:
      - verify-project-code
  - id: verify-doc-accuracy
    content: 校验报告事实分级标注、来源引用与内容一致性，确保无未证实细节
    status: completed
    dependencies:
      - write-analysis-doc
  - id: register-nav
    content: 在 docs/.vitepress/config.mts 的 /reference/ 侧边栏追加新文档入口并 read_lints 校验
    status: completed
    dependencies:
      - write-analysis-doc
---

## 产品概述

产出一份严谨的 DeepSeek Harness 源码级分析报告文档，落盘到 `docs/reference/deepseek-harness-integration-analysis.md`，作为后续"借鉴设计思想改造现有架构"的决策依据。本次**仅落盘分析文档，不改动任何业务代码**，方案经用户确认后再进入第二阶段代码改造。

## 核心内容（三大部分）

### 第一部分：DeepSeek Harness 三层面源码级机制分析

- **核心工作机制**：意图识别（无传统 NLP 模块，由事件溯源 + 双 inbox 队列 + `agent/pre-step` waterfall 数据驱动决策）、harness 间调用协同（AgentHandle 的 followup/steer/inject/send/cancel + 子代理 one-shot/continuable 委派 + withInitiator 因果归因）、系统提示词构建与传递（PromptSection 按 order 分层组装 + 作用域遮蔽 + 工具 schema 注入 + assemble waterfall）。
- **界面交互设计**：工具调用与思考内容的展示（reasoning 块与 text 块类型隔离、StreamChunk 流式协议）、长链接会话执行逻辑与状态管理（append-only SessionEvent 唯一真源 + surface 投影 + deriveMessages 派生 + JSONL/SQLite 持久化 + Fork API）。
- **Web 布局与动效设计**：React + Vite 技术栈、conversation node / slot 体系、投影层与渲染层分离、轻量 CSS 过渡动效（无第三方动画库）。

### 第二部分：与本项目的差异对比

从意图识别、harness 协同、系统提示词、会话/事件溯源、流式协议、UI 渲染、布局动效七个维度做对照表，明确各自优缺点。

### 第三部分：借鉴式集成改造方案（新版本）

架构调整、模块划分、兼容性处理、分阶段实施建议，明确"不引入 dsh 运行时、仅落地设计模式到 FastAPI + Vue 架构"的路径。

## 技术方案

### 交付物与定位

- 新建单份中文 Markdown 文档 `docs/reference/deepseek-harness-integration-analysis.md`。
- 严格遵循项目现有 docs 风格（分层标题、对比表格、代码块标注语言、来源标注）。
- 内容全部基于已完成的事实核查（官方文档 + GitHub 源码 + 本项目代码），**不虚构 API/行为**。

### 内容准确性约束（关键）

对以下两类内容做严格分级标注，避免引入未经证实的细节：

1. **官方文档/源码直接证实** → 标注"官方文档核实"或"源码核实"（如 PromptSection 的 order 约定、InboxTarget 双队列、PreStepDecision、StreamChunk 联合类型、能力接缝三角色等）。
2. **旧笔记中存在但官方文档未直接证实** → 降级标注为"推测/待核实"或删除。需特别注意：

- 旧笔记的"六类工具卡片（generic/terminal/diff/search/read/web）"和"presentCall/presentResult 纯函数"在本次核查中**未被官方文档直接证实**（工具执行管线文档聚焦 pre-execute→guard→execute 流水线，未提 UI 卡片分类），应降级为"待核实"或删除。
- 旧笔记的"reject/enter 字面"实为 `agent/pre-step` 的 `PreStepDecision` 返回值语义（`{kind:'reject'}|{kind:'enter'}`），需用准确术语表述，勿与 Cordis 事件模式（emit/bail/serial/waterfall）混淆。

### 报告文档结构设计

```
# DeepSeek Harness 源码分析与本项目集成评估
## 0. 摘要（定位 + 一句话结论 + 来源说明）
## 1. 核心工作机制（意图识别 / harness 协同 / 系统提示词）
## 2. 界面交互设计（工具与思考展示 / 长链接会话与状态管理）
## 3. Web 布局与动效设计
## 4. 与本项目差异对比（七维度对照表 + 优缺点分析）
## 5. 借鉴式集成改造方案（架构调整 / 模块划分 / 兼容性处理 / 分阶段实施）
## 附录：事实来源清单（每项标注官方文档/源码页面 URL）
```

### 关键内容要点（基于已核实事实）

- **意图识别结论**：dsh 无传统 NLP 意图分类模块，决策由"事件溯源 + inbox 队列（next-turn/next-step）+ `agent/pre-step` waterfall（PreStepDecision 的 reject/enter）"数据驱动；inbox 排空决定轮次结束。对比本项目：传统模式=关键词快速通道+LLM clarify_and_plan，DeepAgent 模式=system_prompt 硬编码触发词，属规则+LLM 混合。
- **harness 协同结论**：dsh 用 AgentHandle 方法（followup/steer/inject/send/cancel）+ 子代理 seam（one-shot/continuable）+ withInitiator 因果归因；本项目用 CompiledSubAgent 预编译子图 + task 工具委派，无因果归因与 one-shot/continuable 区分。
- **系统提示词结论**：dsh 用 PromptSection 分层组装（order -100/0/100-199 + 作用域遮蔽 + assemble waterfall + 工具 schema 注入）；本项目 build_system_prompt 返回单一字符串（硬编码角色+触发词+Skills 拼接），无分层/遮蔽/组装。
- **会话/事件溯源结论**：dsh append-only SessionEvent 唯一真源 + surface 投影（仅 user/message、assistant/message、tool/result 三类投影为可见消息）+ deriveMessages 派生 + Fork；本项目 ChatSession/ChatNode 关系表 + 每轮独立 Redis checkpoint，历史靠反推重建，无投影/Fork。
- **流式协议结论**：dsh StreamChunk 封闭联合类型（block-start/text-delta/reasoning-delta/tool-call-delta/block-end/usage/finish），reasoning 与 text 类型隔离；本项目 SSE 事件 token/thinking/tool_call/tool_result 等，reasoning 未与 text 类型化隔离。
- **能力接缝结论**：dsh Service Definition/Provider/Consumer 三角色 + core/seam/bundle 三类服务，组合时选后端；本项目 ConfigManager 热加载 + skill 落盘，可借鉴 seam 思想强化可替换性。

### 集成改造方案（第三部分）核心思路

- **架构调整**：在现有 FastAPI + LangGraph 上，借鉴事件溯源引入 append-only 会话事件日志（可作为 MySQL 新表或 JSONL 落盘），以 surface 投影替代当前"从 Redis 状态反推历史"；借鉴 PromptSection 重构 build_system_prompt 为分层可组装结构；借鉴能力接缝思想抽象 LLM/存储/搜索等 seam。
- **模块划分**：新增 `app/core/event_sourcing.py`（事件日志 + surface 投影）、`app/core/prompt_section.py`（分层提示词组装）、`app/core/seam.py`（能力接缝注册表）等模块，与现有 `deepagent/`、`graph/` 并存，不破坏现有模式。
- **兼容性处理**：通过环境变量/feature flag 灰度切换，旧模式（传统 LangGraph + 现有 SSE 协议）保持可用，新架构逐步接管；SSE 协议扩展向后兼容（新增事件类型不删除旧类型）。
- **分阶段实施**：Phase 1 落盘事件日志 + 投影（会话持久化改造）→ Phase 2 系统提示词分层组装 → Phase 3 能力接缝抽象 → Phase 4 UI 渲染层改造（reasoning 折叠、conversation node）→ Phase 5 布局动效对齐。

### 文档导航登记（可选，报告确认后再定）

现有 `docs/.vitepress/config.mts` 的 nav"参考"下拉项与 sidebar `/reference/` 分组已存在。新文档完成后，可在 `/reference/` 侧边栏追加条目指向 `deepseek-harness-integration-analysis`，此步骤作为可选收尾，不阻塞文档主体交付。

## 推荐使用的 Agent Extensions

### Skill

- **brainstorming**
- 用途：在正式撰写文档前，对"哪些机制结论可直接证实、哪些需降级为待核实、集成方案的分阶段边界"做一次设计对齐，确保报告内容边界与用户意图一致。
- 预期结果：明确报告的事实分级标准与集成方案落点，避免引入未经证实的实现细节。

### SubAgent

- **code-explorer**
- 用途：在撰写"与本项目差异对比"章节前，快速核对本项目后端 `app/graph/`、`app/deepagent/`、`app/core/` 及前端 `frontend/src/stores/chat.ts`、`components/` 的确切实现细节，确保对比表精准对应真实代码。
- 预期结果：产出本项目七个维度（意图识别/协同/提示词/会话/流式/UI/布局）的实现要点清单，作为对比表依据。