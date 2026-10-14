# Harness Main Agent Architecture Design

**Date:** 2026-10-14  
**Status:** Approved (conversation)  
**Direction:** C — one main Agent; Schema / SQL / Execute / Analysis become Harness peripherals (tools / skills / MCP / optional subagents); security via policy envelope (rules, approval tiers, command whitelist), not a skippable peer node.

## Problem

The current **data** path is a fixed LangGraph DAG (`clarify_plan → schema → sql_coder → security → execute → quality_gate → analyst → reporter`). Nodes are LLM specialists with conditional routing. This is an **agentic workflow / pipeline**, not an open agent loop. Marketing as “multi-agent collaboration” is misleading; it also diverges from DeepSeek Harness / Cursor / WorkBuddy style: **one driver loop + peripheral capabilities + hard permission shell**.

Existing building blocks already lean Harness-ward:

- `app/deepagent/harness.py` (DeepAgent factory, skills progressive disclosure)
- `command_whitelist.json` + `tools_exec.run_command`
- `approval_policy` tiers (`read_only` / `workspace_write` / `full_access`)
- Chat-inline HITL (`interrupt` / resume)
- Feature-flagged event sourcing / prompt sections / seams

Gap: **data mode still bypasses the main agent loop** and keeps security as a graph peer node.

## Goals

1. **Single main Agent loop** for user turns (plan → call tools → observe → continue until done).
2. **Capability surface**: Schema, SQL generate, RAG, analyze, chart, shell — as tools / skills / MCP / optional compiled subagents.
3. **Non-bypassable policy envelope** on dangerous actions (especially SQL execute).
4. **Dual-track migration**: DeepAgent data profile behind flag; legacy graph remains fallback until parity.
5. **Honest naming** in docs/UI: “主 Agent + Harness 能力”, not “8 个 Agent 流水线”.

## Non-Goals (Phase 1)

- Delete the LangGraph data graph in one shot.
- Make Security a normal optional Skill the model can skip.
- Allow arbitrary DB drivers or raw SQL outside `data.execute`.
- Full Cursor-parity (editor, LSP, etc.).

## Target Architecture

```
User message
    ↓
Main Agent (DeepAgent / unified agent-loop)
    · system rules + skill catalog (progressive disclosure)
    · tool calls / optional subagent delegate
    ↓
Capability tools (read-mostly free; write gated)
    · schema.search / schema.get
    · sql.generate / sql.explain
    · rag.search
    · analyze.stats / chart.render
    · shell.run          → command_whitelist + tier
    · data.execute       → ONLY SQL execution entry
    ↓
Policy envelope (middleware / wrapper — not a choosable peer step)
    · SQL risk classify (regex + LLM as today)
    · approval_policy tier decision
    · HITL interrupt when required
    · result masking before return to model / SSE
    ↓
SSE / trajectory (tool_call, tool_result, reasoning, tokens, approval_required)
```

### Decision ownership

| Capability | Form | Who decides “try” | Who decides “allow” |
|------------|------|-------------------|---------------------|
| Schema / SQL generate / RAG / analyze / chart | Tool or Skill | Main Agent | Soft limits only |
| Execute SQL | Controlled tool `data.execute` | Main Agent may invoke | **Envelope always** |
| Security classify / approve | Middleware inside `data.execute` | — | Policy + HITL |
| Heavy SQL specialist | Optional SubAgent | Main Agent delegates | Still must use `data.execute` |
| Shell | Tool | Main Agent | Whitelist + tier |

## Tool / Skill Inventory (Phase 1 contract)

Stable names (implement behind these IDs; wrap existing modules):

