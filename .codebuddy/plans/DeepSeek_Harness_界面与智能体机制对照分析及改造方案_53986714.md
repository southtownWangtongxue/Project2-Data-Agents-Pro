---
name: DeepSeek Harness 界面与智能体机制对照分析及改造方案
overview: 参考已部署的 DeepSeek Harness（http://127.0.0.1:3080）真实界面交互逻辑与智能体执行机制，分析其与本项目 DataAgent Pro 的差异，产出一份严谨的对照分析报告落盘到 docs/reference，并给出分阶段改造方案；代码改造待报告确认后作为后续阶段另行实施。
todos:
  - id: h1-align-facts
    content: 使用 [subagent:code-explorer] 复核本项目七维度实现要点与 11 项差距，确保差异表精准对应真实代码
    status: completed
  - id: h2-harness-interface
    content: 使用 [mcp:chrome-devtools] 与 [skill:inspiration-analyzer] 分析 Harness 界面结构与交互逻辑，产出第一部分
    status: completed
    dependencies:
      - h1-align-facts
  - id: h3-exec-mechanism
    content: 撰写第二部分：Harness 智能体执行机制对照（插件模块映射后端机制）
    status: completed
    dependencies:
      - h1-align-facts
  - id: h4-diff-table
    content: 撰写第三部分：差异对照表（11 项差距 + 已对齐点）
    status: completed
    dependencies:
      - h2-harness-interface
      - h3-exec-mechanism
  - id: h5-phase-plan
    content: 撰写第四部分：分阶段改造方案（Phase A/B/C 优先级、文件路径、风险）并落盘文档
    status: completed
    dependencies:
      - h4-diff-table
  - id: h6-nav-register
    content: 在 docs/.vitepress/config.mts 的 /reference/ 侧边栏登记新文档入口并 read_lints 校验
    status: completed
    dependencies:
      - h5-phase-plan
---

## 产品概述

用户已完成 DeepSeek Harness 本地部署（http://127.0.0.1:3080），要求参考其前端界面交互逻辑与智能体执行机制，分析本项目现有实现，思考如何改造本项目。经确认：本次**仅产出差异分析报告**，落盘到 docs/reference，**代码改造待报告确认后作为后续阶段另行实施**。

## 核心内容（报告四大部分）

### 第一部分：Harness 部署实例界面与交互逻辑分析

基于实际浏览器渲染 + HTML 源码插件注册表，分析工作区/会话树、Agent 预设、权限模式、模型选择器、命令面板、右侧详情面板、明暗双主题。

### 第二部分：Harness 智能体执行机制对照

将 Harness 前端插件模块（tool/subagent/trajectory/jobs/plan/workspace 等）映射到后端机制，分析工具调用、子代理委派、思考轨迹的展示逻辑。

### 第三部分：与本项目差异对照表

11 项差距 + 已对齐点，逐项标注现状证据与改进方向。

### 第四部分：分阶段改造方案

Phase A（界面交互对齐）→ Phase B（智能体执行机制补齐）→ Phase C（事件溯源前端时间线 + Fork UI），含优先级、对应文件路径、实现思路、风险。

## 交付物

新建单份中文 Markdown 文档 `docs/reference/harness-ui-analysis.md`，遵循项目 docs 风格（分层标题、表格、代码块、来源标注）。

## 技术栈与约束

本次任务为**纯文档撰写**，不涉及代码改造。技术要点：

### 内容准确性约束

严格基于已核实事实，不虚构 API/行为：

- **Harness 侧**：基于实际渲染（Chrome DevTools take_snapshot）与 HTML 源码插件注册表（web_fetch），标注来源「实际渲染」或「HTML 源码核实」。
- **本项目侧**：基于 code-explorer 对 `backend/app/api/v1/chat.py`、`backend/app/graph/workflow.py`、`backend/app/deepagent/harness.py`、`backend/app/graph/subagents.py`、`backend/app/core/event_sourcing.py`、`backend/app/core/stream_protocol.py`、`frontend/src/views/Chat.vue`、`ChatInput.vue`、`stores/chat.ts`、`composables/useSSE.ts` 的代码核实。

### 报告结构

```
# DeepSeek Harness 界面与执行机制对比本项目分析
## 0. 摘要（定位 + 数据来源 + 一句话结论）
## 1. Harness 部署实例界面与交互逻辑（工作区/会话树/Agent预设/权限模式/命令面板/详情面板/主题）
## 2. Harness 智能体执行机制对照（插件模块 → 后端机制映射）
## 3. 与本项目差异对照表（11 项差距 + 已对齐点）
## 4. 分阶段改造方案（Phase A/B/C，含优先级/文件路径/实现思路/风险）
## 附录：来源清单（Harness 界面 + 本项目代码文件）
```

### 关键内容要点

- **Harness 界面**：左侧工作区+会话树；顶部 Agent 预设/权限模式/模型选择；输入区命令面板；右侧详情面板；明暗双主题。
- **11 项差距**：1 无工作区 2 无 Agent 预设 3 无权限模式前端控制 4 无命令面板 5 无思考轨迹时间线 6 无子代理可视化 7 无事件溯源前端时间线 8 审批断链 9 无 Fork UI 10 任务粒度粗 11 task 模式无 plan/clarification。
- **已对齐点**：事件溯源、reasoning/text 类型化隔离、多轮节点导航、明暗主题变量。
- **分阶段改造**：Phase A 界面交互（命令面板/工作区/Agent预设/权限模式/详情面板）→ Phase B 执行机制（子代理可视化/轨迹时间线/审批断链修复）→ Phase C 事件时间线 + Fork UI。

## 实施要点

- 新建文档路径：`docs/reference/harness-ui-analysis.md`。
- 严格遵循项目 docs 风格（分层标题、对比表格、代码块标注语言、来源标注）。
- 可选收尾：在 `docs/.vitepress/config.mts` 的 `/reference/` 侧边栏登记新文档入口。

## Agent Extensions

### SubAgent

- **code-explorer**
- 用途：已在规划前完成对项目后端智能体执行机制（chat.py/workflow.py/harness.py/subagents.py/event_sourcing.py/stream_protocol.py）与前端界面（Chat.vue/ChatInput.vue/chat.ts/useSSE.ts）的梳理，产出 11 项差距清单，作为报告「差异对照表」与「分阶段改造方案」的事实依据。
- 预期结果：报告第三、四部分精准对应真实代码路径与实现细节。

### MCP

- **chrome-devtools**
- 用途：已对 Harness 部署实例（127.0.0.1:3080）做实际渲染探查（take_snapshot 获取工作区/会话树/Agent预设/权限模式/命令面板/详情面板的真实结构），并配合 web_fetch 抓取 HTML 源码插件注册表。
- 预期结果：报告第一、二部分基于 Harness 真实界面而非推测。

### Skill

- **inspiration-analyzer**
- 用途：在撰写「Harness 界面与交互逻辑分析」章节时，结合已抓取的 Harness 界面结构，提炼其布局、组件层次与交互模式（可选增强，若需更系统的界面分析则调用）。
- 预期结果：报告第一部分的界面分析更结构化、可操作。