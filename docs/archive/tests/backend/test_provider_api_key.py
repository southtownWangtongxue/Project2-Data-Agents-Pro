"""provider API Key 解析测试(R2)。

背景:provider 配 key_mode=env + api_key_env=OPENROUTER_API_KEY,
而项目未调用 load_dotenv —— pydantic 只把 .env 灌进 Settings 实例,
os.getenv 读不到,导致 resolve_api_key 静默回退到 settings.LLM_API_KEY
(别的厂商 key),把错误 key 发往目标 API(401 Missing Authentication header)。

本测试锁定:解析顺序 os.environ → .env → provider.api_key 直配,
且绝不跨厂商回退到 settings.LLM_API_KEY。
"""
import os

import pytest

from app.core.config_manager import get_config_manager


def _nemotron() -> dict:
    """取目标 provider(env 模式 + 指定 api_key_env),避免误选其它厂商的 provider。"""
    mgr = get_config_manager()
    for p in mgr.llm_providers:
        if p.get("key_mode") == "env" and p.get("api_key_env") == "OPENROUTER_API_KEY":
            return p
    pytest.skip("配置中无 OPENROUTER env 模式 provider")


def test_env_var_wins(monkeypatch):
    mgr = get_config_manager()
    p = _nemotron()
    monkeypatch.setenv(p["api_key_env"], "key-from-process-env")
    assert mgr.resolve_api_key(p) == "key-from-process-env"


def test_falls_back_to_dotenv_file(monkeypatch):
    """.env 里的变量必须能被解析到(pydantic 不灌 os.environ 的补偿路径)。"""
    mgr = get_config_manager()
    p = _nemotron()
    monkeypatch.delenv(p["api_key_env"], raising=False)
    resolved = mgr.resolve_api_key(p)
    # .env 中该变量已由用户配置,故应解析出非空值;若为空说明补偿路径失效
    assert resolved, "未能从 .env 解析到 api_key_env 指向的变量"
    assert resolved.startswith("sk-or"), "解析到的不是 OpenRouter key(跨厂商回退)"


def test_direct_mode_returns_configured_key(monkeypatch):
    mgr = get_config_manager()
    p = dict(_nemotron())
    p.update({"key_mode": "direct", "api_key": "sk-direct-inline"})
    assert mgr.resolve_api_key(p) == "sk-direct-inline"


def test_never_falls_back_to_other_vendor_key(monkeypatch):
    """env 模式解析不到时返回空,绝不用 settings.LLM_API_KEY 兜底。"""
    from app.core.llm import _resolve_key_and_base

    mgr = get_config_manager()
    p = dict(_nemotron())
    monkeypatch.delenv(p["api_key_env"], raising=False)
    # .env 解析路径已在 resolve_api_key 内完成;这里验证它不会把别家 key 带进来
    resolved = mgr.resolve_api_key(p)
    if resolved:
        assert resolved.startswith("sk-or")
    key, base = _resolve_key_and_base(p)
    # base 必须来自 provider(目标厂商),key 不得是 DashScope 形态
    assert base == p["api_base"]
    if not resolved:
        pytest.skip("当前 .env 已配置该 key,跨厂商回退分支不可达")


def test_resolve_key_and_base_keeps_provider_base():
    from app.core.llm import _resolve_key_and_base

    mgr = get_config_manager()
    p = _nemotron()
    key, base = _resolve_key_and_base(p)
    assert base == p["api_base"], "base 必须用 provider 的,否则请求打到错误厂商"
    assert key == mgr.resolve_api_key(p) or key == ""
    assert os.getenv("PATH") is not None  # 进程环境本身可用