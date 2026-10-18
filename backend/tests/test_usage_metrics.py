"""usage_metrics 单元测试 —— Token 计量与上下文构成估算（纯函数，无 IO）。

运行：cd backend && python -m pytest tests/test_usage_metrics.py -q
"""
from types import SimpleNamespace

from app.core.usage_metrics import (
    UsageMeter,
    build_usage_event,
    context_breakdown,
    estimate_tokens,
    messages_text,
    tool_defs_text,
)


def _chunk(content="", usage=None, tool_call_chunks=None):
    """构造伪 AIMessageChunk。"""
    return SimpleNamespace(
        content=content,
        tool_call_chunks=tool_call_chunks or [],
        usage_metadata=usage,
    )


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_cjk_one_char_one_token(self):
        # 9 个汉字 ≈ 9 token（「字符数/3」口径会低估到 3）
        assert estimate_tokens("统计各表的数据量呀") == 9

    def test_ascii_four_chars_per_token(self):
        assert estimate_tokens("abcdefgh") == 2  # 8 字符 / 4

    def test_mixed(self):
        # 5 汉字 + 8 ascii = 5 + 2 = 7
        assert estimate_tokens("统计各表的abcdefgh") == 7

    def test_non_string_falls_back_to_str(self):
        assert estimate_tokens({"a": 1}) > 0


class TestUsageMeter:
    def test_observe_single_turn(self):
        m = UsageMeter()
        m.observe_chunk(_chunk(content="你好", usage={
            "input_tokens": 100, "output_tokens": 20,
            "input_token_details": {"cache_read": 40},
        }))
        assert m.input_tokens == 100
        assert m.output_tokens == 20
        assert m.cached_tokens == 40
        assert m.uncached_input_tokens == 60
        assert m.cache_hit_ratio == 0.4

    def test_multi_turn_accumulates(self):
        m = UsageMeter()
        # 回合 1：内容块 + 末块 usage
        m.observe_chunk(_chunk(content="第一回合"))
        m.observe_chunk(_chunk(usage={"input_tokens": 100, "output_tokens": 10}))
        # 回合 2：新内容块出现 → 去重状态重置，末块 usage 再次累加
        m.observe_chunk(_chunk(content="第二回合"))
        m.observe_chunk(_chunk(usage={"input_tokens": 200, "output_tokens": 30}))
        assert m.input_tokens == 300
        assert m.output_tokens == 40

    def test_usage_only_chunk_dedupe(self):
        """网关在末块之外补发 usage-only chunk 时不得重复计数。"""
        m = UsageMeter()
        m.observe_chunk(_chunk(content="正文"))
        m.observe_chunk(_chunk(usage={"input_tokens": 100, "output_tokens": 10}))
        m.observe_chunk(_chunk(usage={"input_tokens": 100, "output_tokens": 10}))  # 补发
        assert m.input_tokens == 100
        assert m.output_tokens == 10

    def test_observe_event_filters_messages_mode(self):
        m = UsageMeter()
        # updates 模式事件不带 usage，忽略
        m.observe_event(("updates", {"agent": {}}))
        # messages 模式：(chunk, metadata) 元组
        m.observe_event(("messages", (_chunk(usage={"input_tokens": 50, "output_tokens": 5}), {})))
        assert m.input_tokens == 50
        assert m.output_tokens == 5

    def test_observe_usage_direct(self):
        """on_llm_end 回调路径（legacy）。"""
        m = UsageMeter()
        m.observe_usage(80, 12, 8)
        assert (m.input_tokens, m.output_tokens, m.cached_tokens) == (80, 12, 8)

    def test_zero_input_no_div_error(self):
        m = UsageMeter()
        assert m.cache_hit_ratio == 0.0


class TestContextBreakdown:
    def test_breakdown_and_pct(self):
        ctx = context_breakdown(
            system_prompt="系统提示词" * 100,   # 500 汉字 = 500 tok
            tool_defs="abcdefghij" * 40,        # 400 ascii = 100 tok
            messages="对话消息" * 50,            # 200 汉字 = 200 tok
            window=1000,
        )
        assert ctx["system_prompt"] == 500
        assert ctx["tool_defs"] == 100
        assert ctx["messages"] == 200
        assert ctx["used_pct"] == 80

    def test_pct_capped_at_100(self):
        ctx = context_breakdown(system_prompt="超" * 5000, window=100)
        assert ctx["used_pct"] == 100


class TestMessagesAndTools:
    def test_messages_text_dict_and_object(self):
        obj = SimpleNamespace(content="对象消息")
        text = messages_text([{"role": "user", "content": "字典消息"}, obj])
        assert "字典消息" in text and "对象消息" in text

    def test_tool_defs_text(self):
        tool = SimpleNamespace(name="run_sql", description="执行 SQL", args_schema=None)
        assert "run_sql" in tool_defs_text([tool])
        assert tool_defs_text([]) == ""
        assert tool_defs_text(None) == ""


class TestBuildUsageEvent:
    def test_event_shape(self):
        m = UsageMeter()
        m.observe_chunk(_chunk(usage={"input_tokens": 100, "output_tokens": 20,
                                      "input_token_details": {"cache_read": 25}}))
        ev = build_usage_event(
            m,
            context=context_breakdown(system_prompt="系统提示", window=1000),
            turns=2, steps=5,
        )
        assert ev["type"] == "usage"
        assert ev["input_tokens"] == 100
        assert ev["output_tokens"] == 20
        assert ev["cached_tokens"] == 25
        assert ev["total_tokens"] == 120
        assert ev["turns"] == 2 and ev["steps"] == 5
        assert ev["estimated"] is True
        assert ev["context"]["window"] == 1000
