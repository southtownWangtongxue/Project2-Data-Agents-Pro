"""
StreamContext —— 图节点内实时事件推送上下文（阶段二 2.1 精简版）

所有事件源（graph 节点完成事件、节点内 push 的 token/reasoning/node_started）
写入同一个 asyncio.Queue，由 chat.py 主循环单消费者顺序读取。
单队列天然保序：同一节点内先 push 的 token 必先于该节点的完成事件到达主循环，
不再需要旧版的双队列 + 0.1s 轮询 + drain 机制。

用法:
    # 在 chat.py 中设置上下文
    from app.core.stream import StreamContext, set_stream_context
    ctx = StreamContext()
    queue = ctx.create_queue()
    set_stream_context(ctx)
    # ... 运行图 + await queue.get() 单消费者循环 ...
    # 队列元素为 (source, data) 元组：节点内 push 的事件为 ("token", event_dict)，
    # 与 chat.py _forward_graph 的 ("node", evt) 等约定一致

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
    """流式上下文，封装单个 asyncio.Queue 供图节点推送 SSE 事件。"""

    def __init__(self):
        self.queue: asyncio.Queue | None = None

    def create_queue(self) -> asyncio.Queue:
        """创建事件队列并返回。"""
        self.queue = asyncio.Queue()
        return self.queue

    async def push(self, event: dict):
        """推送一个完整的 SSE 事件 dict 到队列。

        原 push_priority（merge_queue 快捷通道）语义已合并于此：
        单队列单消费者天然保序，优先级通道不再需要。
        """
        if self.queue:
            await self.queue.put(("token", event))

    async def push_token(self, content: str | dict, channel: str = "answer"):
        """推送一个 token 事件。

        content 支持纯文本或完整事件 dict；
        channel 默认 "answer"（正文流式），SQL 生成传 "sql"，
        前端按 channel 路由（sql → SQL 卡片流式追加），字段透传到 SSE 输出。
        """
        if isinstance(content, dict):
            event = {"type": "token", **content}
            event.setdefault("channel", channel)
        else:
            event = {"type": "token", "content": content, "channel": channel}
        await self.push(event)


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
