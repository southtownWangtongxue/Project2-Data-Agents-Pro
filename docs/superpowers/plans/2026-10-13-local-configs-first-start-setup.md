# Local Configs + First-Start Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep runtime `backend/configs/*.json` out of git, seed them from tracked `*.example.json` on first start, and surface a setup prompt when no usable LLM is configured.

**Architecture:** Track only `backend/configs/*.example.json`. On `ConfigManager.load_all()`, call `ensure_runtime_configs()` to copy missing runtime files. `get_setup_status()` decides if LLM is usable (enabled provider + resolvable key). Expose `GET /config/setup-status` for admin UIs; log a warning at boot; show a banner in React/Vue admin layouts.

**Tech Stack:** Python 3.10+, FastAPI, pytest, existing ConfigManager, React (antd) + Vue admin layouts, gitignore.

## Global Constraints

- Do not overwrite existing runtime JSON files.
- Do not put plaintext API keys in any `*.example.json`.
- Do not block API startup when setup is incomplete.
- Do not write keys into `.env` in this plan.
- Backend tests: run via `cd backend && uv run pytest …`.
- Commits: only when a task step says Commit; do not amend unless the user asks.

## File Structure

| Path | Responsibility |
|------|----------------|
| `backend/configs/*.example.json` | Tracked templates (no secrets) |
| `backend/configs/*.json` | Runtime only; gitignored |
| `backend/app/core/config_bootstrap.py` | `KNOWN_CONFIGS`, `ensure_runtime_configs`, `is_llm_usable`, `get_setup_status` |
| `backend/app/core/config_manager.py` | Call ensure before load; expose setup helper if needed |
| `backend/app/api/v1/config_api.py` | `GET /setup-status` |
| `backend/app/main.py` | Log setup warning in lifespan |
| `backend/tests/test_config_bootstrap.py` | Unit tests for bootstrap + setup status |
| `frontend-react/src/pages/AdminLayout.tsx` | Fetch status + banner |
| `frontend/src/views/AdminLayout.vue` | Fetch status + banner |
| `.gitignore` | Ignore runtime `*.json`, keep `*.example.json` |
| `docs/guide/quick-start.md` | Document seed + admin LLM setup |

---

### Task 1: Example templates + gitignore (no secrets in repo)

**Files:**
- Create: `backend/configs/llm_providers.example.json`
- Create: `backend/configs/mcp_servers.example.json`
- Create: `backend/configs/skills.example.json`
- Create: `backend/configs/default.example.json`
- Create: `backend/configs/approval_policy.example.json`
- Create: `backend/configs/command_whitelist.example.json`
- Create: `backend/configs/patch.example.json`
- Modify: `.gitignore`
- Untrack (keep disk): `backend/configs/*.json` via `git rm --cached`

**Interfaces:**
- Consumes: current runtime JSON content on disk (scrub secrets for examples)
- Produces: seven `*.example.json` files; gitignore rules

- [ ] **Step 1: Write `llm_providers.example.json` (no secrets)**

```json
{
  "providers": [
    {
      "id": "qwen-flash",
      "name": "qwen3.7-max",
      "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key_env": "DASHSCOPE_API_KEY",
      "api_key": "",
      "key_mode": "env",
      "model": "qwen3.7-max",
      "temperature": 0.3,
      "max_tokens": 4096,
      "is_default": false,
      "enabled": false
    },
    {
      "id": "openrouter-sample",
      "name": "openrouter-sample",
      "api_base": "https://openrouter.ai/api/v1",
      "api_key_env": "OPENROUTER_API_KEY",
      "api_key": "",
      "key_mode": "env",
      "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
      "temperature": 0.7,
      "max_tokens": 128000,
      "is_default": true,
      "enabled": false
    }
  ],
  "mode_defaults": {
    "data": "openrouter-sample",
    "report": "openrouter-sample",
    "doc": "openrouter-sample",
    "task": "openrouter-sample"
  }
}
```

- [ ] **Step 2: Write `mcp_servers.example.json` (portable, disabled)**

```json
{
  "servers": [
    {
      "id": "filesystem",
      "name": "文件系统",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "enabled": false
    }
  ]
}
```

- [ ] **Step 3: Copy safe defaults into the remaining examples**

