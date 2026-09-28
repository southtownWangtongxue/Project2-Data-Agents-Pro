"""
LLM 客户端缓存 + StreamContext channel 透传单元测试（不调 LLM）
"""
import pytest

from app.core import llm
from app.core.llm import get_llm, get_langchain_llm
from app.core.stream import StreamContext


class TestLLMCache:
    """模型实例缓存测试"""

    def setup_method(self):
        llm._openai_clients.clear()
        llm._langchain_models.clear()

    def test_get_llm_cache_hit(self, monkeypatch):
        """相同 (api_key, base_url) 应复用同一 AsyncOpenAI 实例"""
        monkeypatch.setattr(llm.settings, "LLM_API_KEY", "test-key")
        monkeypatch.setattr(llm.settings, "LLM_BASE_URL", "https://example.com/v1")
        c1 = get_llm()
        c2 = get_llm()
        assert c1 is c2

    def test_get_llm_different_base_url(self, monkeypatch):
        """不同 base_url 应创建不同实例"""
        monkeypatch.setattr(llm.settings, "LLM_API_KEY", "test-key")
        monkeypatch.setattr(llm.settings, "LLM_BASE_URL", "https://a.example.com/v1")
        c1 = get_llm()
        monkeypatch.setattr(llm.settings, "LLM_BASE_URL", "https://b.example.com/v1")
        c2 = get_llm()
        assert c1 is not c2

    def test_get_langchain_llm_cache_hit(self, monkeypatch):
        """相同 (model, api_key, base_url) 应复用同一 LangChain model 实例"""
        monkeypatch.setattr(llm.settings, "LLM_API_KEY", "test-key")
        monkeypatch.setattr(llm.settings, "LLM_BASE_URL", "https://example.com/v1")
        monkeypatch.setattr(llm.settings, "LLM_MODEL_NAME", "qwen-test")
        m1 = get_langchain_llm()
        m2 = get_langchain_llm()
        assert m1 is m2


class TestPushTokenChannel:
    """StreamContext.push_token channel 透传测试（单队列 ("token", event) 约定）"""

    @pytest.mark.asyncio
    async def test_default_channel_answer(self):
        """纯文本 token 默认携带 channel=answer"""
        ctx = StreamContext()
        q = ctx.create_queue()
        await ctx.push_token("你好")
        source, event = q.get_nowait()
        assert source == "token"
        assert event == {"type": "token", "content": "你好", "channel": "answer"}

    @pytest.mark.asyncio
    async def test_sql_channel_passthrough(self):
        """channel=sql 应透传到事件 dict（供前端路由到 SQL 卡片）"""
        ctx = StreamContext()
        q = ctx.create_queue()
        await ctx.push_token("SELECT 1", channel="sql")
        source, event = q.get_nowait()
        assert source == "token"
        assert event == {"type": "token", "content": "SELECT 1", "channel": "sql"}

    @pytest.mark.asyncio
    async def test_dict_content_channel_priority(self):
        """dict 形式传入时，dict 内的 channel 优先"""
        ctx = StreamContext()
        q = ctx.create_queue()
        await ctx.push_token({"content": "x", "channel": "sql"})
        source, event = q.get_nowait()
        assert source == "token"
        assert event == {"type": "token", "content": "x", "channel": "sql"}

    @pytest.mark.asyncio
    async def test_push_wraps_as_token_source(self):
        """push() 应统一包装为 ("token", event)，与 graph 的 ("node", evt) 同队列保序"""
        ctx = StreamContext()
        q = ctx.create_queue()
        await ctx.push({"type": "node_started", "agent": "analyst"})
        source, event = q.get_nowait()
        assert source == "token"
        assert event["type"] == "node_started"
