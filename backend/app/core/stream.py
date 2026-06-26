"""
StreamContext —— 图节点内实时 Token 推流上下文

允许 Agent 节点在 LLM 调用期间将 token 实时推送到 SSE 生成器，
实现真正的流式输出（替代 chat.py 中的 _stream_tokens 模拟延迟）。

用法:
    # 在 chat.py 中设置上下文
    from app.core.stream import StreamContext, set_stream_context
    ctx = StreamContext()
    token = set_stream_context(ctx)
    queue = ctx.create_queue()
    # ... 运行图 + 并发读取 queue ...

    # 在 Agent 节点中使用
    from app.core.stream import get_stream_context
    ctx = get_stream_context()
    if ctx.queue:
        async for chunk in stream_response:
            await ctx.push_token(chunk_text)
"""
import asyncio
import contextvars


class StreamContext:
    """流式上下文，封装 asyncio.Queue 供图节点推送 token 事件。

    merge_queue: 直接写入 SSE 主循环队列的快捷通道（绕过 token 队列，用于高优先级事件）。
    """

    def __init__(self):
        self.queue: asyncio.Queue | None = None
        self.merge_queue: asyncio.Queue | None = None

    def create_queue(self) -> asyncio.Queue:
        """创建事件队列并返回。"""
        self.queue = asyncio.Queue()
        return self.queue

    async def push(self, event: dict):
        """推送一个完整的 SSE 事件 dict 到普通队列。"""
        if self.queue:
            await self.queue.put(event)

    async def push_token(self, content: str):
        """推送一个 token 事件。"""
        await self.push({"type": "token", "content": content})

    async def push_priority(self, event: dict):
        """直接推送事件到 merge_queue（绕过 token 队列，用于节点开始等及时事件）。"""
        if self.merge_queue:
            # 使用 ("token", data) 格式与 _forward_tokens 一致，主循环统一处理
            await self.merge_queue.put(("token", event))


# 上下文变量 —— 图节点通过此变量获取当前 StreamContext
_stream_ctx: contextvars.ContextVar[StreamContext] = contextvars.ContextVar(
    "stream_ctx", default=StreamContext()
)


def get_stream_context() -> StreamContext:
    """获取当前协程的 StreamContext 实例。"""
    return _stream_ctx.get()


def set_stream_context(ctx: StreamContext):
    """设置当前协程的 StreamContext 并返回重置 token。"""
    return _stream_ctx.set(ctx)
