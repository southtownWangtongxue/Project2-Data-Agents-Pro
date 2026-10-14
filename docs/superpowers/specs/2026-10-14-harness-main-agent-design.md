# Harness 主 Agent 架构设计

**Date:** 2026-10-14  
**Status:** Approved (conversation)  
**Supersedes (naming):** 「8 Agent 固定流水线」作为 Data 主路径的对外表述  
**Related:** `docs/reference/harness-landing-gap-analysis.md`, DeepAgent harness / Skills / approval_policy / command_whitelist

## 1. Problem

当前 Data 模式是 LangGraph 固定编排（clarify → schema → sql_coder → security → execute → …）。节点虽称 Agent，但下一步由条件边写死，体验与 Cursor / DeepSeek Harness / WorkBuddy 的「主循环 + 外围能力」不一致；安全靠流水线位置保证，而非 Harness 式策略壳。

## 2. Goals

- **主 Agent 循环**：规划 / 调工具 / 观察 / 再规划，自主决定是否查 Schema、生成 SQL、分析、出图。
- **能力外围化**：现有编排步骤变为 Tool / Skill / MCP / 可选 SubAgent，可配置启停。
- **安全不可旁路**：执行类动作经 Policy 中间件（分类、审批档位、HITL、脱敏、命令白名单）；Security **不是**可跳过的并列 Skill。
- **渐进迁移**：双轨（DeepAgent data 路径 + legacy graph），feature flag 切换；不一次删图。

## 3. Non-Goals (Phase 1)

- 删除全部 LangGraph data 图代码。
- 让模型直连 JDBC / 任意执行未包装 SQL。
- 将 Security 做成普通可跳过 Skill。
- 默认 `full_access` 无确认。

## 4. Target Architecture

```
User message
    ↓
Main Agent (DeepAgent loop)
    ↓ tools / skills / mcp / subagents
    ├─ schema.search / schema.get
    ├─ sql.generate / sql.explain
    ├─ data.execute   ← mandatory policy envelope
    ├─ rag.search
    ├─ analyze / chart
    └─ shell.run      ← command_whitelist + tier
    ↓
Policy envelope (rules + middleware, not optional tools)
    · system rules
    · approval_policy tiers
    · SQL risk class + HITL interrupt
    · command whitelist / path sandbox
```

### 4.1 Decision matrix

| Capability | Form | Who decides to invoke | Who decides allow |
|------------|------|----------------------|-------------------|
| Schema / generate SQL / analyze / chart | Tool or Skill | Main Agent | Mostly free (read) |
| Execute SQL | Controlled Tool `data.execute` | Main Agent may request | Middleware always |
| Security | Envelope around execute | — | Always on |
| Heavy SQL specialty | Optional SubAgent | Main Agent delegates | Same execute envelope |
| Shell | Tool `shell.run` | Main Agent | Whitelist + tier |

### 4.2 Tool inventory (Phase 1 contract)

| Tool ID | Maps from | Notes |
|---------|-----------|--------|
| `schema.search` / `schema.get` | `schema_agent` | Return filtered DDL / columns |
| `sql.generate` | `sql_coder` (gen only) | Dialect-aware; no execute |
| `sql.explain` | optional | Read-only explain if dialect supports |
| `data.execute` | `security` + `execute_sql` | **Only** SQL execution entry |
| `rag.search` | `rag_agent` | Optional |
| `analyze.result` | `analyst` | Stats on last result set |
| `chart.render` | `reporter` | ECharts JSON |
| `shell.run` | existing deepagent exec | Whitelist first token |

Clarification / misc / title can remain lightweight helpers (prompt or thin tools), not graph nodes.

### 4.3 Policy envelope on `data.execute`

1. Parse / classify SQL (regex + existing LLM double-check as needed).  
2. `approval_policy.decide_approval(tier, risk)` — reuse `app/core/approval_policy.py`.  
3. If human required → HITL interrupt (reuse conversation approve / resume).  
4. Execute via existing DB session layer.  
5. Mask sensitive fields before returning to Agent / SSE.  
6. Never expose a second execute path to the model.

System rules (prompt + hard checks): model must not invent connection strings; must not claim write succeeded without `data.execute` result.

### 4.4 Main Agent runtime

- Prefer existing `app/deepagent/harness.py` (`create_deep_agent`, Skills progressive disclosure, fixed tools).  
- Data mode profile: DeepAgent with the tool set above (+ MCP from config when enabled).  
- Trajectory: emit `tool_call` / `tool_result` (and existing SSE types) for UI step list — stop hardcoding graph node names as the only progress model.

## 5. Migration

| Phase | Deliverable | Exit criteria |
|-------|-------------|---------------|
| M0 | Spec + tool interface stubs behind flag | Review approved |
| M1 | Wrap schema / sql.generate / data.execute / analyze / chart as tools; policy on execute | Unit tests; shadow or opt-in flag |
| M2 | Data chat path via DeepAgent when `USE_DEEP_AGENT` / data-profile on | Parity on golden NL→SQL cases; HITL still works |
| M3 | UI trajectory from tools; docs rename | Frontend checklist not node-locked |
| M4 | Deprecate default legacy graph; keep fallback flag | Error budget OK |

Flags (illustrative; names may align with existing settings):

- Keep `USE_DEEP_AGENT` as master or introduce `DATA_AGENT_PROFILE=legacy|harness`.  
- Legacy graph remains until M4.

## 6. Compatibility

- Approval tiers, command whitelist, config center Skills/MCP UI stay.  
- SSE protocol: only add, don’t remove (`stream_protocol`).  
- Existing HITL approve API continues to resume the same thread.

## 7. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Agent skips schema → bad SQL | Prompt rules + optional soft gate / quality tool; eval suite |
| Agent bypasses security | Single execute tool; code review forbid raw DB in other tools |
| Latency / token cost | Progressive skill disclosure; schema search not full dump |
| Regressions | Golden queries; shadow compare legacy vs harness |

## 8. Success metrics

- Default data path runs Main Agent + tools under flag.  
- 100% write SQL still hit approval when tier requires.  
- No plaintext second execute API for the model.  
- Docs describe「主 Agent + Harness 能力」，not「8 Agent 流水线」as primary story.

## 9. Open follow-ups (out of Phase 1 scope)

- Full MCP packaging of every tool for external hosts.  
- SubAgent for SQL-only specialist.  
- Unify `AgentLoopRunner` to own streaming end-to-end (R20 completion).
