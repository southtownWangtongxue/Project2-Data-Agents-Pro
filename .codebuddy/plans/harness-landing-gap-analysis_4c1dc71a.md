---
name: harness-landing-gap-analysis
overview: 产出《Harness 架构落地差距分析》报告入库 docs/(含已落地清单、差距项、分阶段建议),并同步修正既有文档(CLAUDE.md、项目审计与改进计划.md、README/架构文档)中与代码现状不符的过时内容。全程仅改文档,不改任何代码、配置与 feature flag。
todos:
  - id: verify-claims
    content: 使用 [subagent:code-explorer] 核实审计文档全部过时陈述的代码证据，形成对照表
    status: completed
  - id: write-gap-report
    content: 撰写 docs/reference/harness-landing-gap-analysis.md 差距分析报告(已落地清单/差距项/分阶段建议/来源标注)
    status: completed
    dependencies:
      - verify-claims
  - id: fix-audit-doc
    content: 修正 docs/项目审计与改进计划.md 过时项(§4.2 事件清单、§3.2 对照表、§5 问题表、阶段 C 标注)
    status: completed
    dependencies:
      - verify-claims
  - id: update-claude-readme
    content: CLAUDE.md 架构节补四模块与 flag 说明；README/architecture.md/index.md 最小化补充能力一句话
    status: completed
    dependencies:
      - verify-claims
  - id: nav-and-commit
    content: 报告挂入 VitePress 导航(如适用)；分两个 commit 提交(①用户的 Hermes→Harness 更名；②差距分析报告 + 文档对齐)，提交前核对工作区无代码文件改动
    status: completed
    dependencies:
      - write-gap-report
      - fix-audit-doc
      - update-claude-readme
---

## 产品概述

用户已将项目文档中的架构称谓由「Hermes」统一更名为「Harness」(7 个文件、纯措辞更名)，需要一份正式的「Harness 架构落地差距分析」报告入库，并对既有文档中与代码现状不符的过时内容进行对齐——让文档与代码真实状态一致。

## 核心交付

1. **差距分析报告**(新建 `docs/reference/harness-landing-gap-analysis.md`):

- 已落地清单：对照 `docs/reference/deepseek-harness-integration-analysis.md`(v1.0, 2026-08-17)的 5 阶段方案，逐项核实 Phase 1~4 的实际落地状态(event_sourcing / prompt_section / seam / stream_protocol 四模块、三 feature flag、fork/trajectory/goal API、reasoning/step_id/channel 协议演进、2026-09-28 流式链路优化三 commit)
- 差距项：三 flag 默认 False 无灰度计划、子代理无 MessageSource 因果归因、Phase 5 slot 体系未实施、传统路径意图识别仍为 LLM clarify_and_plan、TokenUsage 未细分——只列出分析与分阶段建议，本轮不实施
- 来源标注：每项结论标注证据(代码文件路径、commit、参考文档章节)

2. **既有文档对齐**(仅文档，不改代码/配置/flag):

- `docs/项目审计与改进计划.md`:修正 §4.2 事件清单(quality_feedback 已补、node_started 已产出、补 reasoning/channel/step_id)、§3.2 对照表(流式 Token/思考过程/工具可视化/会话管理已实现)、§5 问题表(RAG Agent、deepAgents 已落地)、阶段 C-1/C-2 标注完成
- `CLAUDE.md`:架构节补充四个新核心模块与三个 feature flag 说明
- `README.md` / `docs/guide/architecture.md` / `docs/index.md`:最小化补充「事件溯源/能力接缝/分层提示词」能力一句话说明

## 约束

- 仅改文档文件(docs/、CLAUDE.md、README.md),不改任何代码、配置、feature flag、数据库
- 不回退不覆盖用户已做的 Hermes→Harness 更名(基于其上继续工作)
- 报告风格与 docs/reference/ 下 deepseek-harness 系列文档一致(中文、表格化、分级来源标注)
- 报告加入 docs/.vitepress 导航(如该系列文档已挂导航)

## Agent Extensions

### SubAgent

- **code-explorer**
- Purpose: 核实审计文档中待修正陈述对应的代码证据(如 rag_agent 节点、task_workflow、会话 API 清单)，确保报告与文档修正的每一条结论都有代码级依据
- Expected outcome: 输出「陈述 → 代码证据(文件/行/commit)」对照表，供报告引用