Copy current content from:
- `skills.json` → `skills.example.json`
- `default.json` → `default.example.json`
- `approval_policy.json` → `approval_policy.example.json`
- `command_whitelist.json` → `command_whitelist.example.json`

`patch.example.json`:

```json
{
  "_comment": "运维补丁层：在白名单内临时覆盖特性开关。默认为空对象即可。"
}
```

Verify no file under `backend/configs/*.example.json` contains `sk-` substrings.

- [ ] **Step 4: Update `.gitignore`**

Append:

```
# Runtime JSON configs (seeded from *.example.json on first start)
backend/configs/*.json
!backend/configs/*.example.json
```

- [ ] **Step 5: Untrack runtime JSON; keep working tree**

```bash
git rm --cached backend/configs/llm_providers.json backend/configs/mcp_servers.json backend/configs/skills.json backend/configs/default.json backend/configs/approval_policy.json backend/configs/command_whitelist.json backend/configs/patch.json
```

Expected: files remain on disk; index no longer tracks them.

- [ ] **Step 6: Commit**

```bash
git add .gitignore backend/configs/*.example.json
git commit -m "chore(configs): track example templates; gitignore runtime JSON"
```

---

### Task 2: `ensure_runtime_configs` (TDD)

**Files:**
- Create: `backend/app/core/config_bootstrap.py`
- Create: `backend/tests/test_config_bootstrap.py`
- Modify: `backend/app/core/config_manager.py` (call ensure inside `load_all`)

**Interfaces:**
- Consumes: `configs_dir: Path`
- Produces:
  - `KNOWN_CONFIGS: list[str]` — the seven runtime filenames
  - `ensure_runtime_configs(configs_dir: Path) -> list[str]` — names copied this call

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_config_bootstrap.py`:

```python
import json
from pathlib import Path

from app.core.config_bootstrap import KNOWN_CONFIGS, ensure_runtime_configs


def test_ensure_copies_missing_runtime_files(tmp_path: Path):
    for name in KNOWN_CONFIGS:
        stem = name.removesuffix(".json")
        (tmp_path / f"{stem}.example.json").write_text(
            json.dumps({"seed": name}), encoding="utf-8"
        )
    copied = ensure_runtime_configs(tmp_path)
    assert set(copied) == set(KNOWN_CONFIGS)
    for name in KNOWN_CONFIGS:
        assert (tmp_path / name).is_file()
        assert json.loads((tmp_path / name).read_text(encoding="utf-8")) == {"seed": name}


def test_ensure_does_not_overwrite_existing(tmp_path: Path):
    stem = "llm_providers"
    (tmp_path / f"{stem}.example.json").write_text('{"from":"example"}', encoding="utf-8")
    (tmp_path / f"{stem}.json").write_text('{"from":"runtime"}', encoding="utf-8")
    # other examples present so ensure does not skip entire set awkwardly
    for name in KNOWN_CONFIGS:
        s = name.removesuffix(".json")
        if s == stem:
            continue
        (tmp_path / f"{s}.example.json").write_text("{}", encoding="utf-8")
    copied = ensure_runtime_configs(tmp_path)
    assert "llm_providers.json" not in copied
    assert json.loads((tmp_path / "llm_providers.json").read_text(encoding="utf-8")) == {
        "from": "runtime"
    }


