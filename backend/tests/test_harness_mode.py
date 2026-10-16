"""HARNESS_MODE 配置链路测试(RED→GREEN)。

验证三处打通:
1. settings.HARNESS_MODE 字段存在且默认 off(.env 可配);
2. HARNESS_MODE 进入 config_layer 白名单(configs/patch.json 可热更新覆盖);
3. chat.py 的解析函数读 settings 而非裸 os.getenv
   (.env 里配生效;真实环境变量不覆盖 settings 值)。
"""
from app.api.v1 import chat
from app.core.config import settings
from app.core.config_layer import KNOWN_FLAGS


def test_settings_field_defaults_off():
    """Settings 暴露 HARNESS_MODE,默认 off(.env 缺省时行为不变)。"""
    assert settings.HARNESS_MODE == "off"


def test_harness_mode_in_patch_whitelist():
    """白名单内 → patch.json 可热更新覆盖,dump_effective 可审计。"""
    assert "HARNESS_MODE" in KNOWN_FLAGS


def test_resolve_harness_mode_reads_settings(monkeypatch):
    """解析值来自 settings(.env/patch),不是进程环境变量。"""
    monkeypatch.setattr(chat.settings, "HARNESS_MODE", "shadow")
    # 即使真实环境变量另有其值,也不应覆盖 settings
    monkeypatch.setenv("HARNESS_MODE", "on")
    assert chat._resolve_harness_mode() == "shadow"


def test_resolve_harness_mode_normalizes_case_and_space(monkeypatch):
    monkeypatch.setattr(chat.settings, "HARNESS_MODE", "  ON  ")
    assert chat._resolve_harness_mode() == "on"


def test_resolve_harness_mode_falls_back_off_when_empty(monkeypatch):
    monkeypatch.setattr(chat.settings, "HARNESS_MODE", "")
    assert chat._resolve_harness_mode() == "off"


# ── Harness 安全旋钮接入 settings(Phase 2 切换前置)────────────

def test_harness_limits_readable_from_settings():
    """三个预算旋钮必须能经 .env / patch.json 配置(裸 os.getenv 读不到 .env)。"""
    from app.core.config import settings

    assert hasattr(settings, "HARNESS_RECURSION_LIMIT")
    assert hasattr(settings, "HARNESS_MAX_SECONDS")
    assert hasattr(settings, "HARNESS_SHADOW_TIMEOUT")


def test_harness_limits_defaults_match_approved_budget():
    """默认值与设计文档批准档一致(data 20 步 → 40 递归;墙钟 300s;影子 120s)。"""
    from app.core.config import settings

    assert settings.HARNESS_RECURSION_LIMIT == 40
    assert settings.HARNESS_MAX_SECONDS == 300
    assert settings.HARNESS_SHADOW_TIMEOUT == 120


def test_harness_mode_flag_in_patch_whitelist():
    from app.core.config_layer import KNOWN_FLAGS

    assert "HARNESS_MODE" in KNOWN_FLAGS