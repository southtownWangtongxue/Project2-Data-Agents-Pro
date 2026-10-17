"""Harness 模型构建的 provider 配置保真测试(TDD)。

背景:app/deepagent/harness.py 的 _build_model 硬编码 temperature=1.0,
而 provider 配置里每个模型都带 temperature(qwen-flash=0.3)。温度 1.0 下
工具调用行为高度随机——同一问题有时调工具、有时只做自我介绍(实测),
且管理台调温对 Harness 路径完全无效。legacy 各节点用的是 0.0~0.3。
"""
from app.deepagent import harness as dh


def _patch_model(monkeypatch, provider, captured):
    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return "fake-model"

    monkeypatch.setattr(dh, "init_chat_model", fake_init_chat_model)
    monkeypatch.setattr(dh, "get_model_name", lambda: provider.get("model", "m"))
    monkeypatch.setattr(dh, "get_current_provider", lambda: provider)
    monkeypatch.setattr(dh, "_resolve_key_and_base", lambda p=None: ("k", "http://b"))


def test_uses_provider_temperature(monkeypatch):
    """provider 配置的 temperature 必须生效(管理台调温才对 Harness 有用)。"""
    captured = {}
    _patch_model(monkeypatch, {"model": "m", "temperature": 0.3}, captured)
    dh._build_model()
    assert captured["temperature"] == 0.3


def test_falls_back_to_deterministic_default(monkeypatch):
    """provider 未配 temperature 时用确定性默认(0.3),不用 1.0。"""
    captured = {}
    _patch_model(monkeypatch, {"model": "m"}, captured)
    dh._build_model()
    assert captured["temperature"] == 0.3


def test_zero_temperature_is_respected(monkeypatch):
    """temperature=0.0 是合法配置(legacy orchestrator 用的就是 0),不能被当成缺省。"""
    captured = {}
    _patch_model(monkeypatch, {"model": "m", "temperature": 0.0}, captured)
    dh._build_model()
    assert captured["temperature"] == 0.0


def test_still_injects_key_base_and_disables_responses_api(monkeypatch):
    """既有修复不能回退:显式注入 key/base + 禁用 Responses API。"""
    captured = {}
    _patch_model(monkeypatch, {"model": "m", "temperature": 0.3}, captured)
    dh._build_model()
    assert captured["api_key"] == "k"
    assert captured["base_url"] == "http://b"
    assert captured["use_responses_api"] is False