def test_ensure_skips_when_example_missing(tmp_path: Path):
    # no examples at all
    assert ensure_runtime_configs(tmp_path) == []
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && uv run pytest tests/test_config_bootstrap.py -v
```

Expected: FAIL (`ModuleNotFoundError` or import error for `config_bootstrap`).

- [ ] **Step 3: Implement `config_bootstrap.py`**

```python
"""First-start config seeding + setup status helpers."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.utils.log_utils import log

KNOWN_CONFIGS: list[str] = [
    "llm_providers.json",
    "mcp_servers.json",
    "skills.json",
    "default.json",
    "approval_policy.json",
    "command_whitelist.json",
    "patch.json",
]


def _example_path(configs_dir: Path, runtime_name: str) -> Path:
    stem = runtime_name.removesuffix(".json")
    return configs_dir / f"{stem}.example.json"


def ensure_runtime_configs(configs_dir: Path) -> list[str]:
    """Copy missing runtime JSON from *.example.json. Never overwrite existing."""
    copied: list[str] = []
    for name in KNOWN_CONFIGS:
        runtime = configs_dir / name
        example = _example_path(configs_dir, name)
        if runtime.exists():
            continue
        if not example.is_file():
            log.warning(f"[ConfigBootstrap] 缺少示例模板，跳过: {example.name}")
            continue
        try:
            shutil.copyfile(example, runtime)
            copied.append(name)
            log.info(f"[ConfigBootstrap] 已从示例生成: {name}")
        except OSError as exc:
            log.error(f"[ConfigBootstrap] 生成 {name} 失败: {exc}")
    return copied
```

- [ ] **Step 4: Wire into `ConfigManager.load_all`**

At the start of `load_all` in `backend/app/core/config_manager.py`:

```python
from app.core.config_bootstrap import ensure_runtime_configs

def load_all(self):
    ensure_runtime_configs(CONFIGS_DIR)
    for path in sorted(CONFIGS_DIR.glob("*.json")):
        if path.name.endswith(".example.json"):
            continue
        # note: glob "*.json" does not match "*.example.json" as a separate pattern
        # but "*.example.json" ends with .json — MUST skip example files
        if path.name.endswith(".example.json"):
            continue
        self._cache[path.name] = self._load_json(path.name)
    log.info("[ConfigManager] 配置加载完成")
```

Important: `Path.glob("*.json")` matches `foo.example.json` because the name ends with `.json`. Always skip `*.example.json` when loading into cache.

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd backend && uv run pytest tests/test_config_bootstrap.py -v
```

Expected: PASS for the three ensure tests (setup-status tests not yet added).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config_bootstrap.py backend/app/core/config_manager.py backend/tests/test_config_bootstrap.py
git commit -m "feat(config): seed runtime JSON from examples on first load"
```

---

### Task 3: `get_setup_status` / LLM usable check (TDD)

**Files:**
- Modify: `backend/app/core/config_bootstrap.py`
- Modify: `backend/tests/test_config_bootstrap.py`

**Interfaces:**
- Consumes: providers list (`list[dict]`), `os.environ`
- Produces:
  - `is_llm_usable(providers: list[dict]) -> bool`
  - `get_setup_status(*, providers: list[dict], bootstrapped_files: list[str] | None = None) -> dict`

- [ ] **Step 1: Append failing tests**

```python
import os
from app.core.config_bootstrap import is_llm_usable, get_setup_status


def test_llm_not_usable_when_disabled_or_empty_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert not is_llm_usable([
        {"enabled": False, "key_mode": "env", "api_key_env": "OPENROUTER_API_KEY", "api_key": ""},
        {"enabled": True, "key_mode": "env", "api_key_env": "OPENROUTER_API_KEY", "api_key": ""},
        {"enabled": True, "key_mode": "direct", "api_key_env": "", "api_key": ""},
    ])


def test_llm_usable_with_env_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert is_llm_usable([
        {"enabled": True, "key_mode": "env", "api_key_env": "OPENROUTER_API_KEY", "api_key": ""},
    ])


def test_llm_usable_with_direct_key():
    assert is_llm_usable([
        {"enabled": True, "key_mode": "direct", "api_key_env": "", "api_key": "sk-direct"},
    ])


def test_setup_status_required_when_no_llm():
    status = get_setup_status(providers=[], bootstrapped_files=["skills.json"])
    assert status["setup_required"] is True
    assert status["llm_configured"] is False
    assert "llm_api_key" in status["missing"]
    assert status["bootstrapped_files"] == ["skills.json"]
    assert isinstance(status["hints"], list) and status["hints"]
    assert "mcp_optional_hint" in status
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && uv run pytest tests/test_config_bootstrap.py::test_llm_usable_with_env_key -v
```

Expected: FAIL (functions missing).

- [ ] **Step 3: Implement helpers in `config_bootstrap.py`**

```python
import os
from typing import Any


def is_llm_usable(providers: list[dict[str, Any]]) -> bool:
    for p in providers:
        if not p.get("enabled"):
            continue
        if p.get("key_mode") == "direct" and (p.get("api_key") or "").strip():
            return True
        env_name = (p.get("api_key_env") or "").strip()
        if env_name and os.getenv(env_name, "").strip():
            return True
    return False


def get_setup_status(
    *,
    providers: list[dict[str, Any]],
    bootstrapped_files: list[str] | None = None,
) -> dict[str, Any]:
    llm_ok = is_llm_usable(providers)
    missing: list[str] = []
    if not llm_ok:
        missing.append("llm_api_key")
    return {
        "setup_required": not llm_ok,
        "llm_configured": llm_ok,
        "missing": missing,
        "hints": [
            "请到管理台「模型配置」添加/启用模型，并填写 API Key（或在 .env 中设置对应环境变量）"
        ]
        if not llm_ok
        else [],
        "mcp_optional_hint": "如需 MCP，可在管理台「MCP」中配置（可选）",
        "bootstrapped_files": list(bootstrapped_files or []),
    }
```

- [ ] **Step 4: Run full bootstrap tests — expect PASS**

```bash
cd backend && uv run pytest tests/test_config_bootstrap.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config_bootstrap.py backend/tests/test_config_bootstrap.py
git commit -m "feat(config): add setup status for usable LLM detection"
```

---

### Task 4: Lifespan warning + API endpoint

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/config_api.py`
- Optional test: extend `backend/tests/test_api.py` only if an easy admin client fixture exists; otherwise manual curl is enough for this task.

**Interfaces:**
- Consumes: `get_config_manager().llm_providers`, `get_setup_status`
- Produces: `GET /api/v1/config/setup-status` → setup status dict

- [ ] **Step 1: Add route in `config_api.py` (near top of LLM section)**

```python
from app.core.config_bootstrap import get_setup_status

@router.get("/setup-status", summary="首次配置状态")
async def setup_status(_admin=Depends(require_admin)):
    mgr = get_config_manager()
    return get_setup_status(providers=mgr.llm_providers)
```

- [ ] **Step 2: Log warning in `lifespan` after config watcher starts**

```python
from app.core.config_bootstrap import get_setup_status
from app.core.config_manager import get_config_manager

mgr = get_config_manager()
status = get_setup_status(providers=mgr.llm_providers)
if status["setup_required"]:
    for hint in status["hints"]:
        log.warning(f"[Setup] {hint}")
    log.warning(f"[Setup] {status['mcp_optional_hint']}")
```

Place after `get_config_manager().start_watcher()` so configs are loaded (singleton already called `load_all` on first `get_config_manager()`).

- [ ] **Step 3: Manual smoke (optional if server running)**

```bash
# with admin JWT
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/config/setup-status
```

Expected JSON includes `setup_required` boolean.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/api/v1/config_api.py
git commit -m "feat(config): expose setup-status API and boot warning"
```

---

### Task 5: React admin setup banner

**Files:**
- Modify: `frontend-react/src/pages/AdminLayout.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/config/setup-status` via existing `api()` helper
- Produces: banner above `<Outlet />` when `setup_required`

- [ ] **Step 1: Add status fetch + banner in `AdminLayout.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { Alert } from 'antd'
import { api } from '@/api/client'

type SetupStatus = {
  setup_required: boolean
  hints: string[]
  mcp_optional_hint?: string
}

// inside AdminLayout:
const [setup, setSetup] = useState<SetupStatus | null>(null)

useEffect(() => {
  if (!getToken()) return
  api<SetupStatus>('/config/setup-status')
    .then(setSetup)
    .catch(() => setSetup(null))
}, [navigate])

// in JSX, above <Outlet />:
{setup?.setup_required && (
  <Alert
    type="warning"
    showIcon
    className="mb-4"
    message={setup.hints?.[0] || '请先配置可用的 LLM 模型'}
    description={
      <span>
        {setup.mcp_optional_hint}
        {' · '}
        <button
          type="button"
          className="text-brand-light bg-transparent border-none cursor-pointer underline"
          onClick={() => navigate('/admin/llm')}
        >
          前往模型配置
        </button>
      </span>
    }
  />
)}
```

Keep existing auth redirect `useEffect`. Merge imports carefully (`useEffect` may already be imported).

- [ ] **Step 2: Manual check**

Open `/admin/llm` with admin account when no usable LLM → banner visible. After enabling a provider with key → refresh → banner gone.

- [ ] **Step 3: Commit**

```bash
git add frontend-react/src/pages/AdminLayout.tsx
git commit -m "feat(frontend-react): show first-start LLM setup banner in admin"
```

---

### Task 6: Vue admin setup banner

**Files:**
- Modify: `frontend/src/views/AdminLayout.vue`

**Interfaces:**
- Same API as Task 5

- [ ] **Step 1: Fetch setup-status on mount; show alert**

Use the project's existing request helper (same pattern as other admin views — typically `request` / axios wrapper under `@/api`). If unsure, mirror `LlmConfig.vue` fetch style.

Minimal pattern:

```ts
import { onMounted, ref } from 'vue'
// use whatever HTTP helper LlmConfig.vue uses for /config/llm

const setupRequired = ref(false)
const setupHint = ref('')
const mcpHint = ref('')

onMounted(async () => {
  try {
    const data = await /* same client as LlmConfig */('/config/setup-status')
    setupRequired.value = !!data.setup_required
    setupHint.value = data.hints?.[0] || ''
    mcpHint.value = data.mcp_optional_hint || ''
  } catch {
    setupRequired.value = false
  }
})
```

Template above main content:

```html
<div v-if="setupRequired" class="setup-banner">
  <p>{{ setupHint }}</p>
  <p class="muted">{{ mcpHint }}</p>
  <button type="button" @click="router.push('/admin/llm')">前往模型配置</button>
</div>
```

Style lightly to match existing admin theme (warning border/background already used elsewhere if available).

- [ ] **Step 2: Manual check** — same as Task 5 on Vue admin.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/AdminLayout.vue
git commit -m "feat(frontend): show first-start LLM setup banner in Vue admin"
```

---

### Task 7: Quick-start docs

**Files:**
- Modify: `docs/guide/quick-start.md`

- [ ] **Step 1: Add a short section after env configuration**

Insert after the `.env` section (around “第二步：配置环境变量”):

```markdown
## 配置中心 JSON（本地生成）

`backend/configs/*.json` 为运行时配置，**不入库**。仓库只提供同名的 `*.example.json`。

- 后端首次启动时，若缺少运行时文件，会自动从 example 拷贝生成。
- 密钥请在管理台「模型配置」中填写，或写入 `.env` 中对应的环境变量名（如 `OPENROUTER_API_KEY`），**不要**把明文 key 提交到 git。
- 启动日志若出现 `[Setup]` 警告，表示尚未配置可用 LLM；打开管理台按提示完成配置即可。
```

- [ ] **Step 2: Commit**

```bash
git add docs/guide/quick-start.md
git commit -m "docs: document local config seeding and first-start LLM setup"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run bootstrap unit tests**

```bash
cd backend && uv run pytest tests/test_config_bootstrap.py -v
```

Expected: all PASS.

- [ ] **Step 2: Confirm git hygiene**

```bash
git check-ignore -v backend/configs/llm_providers.json
git ls-files backend/configs/
```

Expected: runtime json is ignored; `git ls-files` lists only `*.example.json` under `backend/configs/`.

- [ ] **Step 3: Confirm no secrets in tracked examples**

```bash
rg -n "sk-" backend/configs/*.example.json
```

Expected: no matches (or only comments explaining not to paste keys — prefer zero matches).

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| gitignore runtime `*.json`, keep examples | Task 1 |
| `git rm --cached` migration | Task 1 |
| Example templates without secrets / portable MCP | Task 1 |
| `ensure_runtime_configs` copy-if-missing | Task 2 |
| Skip loading `*.example.json` into cache | Task 2 |
| LLM usable detection + setup status | Task 3 |
| Boot warning, non-blocking | Task 4 |
| `GET /config/setup-status` | Task 4 |
| React admin banner | Task 5 |
| Vue admin banner | Task 6 |
| Quick-start docs | Task 7 |
| No `.env` writeback / no boot hard-fail | Global constraints |

## Self-review notes

- Example filename convention is `{stem}.example.json` (e.g. `llm_providers.example.json`), not `llm_providers.json.example`.
- `glob("*.json")` matches `*.example.json`; Task 2 must skip them in `load_all`.
- `bootstrapped_files` in API may be empty after first boot (ensure runs inside load_all without returning list to main); optional — API can omit or return `[]`. Spec allows empty list; do not require persisting bootstrap history across restarts.
