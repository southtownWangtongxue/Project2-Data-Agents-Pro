# Docs IA Restructure Design

**Date:** 2026-10-14  
**Status:** Approved  
**Choice:** C — slim public VitePress docs; archive research / obsolete plans

## Goals

- Fix discoverability: one clear path for onboarding, system understanding, integration, and secondary development.
- Remove redundant / obsolete entries from nav (Vue-era plans, overlapping Harness notes, root-level planning clutter).
- Preserve history under `docs/archive/` (move, do not delete).

## Public IA

| Nav | Pages |
|-----|--------|
| 上手 | `guide/quick-start`, `guide/deployment` |
| 理解系统 | `guide/architecture`, `guide/workflow`, `reference/harness-landing-gap-analysis` |
| 使用与集成 | `api/*`, `advanced/security`, `advanced/rag-config`, `advanced/database-access` |
| 二次开发 | `develop/frontend-dev`, `develop/agent-dev`, `reference/chat-ui-playground-alignment` |
| 质量与验收 | `qa/*` |
| 归档说明 | `archive/README` (index of moved docs) |

## Home

- Frontmatter only for hero + features; body = short links, no duplicate architecture ASCII / tech stack tables.

## Archive targets

- DeepSeek / Harness research notes (except landing-gap)
- `reference/runtime-architecture.md`
- Root: 开发计划, 需求 V1/V2, 配置体系, 审计, redesign/phase docs, 开发提示词, empty AntDesignX stub
- `plans/` → `archive/plans/`
- `superpowers/` → `archive/superpowers/` (optional; keep out of nav)

## Non-goals

- No app code changes; no content deletion; CLAUDE.md sync deferred.
