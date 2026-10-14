import json
from pathlib import Path

from app.core.config_bootstrap import (
    KNOWN_CONFIGS,
    ensure_runtime_configs,
    get_setup_status,
    is_llm_usable,
)


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
    assert ensure_runtime_configs(tmp_path) == []


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
