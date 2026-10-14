"""First-start config seeding + setup status helpers."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

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