| Tool ID | Wraps (today) | Notes |
|---------|---------------|-------|
| `schema.search` / `schema.get` | `schema_agent` | Return filtered DDL / table cards |
| `sql.generate` | `sql_coder` generate path | Dialect-aware; may self-repair on *dry* feedback only |
| `data.execute` | security + execute + mask | **Mandatory gate**; never expose raw engine to model |
| `rag.search` | `rag_agent` | Optional |
| `analyze.summarize` | `analyst` | On tabular payload from last execute |
| `chart.render` | `reporter` | ECharts JSON |
| `shell.run` | `tools_exec.run_command` | Existing whitelist |
| `load_skill` | skills progressive disclosure | Already present |

Clarification / intent: prefer **main Agent + rules** (ask user when ambiguous) over a hardwired `clarify_plan` node; keep a thin pre-check only if product requires structured clarification cards.

## Policy Envelope

1. **Rules** (system / prompt sections): read free; writes only via `data.execute`; never invent execution bypass; respect approval tier.
2. **`data.execute(sql, …)`**:
   - Classify risk (reuse security agent logic).
   - `decide_approval(tier, risk)` → auto | interrupt.
   - On interrupt: emit `approval_required`, suspend (checkpointer), resume with approve/reject.
   - On allow: run query, mask PII, return rows/summary to agent + SSE `result`.
3. **Shell**: unchanged whitelist semantics; empty whitelist = deny.
4. **Observability**: every gated call logs audit fields (user, sql hash, risk, decision).

Security is **not** registered as a peer tool `security.check` that the model can omit before a hypothetical free execute.

## Runtime / Feature Flags

| Flag | Default | Behavior |
|------|---------|----------|
| `USE_DEEP_AGENT` or profile `deepagent` for `mode=data` | false initially | Route data chat through main Agent + tools |
| Legacy `get_data_workflow()` | remains | Fallback when flag off or kill-switch |
| `AGENT_LOOP_ENABLED` | evolve | Unify construction then execution (extend existing R20 skeleton) |

Shadow mode (optional): run tool-path construction and log drift vs graph path without serving it.

## Frontend Impact

- Task checklist / step chain driven by **tool_call / tool_result / node_started** (or mapped tool IDs), not hardcoded graph node order.
- Approval UX unchanged (SSE `approval_required` → resume).
- Config center already manages skills / MCP / approval — extend to show “data tools” enablement if needed.

## Migration Milestones

1. **M1 — Tool adapters**: Wrap schema / sql.generate / data.execute / analyze / chart; unit tests on envelope (deny bypass, HITL path).
2. **M2 — Main Agent data profile**: DeepAgent (or agent-loop) with tool set + rules; feature-flagged; golden questions vs legacy.
3. **M3 — Trajectory UX**: Frontend groups by tools; docs rename.
4. **M4 — Deprecate graph default**: Flip default profile when metrics pass; keep graph as emergency fallback one release.
5. **M5 — Optional**: MCP exposure of same tools; SQL subagent for hard queries.

## Success Criteria

- Main Agent can answer a multi-step data question by choosing tools without a fixed node sequence.
- No SQL reaches the DB except through `data.execute`.
- Write SQL still requires HITL under `read_only`.
- Flag off restores legacy graph behavior.
- Docs/nav describe Harness main Agent, not “8-agent pipeline”.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Model loops or skips schema | Tool guidance + max iterations; quality skill / critic optional |
| Latency / token cost | Progressive skill disclosure; smaller tool schemas; cache schema packs |
| Regressions on Text-to-SQL | Dual-track + golden set; shadow compare |
| “Security as tool” footgun | Envelope ownership documented; code review gate on execute path |

## Related Code

- `backend/app/deepagent/harness.py`, `tools_exec.py`, `prompts.py`
- `backend/app/graph/workflow.py` (legacy)
- `backend/app/core/approval_policy.py`, `agent_loop.py`
- `backend/app/core/hitl.py` / chat approve SSE

## Out of Scope Follow-ups

- Align CLAUDE.md marketing language (small doc PR).
- Full MCP server packaging for external IDEs.
- Removing Vue legacy frontend docs (already archived).
