"""
配置分层（R19，架构专项 P3，对齐 Harness Profile / Patch）

解决 8+ 个特性开关散落各处、运维无法统一查看与临时覆盖的问题：

分层优先级（高 → 低）：
    1. configs/patch.json   运维补丁层（热更新生效，临时覆盖）
    2. settings 默认值/.env  代码层（pydantic settings）

设计取舍：
    - 不重写 pydantic settings 体系：分层只作用于**白名单内的特性开关**，
      以"启动/重载时应用补丁到 settings 实例"的方式生效，读取点零改动
    - 白名单防止 patch.json 写入任意属性（安全边界）
    - dump_effective() 提供全量生效配置与来源标注（审计能力）
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.config_manager import get_config_manager
from app.utils.log_utils import log

PATCH_FILE = "patch.json"

# 特性开关白名单（允许被 patch.json 覆盖的 settings 属性）
KNOWN_FLAGS: list[str] = [
    "USE_DEEP_AGENT",
    "EVENT_SOURCING_ENABLED",
    "PROMPT_SECTION_ENABLED",
    "PARALLEL_ANALYST_REPORTER",
    "SKILL_PROGRESSIVE_DISCLOSURE",
    "TOOL_PIPELINE_ENABLED",
    "TOOL_EXEC_TIMEOUT",
    "TOOL_RESULT_MAX_LEN",
    "CONTEXT_COMPACTION_ENABLED",
    "CONTEXT_MAX_MESSAGES",
    "CONTEXT_KEEP_RECENT",
    "CONTEXT_DIGEST_MAX_CHARS",
    "TURN_EVENT_ENABLED",
    "AGENT_LOOP_ENABLED",
    "AGENT_LOOP_SHADOW",
    "HARNESS_MODE",
    "HARNESS_RECURSION_LIMIT",
    "HARNESS_MAX_SECONDS",
    "HARNESS_SHADOW_TIMEOUT",
]

# 生效来源标记
_SOURCE_PATCH = "patch"
_SOURCE_DEFAULT = "default"


def _get_patch() -> dict:
    """读取运维补丁层（ConfigManager 缓存，热更新自动生效）。"""
    data = get_config_manager().get(PATCH_FILE)
    return data if isinstance(data, dict) else {}


# 已应用补丁键 → 原始值快照（补丁撤销时还原默认）
_originals: dict[str, object] = {}


def apply_patch_overrides() -> list[str]:
    """把 patch.json 中白名单内的键应用到 settings 实例（启动/重载时调用）。

    支持补丁撤销：本次 patch 中已不存在、但此前被补丁覆盖过的键，
    会还原为首次覆盖前的原始值。
    返回实际应用的键列表；非法键忽略并告警。
    """
    applied: list[str] = []
    patch = _get_patch()
    settings = get_settings()

    # 1. 还原：此前被覆盖、本次 patch 已移除的键
    for key in [k for k in _originals if k not in patch]:
        try:
            setattr(settings, key, _originals.pop(key))
            log.info(f"[ConfigLayer] 补丁已撤销，还原默认: {key}")
        except Exception as exc:
            log.warning(f"[ConfigLayer] 还原 {key} 失败: {exc}")

    # 2. 应用：白名单内的补丁键
    for key, value in patch.items():
        if key.startswith("_"):
            continue  # 元键（_comment/_note 等）
        if key not in KNOWN_FLAGS:
            log.warning(f"[ConfigLayer] patch.json 含未知键 '{key}'，已忽略（白名单外）")
            continue
        try:
            if key not in _originals:
                _originals[key] = getattr(settings, key)  # 首次覆盖前留存原始值
            setattr(settings, key, value)
            applied.append(key)
        except Exception as exc:
            log.warning(f"[ConfigLayer] 应用补丁 {key}={value} 失败: {exc}")
    if applied:
        log.info(f"[ConfigLayer] 补丁覆盖已应用: {applied}")
    return applied


def dump_effective() -> dict:
    """dump 全量生效配置（R19 审计能力）：键 → {value, source}。"""
    settings = get_settings()
    patch = _get_patch()
    out: dict[str, dict] = {}
    for key in KNOWN_FLAGS:
        value = getattr(settings, key, None)
        source = _SOURCE_PATCH if key in patch else _SOURCE_DEFAULT
        out[key] = {"value": value, "source": source}
    return out


def reload_patch() -> list[str]:
    """手动重载补丁层（PATCH_FILE 被 ConfigManager watchdog 自动监听，
    此接口用于主动触发/验证）。"""
    get_config_manager().reload_file(PATCH_FILE)
    return apply_patch_overrides()
