"""影子双跑比对测试:legacy 与 harness 双跑,产出比对记录;影子失败不影响主流程。"""
import json

import pytest

from app.harness import shadow


class _FakeAgent:
    """产出固定文本的假 Agent(贴近真实流:updates 模型回合 + messages 流式 token)。"""

    def __init__(self, text="智能体回答", tool_results=0):
        self.text = text
        self.tool_results = tool_results

    async def astream(self, input_data, config, stream_mode=None):
        chunk = type("M", (), {
            "content": self.text,
            "tool_calls": None,
            "tool_call_chunks": None,
            "additional_kwargs": {},
            "reasoning_content": "",
        })()
        # 真实 deepagents:模型回合以 updates.agent 收尾,messages 承载逐 token 流
        yield ("updates", {"agent": {"messages": [chunk]}})
        yield ("messages", (chunk, {"langgraph_node": "agent"}))
        for i in range(self.tool_results):
            tm = type("M", (), {"content": "ok", "name": "run_sql"})()
            yield ("updates", {"tools": {"messages": [tm]}})


@pytest.fixture
def patched(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _FakeAgent())
    monkeypatch.setattr(shadow, "COMPARISON_LOG", tmp_path / "shadow.jsonl")
    yield tmp_path


@pytest.mark.asyncio
async def test_comparison_record_written(patched):
    rec = await shadow.run_shadow_comparison(
        question="统计各表数据量",
        legacy_answer="legacy 回答",
        legacy_metrics={"duration_ms": 1000, "llm_calls": 4, "tools": 5},
    )
    assert rec["question"] == "统计各表数据量"
    assert rec["legacy"]["answer"] == "legacy 回答"
    assert rec["harness"]["answer"] == "智能体回答"
    assert rec["harness"]["llm_rounds"] >= 1
    lines = shadow.COMPARISON_LOG.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["question"] == "统计各表数据量"


@pytest.mark.asyncio
async def test_shadow_failure_returns_none_and_no_log(patched, monkeypatch):
    def boom():
        raise RuntimeError("agent build failed")

    monkeypatch.setattr(shadow, "build_harness_agent", boom)
    rec = await shadow.run_shadow_comparison(
        question="x", legacy_answer="y", legacy_metrics={"duration_ms": 1},
    )
    assert rec is None
    assert not shadow.COMPARISON_LOG.exists()


@pytest.mark.asyncio
async def test_shadow_resolves_provider_from_request_model(patched, monkeypatch):
    """传入请求模型时,先按该模型锁定 provider 再构建 Agent。

    防止影子任务抢在 legacy 流 set_provider 之前构建,误用进程启动时的
    默认 provider(无 key → 401 → 静默失败)。
    """
    seen = {}

    def fake_set_provider(cfg):
        seen["provider_cfg"] = cfg

    monkeypatch.setattr(shadow, "set_provider", fake_set_provider)
    monkeypatch.setattr(
        shadow, "get_config_manager",
        lambda: type("M", (), {"get_llm_config": staticmethod(lambda model: {"model": model})})(),
    )
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _FakeAgent())

    await shadow.run_shadow_comparison(
        question="q", legacy_answer="a", legacy_metrics={}, model="qwen3.7-max",
    )
    assert seen["provider_cfg"] == {"model": "qwen3.7-max"}


@pytest.mark.asyncio
async def test_shadow_without_model_skips_provider_lock(patched, monkeypatch):
    """未传模型(如手动触发)时不动 provider 解析。"""
    called = {"set": False}

    def fake_set_provider(cfg):
        called["set"] = True

    monkeypatch.setattr(shadow, "set_provider", fake_set_provider)
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _FakeAgent())

    await shadow.run_shadow_comparison(question="q", legacy_answer="a", legacy_metrics={})
    assert called["set"] is False


def test_report_aggregates(patched):
    shadow.COMPARISON_LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"question": "q1", "legacy": {"answer": "a"}, "harness": {"answer": "b", "llm_rounds": 2}},
        {"question": "q2", "legacy": {"answer": "c"}, "harness": {"answer": "d", "llm_rounds": 3}},
    ]), encoding="utf-8")
    report = shadow.shadow_report()
    assert report["total"] == 2
    assert report["avg_llm_rounds"] == 2.5
