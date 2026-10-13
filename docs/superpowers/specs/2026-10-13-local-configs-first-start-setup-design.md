# Local Configs + First-Start Setup Design

**Date:** 2026-10-13  
**Status:** Approved (conversation); awaiting written-spec review  
**Scope:** Keep runtime JSON under `backend/configs/` out of git; seed from examples on first start; prompt only when LLM (and optionally MCP) is not usable.

## Problem

1. `llm_providers.json` (and similar files) are tracked in git. Pasting API keys into the admin UI or editing JSON locally risks committing secrets (GitHub Push Protection already blocked an OpenRouter key).
2. New clones need a clear path: generate safe defaults automatically, and tell the operator to configure a real LLM before chatting.

## Goals

- Runtime `backend/configs/*.json` are gitignored; only `*.example.json` templates are tracked.
- First start (missing runtime files) copies from examples without blocking API boot.
- Setup status flags when no usable LLM is configured; console + admin UI surface a clear prompt.
- Safe defaults for skills / default / approval / whitelist / patch need no operator action.
- MCP example has no machine-specific absolute paths; MCP setup is optional in the same status payload.

## Non-Goals

- Writing API keys back into `.env` (deferred; not part of this change).
- Refusing to start the API when setup is incomplete.
- Changing Docker/K8s Secret injection; `os.getenv` / env-based keys continue to work.
- Encrypting keys at rest or moving config into a database.

## Architecture

```
backend/configs/
  *.example.json          # tracked templates (no secrets)
  *.json                  # runtime, gitignored, created on demand

Startup (lifespan / ConfigManager):
  ensure_runtime_configs()
    → for each known name: if missing runtime && example exists → copy
  get_setup_status()
    → LLM usable? MCP notes?
  log warning if setup_required

Admin UI:
  GET /api/v1/config/setup-status
    → banner when setup_required
```

### Known config files

| Runtime file | Example | First-start behavior | Operator prompt |
|--------------|---------|----------------------|-----------------|
| `llm_providers.json` | yes | copy template with empty keys, providers disabled or env-only placeholders | **required** if no usable LLM |
| `mcp_servers.json` | yes | copy portable sample (no absolute paths), servers disabled | optional note |
| `skills.json` | yes | copy as-is | none |
| `default.json` | yes | copy as-is | none |
| `approval_policy.json` | yes | copy as-is | none |
| `command_whitelist.json` | yes | copy as-is | none |
| `patch.json` | yes | copy minimal stub | none |

## Component Design

### 1. Gitignore

Add to `.gitignore`:

```
# Runtime JSON configs (seeded from *.example.json on first start)
backend/configs/*.json
!backend/configs/*.example.json
```

Untrack existing runtime files with `git rm --cached` (keep working tree copies). Commit example files that replace them as the source of truth in the repo.

### 2. Example templates

- **`llm_providers.example.json`:** No plaintext API keys. Prefer `key_mode: "env"` with names like `DASHSCOPE_API_KEY` / `OPENROUTER_API_KEY`. Providers default to `enabled: false` except documentation-friendly samples that still have empty keys (still not “usable” until env or UI fills a key). `mode_defaults` may point at a sample id; chat remains unusable until setup passes.
- **`mcp_servers.example.json`:** Portable commands only (e.g. `npx` + package name + relative/`/tmp` path). No Windows absolute venv paths. All `enabled: false`.
- Other examples: copy current safe content (strip secrets if any appear later).

### 3. ConfigManager bootstrap

Extend `app/core/config_manager.py` (or a small sibling module called from `load_all` / lifespan):

- `KNOWN_CONFIGS`: list of runtime filenames above.
- `ensure_runtime_configs() -> list[str]`: copied filenames; log info per copy.
- Call before/within `load_all()` so the first load sees generated files.
- Idempotent: never overwrite an existing runtime file.

### 4. Setup status

`get_setup_status() -> dict`:

```json
{
  "setup_required": true,
  "llm_configured": false,
  "missing": ["llm_api_key"],
  "hints": [
    "请到管理台「模型配置」添加/启用模型，并填写 API Key（或在 .env 中设置对应环境变量）"
  ],
  "mcp_optional_hint": "如需 MCP，可在管理台「MCP」中配置（可选）",
  "bootstrapped_files": ["skills.json", "..."]
}
```

**LLM usable** when at least one provider has `enabled: true` and:

- `key_mode == "direct"` and `api_key` non-empty, or
- `key_mode == "env"` (or default) and `api_key_env` non-empty and `os.getenv(api_key_env)` non-empty.

Do not treat “provider exists but disabled / empty key” as configured.

### 5. API

`GET /api/v1/config/setup-status` (admin auth, same as other `/config/*`):

- Returns `get_setup_status()`.
- Used by frontend banner; also useful for ops scripts.

Startup: if `setup_required`, log a conspicuous warning (not error); do not fail lifespan. LLM warmup already tolerates failure.

### 6. Frontend

- React admin (`frontend-react`) and Vue admin (`frontend`) if both still ship: on admin shell load (or LLM config page), call setup-status; show dismissible or persistent banner while `setup_required`.
- Banner CTA: navigate to LLM config page.
- No modal that blocks the whole app; admin must remain usable to fix setup.

### 7. Docs

- Short note in `docs/guide/quick-start.md` (or equivalent): configs are local; first start seeds from examples; configure LLM in admin or `.env`.

## Error Handling

| Case | Behavior |
|------|----------|
| Example missing for a known file | Log warning; skip copy; that config stays empty `{}` as today |
| Copy fails (permissions) | Log error; continue boot |
| Runtime JSON invalid | Existing ConfigManager behavior (warn / keep cache) |
| Setup incomplete | Warn + UI banner; chat/LLM may fail at use time as today |

## Testing

- Unit: `ensure_runtime_configs` copies only when missing; does not overwrite.
- Unit: `get_setup_status` — no providers / disabled / env missing → `setup_required`; env set or direct key → not required.
- Manual: fresh clone without runtime json → start backend → files appear; banner shows until key configured.

## Migration for existing clones

1. Pull change: examples appear; gitignore applies; `git rm --cached` removes tracked runtime json from index.
2. Local runtime files remain on disk → no overwrite → no data loss.
3. Developers with secrets already in local `llm_providers.json` keep working; they should not re-add those files to git.

## Out of scope follow-ups

- Auto-write UI-entered keys into `.env`.
- Secret scanning CI on example files.
- Multi-node shared config store.
