"""
聊天接口 —— SSE 流式对话

提供基于 Server-Sent Events 的流式对话能力。
后端通过 LangGraph 的 astream() 方法监听各 Agent 节点的
状态变更，将关键信息实时推送给前端（状态、SQL、结果、
分析洞察、图表配置等）。
"""
import contextvars
import json
import logging
import os as _os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langgraph.errors import GraphInterrupt, GraphRecursionError
from langgraph.types import Command

from app.core import hitl
from app.api.deps import get_current_user
from app.graph.workflow import get_graph, get_graph_async, use_deep_agent, get_deep_agent
from app.core.config import settings
from app.core.config_manager import get_config_manager
from app.agents.title_generator import generate_node_title
from app.agents.question_suggester import generate_question_suggestions, get_cached_suggestions
from app.agents.schema_agent import get_table_schemas
from app.db.session import get_engine
from app.utils.json_encoder import CustomEncoder
from app.utils.log_utils import log
from app.core.stream import StreamContext, set_stream_context, get_stream_context
from app.core.event_sourcing import (
    SessionEventStore,
    EventType,
    event_sourcing_enabled,
    turn_event_enabled,
    check_history_invariant,
    MAX_RESULT_ROWS,
)
from app.core.compaction import compact_history
from app.core.agent_loop import AgentLoopRunner, agent_loop_enabled, agent_loop_shadow
from app.core.stream_protocol import SSEEventType, make_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
router = APIRouter(prefix="/chat", tags=["chat"])

# ── SSE step_id 上下文（阶段二 2.2）──
# 主循环按 graph 节点分配自增 step_id（同轮次内从 1 开始）并设置到此上下文，
# _sse_event 统一注入到该节点产生的所有事件；done/title/thread_id 不携带。
_sse_step_id: contextvars.ContextVar[int] = contextvars.ContextVar("sse_step_id", default=0)
_STEPLESS_TYPES = {"thread_id", "done", "title"}


def _resolve_enabled_provider(model: str | None = None) -> dict | None:
    """
    解析 LLM provider，强制走「前端模型列表」(llm_providers.json 中 enabled 的 provider)。

    规则（与聊天流 _inject_and_set_provider 一致，但绝不回退到 .env 的 settings）：
        1. model 命中 enabled provider → 返回该 provider
        2. model 未命中/为空 → 返回第一个 enabled provider（保证仍走前端列表）
        3. 没有任何 enabled provider → 返回 None（调用方应降级，而不是悄悄用 env）
    """
    cm = get_config_manager()
    if model:
        provider = cm.get_llm_config(model)
        if provider and provider.get("enabled", True):
            return provider
    # 回退：第一个 enabled provider（注意：ConfigManager 的属性是 llm_providers，为 list[dict]）
    for p in cm.llm_providers:
        if p.get("enabled", True):
            return p
    return None


# ================================================================
# 数据模型
# ================================================================


class ChatMessage(BaseModel):
    """单条对话消息"""
    role: str = Field(..., description="消息角色: user / assistant / system")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """聊天请求体"""
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="对话历史消息列表",
    )
    stream: bool = Field(
        default=True,
        description="是否启用 SSE 流式响应",
    )
    thread_id: str | None = Field(
        default=None,
        description="会话 thread_id（同一会话多轮对话复用，新建会话时不传）",
    )
    mode: str = Field(
        default="data",
        description="工作模式: data（数据分析）| report（研究报告）| doc（文档智读）| task（通用任务）",
        pattern="^(data|report|doc|task)$",
    )
    web_search: bool = Field(
        default=False,
        description="是否启用联网搜索（百度搜索 API）",
    )
    model: str | None = Field(
        default=None,
        description="模型 provider id（对应 LLM 配置中的 id）；为空则使用默认 provider。界面切换模型时动态路由实际调用",
    )


# ================================================================
# 内部辅助函数
# ================================================================

import asyncio as _asyncio

def _extract_interrupt_data(evt) -> dict:
    """从 updates 模式的 __interrupt__ 节点事件中提取审批载荷(sql/reason)。"""
    raw = evt.get("__interrupt__", evt) if isinstance(evt, dict) else evt
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    payload = getattr(raw, "value", raw)
    if not isinstance(payload, dict):
        payload = {"reason": str(payload or "")}
    return payload


def _sse_event(data: dict) -> str:
    """
    构造 SSE 事件字符串（符合 Server-Sent Events 规范）。

    阶段二 2.2：上下文中已有 step_id 时统一注入（done/title/thread_id 等
    无步骤归属的事件除外），前端按 step_id 分组渲染步骤卡片。

    参数:
        data: 事件数据字典，将被 JSON 序列化

    返回:
        形如 "data: {...}\n\n" 的 SSE 事件字符串
    """
    sid = _sse_step_id.get()
    if sid and data.get("type") not in _STEPLESS_TYPES and "step_id" not in data:
        data["step_id"] = sid
    return f"data: {json.dumps(data, ensure_ascii=False, cls=CustomEncoder)}\n\n"


def _resolve_harness_mode() -> str:
    """解析 Harness 主循环模式(off/shadow/on)。

    读 settings(而非裸 os.getenv):.env 由 pydantic 加载进 settings,
    项目无 load_dotenv,os.getenv 读不到;configs/patch.json 的白名单
    热更新同样作用于 settings——两者都因此生效,且默认 off 零影响。
    """
    return str(getattr(settings, "HARNESS_MODE", "") or "off").strip().lower()


# ── 流式任务注册表（阶段2 B3：支持停止生成）──────────────
# thread_id → asyncio.Task，供 POST /chat/cancel 取消运行中的 SSE 流
_active_stream_tasks: dict[str, _asyncio.Task] = {}
# thread_id → asyncio.Event 停止标志：cancel 时 set，生成器检测后正常结束 SSE
_active_stream_events: dict[str, _asyncio.Event] = {}
# 后台影子双跑任务强引用集(asyncio 官方模式:防任务被 GC 中途取消)
_shadow_tasks: set[_asyncio.Task] = set()


async def _wrap_cancellable(inner_stream):
    """
    包装内部 SSE 流生成器：

    - 解析内部流首个 ``thread_id`` 事件，注册运行任务与停止标志
    - 检测到停止标志时提前 break（正常结束 SSE 流，前端收到 EOF 触发 onDone）
    - 流结束 / 异常时在 finally 中反注册
    - 供 ``POST /chat/cancel`` 通过标志 + task.cancel() 中断生成
    """
    task = _asyncio.current_task()
    registered_key: str | None = None
    stop_event: _asyncio.Event | None = None
    try:
        async for chunk in inner_stream:
            if registered_key is None and isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    payload = json.loads(chunk[len("data: "):].strip())
                    if payload.get("type") == "thread_id":
                        tid = payload.get("thread_id")
                        if tid:
                            _active_stream_tasks[tid] = task
                            stop_event = _asyncio.Event()
                            _active_stream_events[tid] = stop_event
                            registered_key = tid
                except Exception:
                    pass
            # 停止生成：提前 break，SSE 流正常结束（前端收到 EOF → onDone）
            if registered_key and stop_event and stop_event.is_set():
                break
            yield chunk
    finally:
        if registered_key:
            _active_stream_tasks.pop(registered_key, None)
            _active_stream_events.pop(registered_key, None)


async def _stream_tokens(text: str, delay: float = 0.0):
    """
    将文本分块流式输出为 token SSE 事件。

    按字符分块（每块 1~2 字符），实现类 ChatGPT 的逐字输出效果。
    用于在 analysis/text 等大段文本推送时提供更好的用户体验。

    参数:
        text: 待流式输出的文本内容
        delay: 每个分块之间的延迟（秒），默认 0 以最大化输出速度

    产出:
        token 类型的 SSE 事件字符串
    """
    chunk_size = 2
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        yield _sse_event({"type": "token", "content": chunk})
        if delay > 0:
            await _asyncio.sleep(delay)


def _thinking_event(agent: str, phase: str, content: str = "") -> str:
    """
    构造 thinking SSE 事件，展示 Agent 推理过程。

    参数:
        agent: Agent 名称，如 "orchestrator", "sql_coder", "analyst"
        phase: 阶段描述，如 "classifying", "generating", "analyzing"
        content: 详细思考内容（可选）

    返回:
        thinking 类型的 SSE 事件字符串
    """
    return _sse_event({
        "type": "thinking",
        "agent": agent,
        "phase": phase,
        "content": content,
    })


def _tool_event(event_type: str, tool_name: str, **kwargs) -> str:
    """
    构造工具调用/结果 SSE 事件。

    参数:
        event_type: "tool_call" 或 "tool_result"
        tool_name: 工具/Agent 名称
        **kwargs: 额外字段（args, result 等）

    返回:
        tool_call 或 tool_result 类型的 SSE 事件字符串
    """
    payload = {"type": event_type, "tool_name": tool_name, **kwargs}
    return _sse_event(payload)


def _error_event(message: str, code: str = "UNKNOWN", recoverable: bool = False) -> str:
    """
    构造带错误码的 error SSE 事件。

    参数:
        message: 用户友好的错误描述
        code: 错误码（LLM_TIMEOUT / SQL_EXEC_FAILED / NETWORK_ERROR / UNKNOWN）
        recoverable: 是否可重试

    返回:
        error 类型的 SSE 事件字符串
    """
    return _sse_event({
        "type": "error",
        "error": message,
        "code": code,
        "recoverable": recoverable,
    })


# ================================================================
# SSE 流式对话生成器
# ================================================================


async def _stream_chat(question: str, user_name: str, history: list[dict] | None = None, existing_thread_id: str | None = None, model: str | None = None, mode: str = "data", web_search: bool = False):
    """
    SSE 流式对话生成器 —— 异步生成 SSE 事件流。

    执行流程：
        1. 创建 LangGraph 执行上下文（session thread_id 用于 MySQL 分组，run_id 用于 Redis checkpoint）
        2. 通过 graph.astream() 监听各节点状态变更
        3. 根据节点名称分发对应的 SSE 事件（status / sql / result /
           analysis / chart / error / done）

    参数:
        question: 用户最新输入的自然语言问题
        user_name: 当前登录用户名（用于 thread_id 格式和用户隔离）
        history: 对话历史消息列表 [{"role": "...", "content": "..."}, ...]
        existing_thread_id: 前端传入的会话 thread_id（多轮复用，新建会话时为 None）

    产出:
        SSE 事件字符串，每个事件一行 "data: {...}\n\n"
    """
    from app.graph.mode_router import get_graph as get_graph_by_mode
    from app.core.llm import set_provider, describe_route
    from app.core.config_manager import get_config_manager
    # 解析并锁定当前模型 provider（动态路由：界面所选模型 → 实际 API 调用）
    provider = get_config_manager().get_llm_config(model)
    set_provider(provider)
    logger.info("[LLM路由] 实际调用: %s", describe_route())

    graph = get_graph_by_mode(mode)

    # 构造初始状态（含多轮对话历史 + 模式参数，供 Agent 参考上下文）
    initial_state = {
        "user_question": question,
        "messages": history or [],
        "mode": mode,
        "enable_web_search": web_search,
    }

    # 会话级 thread_id：多轮对话复用，新建会话生成新的
    session_thread_id = existing_thread_id if existing_thread_id else f"{user_name}:{uuid.uuid4()}"
    # 执行级 run_id：每次调用都生成新的，确保 LangGraph 从初始状态开始
    run_id = f"{user_name}:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": run_id}}

    # ── 多轮对话：恢复上一轮的查询数据（用于 chart_interaction 快捷路径）──
    if existing_thread_id:
        last_state = await _get_last_run_state(session_thread_id)
        if last_state:
            initial_state["_cached_query_result"] = last_state.get("query_result", [])
            initial_state["_cached_query_columns"] = last_state.get("query_columns", [])
            logger.info("[chat] 已缓存上轮查询数据: %d 行 %d 列",
                        len(initial_state["_cached_query_result"]),
                        len(initial_state["_cached_query_columns"]))

    # ── 流式上下文：Agent 节点可通过 StreamContext 实时推送事件 ──
    # 阶段二 2.1：单队列单消费者——graph 节点事件与节点内 push 写入同一队列，天然保序
    stream_ctx = StreamContext()
    stream_queue = stream_ctx.create_queue()
    _ctx_token = set_stream_context(stream_ctx)

    # 提前声明 merge_queue（下面会用到），让 StreamContext 可以直接写入优先级事件
    merge_queue: _asyncio.Queue[tuple[str, object]] = _asyncio.Queue()
    stream_ctx.merge_queue = merge_queue  # ← 关键：连接快捷通道

    # DEF-009：节点级耗时埋点（节点事件入口统一计时，供性能画像使用）
    import time as _time
    _run_t_start = _time.monotonic()
    _node_t_prev = _run_t_start
    _node_timings: list[str] = []

    logger.info("[chat] _stream_chat: session_thread_id=%s (reused=%s), run_id=%s, question=%s",
                session_thread_id, bool(existing_thread_id), run_id, question[:80])

    # 推送 session thread_id 给前端（多轮复用，让前端知道归属同一会话）
    yield _sse_event({"type": "thread_id", "thread_id": session_thread_id})

    # 创建/更新会话元数据记录（新建与复用均走 upsert，顺带刷新 updated_at 时间戳）
    await _upsert_chat_session(session_thread_id, user_name)

    # 用于标题生成的数据收集
    collected_analysis = ""     # 收集分析/回答文本
    collected_sql = ""          # 收集 SQL 语句（辅助标题推断）
    # DEF-009：标题 LLM 调用提前到 analyst 节点完成时启动（与 reporter/chart 并行），
    # 输入与原 finish 时刻完全一致，仅消除串行等待（实测节省 ~7.5s）
    title_task: _asyncio.Task | None = None

    # 多轮对话：根据已有节点数确定本轮 node_index
    if existing_thread_id:
        node_index = await _count_nodes(session_thread_id)
    else:
        node_index = 0

    # ── 事件溯源双写（Phase 1）：feature flag 开启时，记录业务事件到 session_events ──
    es_enabled = event_sourcing_enabled()

    async def _track(etype: str, role: str | None = None, content: str = "", payload: dict | None = None):
        """在事件溯源开启时追加一条事件（失败不阻断主流程）。"""
        if es_enabled:
            await SessionEventStore.append(
                session_thread_id, etype,
                run_id=run_id, node_index=node_index,
                role=role, content=content, payload=payload,
            )

    if es_enabled:
        await _track(EventType.USER_MESSAGE, role="user", content=question)
        # R16：turn 边界事件（node_index 即轮次标识；事件 id 升序即 step 序）
        if turn_event_enabled():
            await _track(EventType.TURN_START, role="system", payload={
                "turn_index": node_index, "question_preview": question[:100],
            })

    try:
        # ── 单队列单消费者（阶段二 2.1）：graph 事件与节点内 push 同队列，天然保序 ──

        async def _forward_graph():
            try:
                logger.info("[SSE-GRAPH] graph.astream() 开始")
                event_count = 0
                resume_cmd = None
                # 第一段:初始运行(可能在 security 节点因高危 SQL 中断等待审批)
                async for evt in graph.astream(initial_state, config, stream_mode="updates"):
                    event_count += 1
                    logger.info(f"[SSE-GRAPH] 收到图事件 #{event_count} keys: {list(evt.keys())}")
                    if isinstance(evt, dict) and "__interrupt__" in evt:
                        # ── HITL 流内等待(对话内审批)──
                        # updates 模式下中断以 __interrupt__ 节点事件投递:
                        # 通知主循环发 approval_required(流保持打开),流内等待决策,
                        # 通过后 Command(resume) 恢复并续流,拒绝则终止。
                        interrupt_data = _extract_interrupt_data(evt)
                        logger.info("[SSE-GRAPH] 审批中断,流内等待决策(≤300s): %s", str(interrupt_data)[:120])
                        await stream_queue.put(("approval", interrupt_data))
                        decision = await hitl.wait_for(session_thread_id, timeout=300)
                        if decision is None:
                            decision = {"approved": False, "comment": "审批超时（5 分钟），自动拒绝"}
                        if decision.get("approved"):
                            logger.info("[SSE-GRAPH] 审批通过,恢复图执行")
                            resume_cmd = Command(resume=decision)
                            break
                        logger.info("[SSE-GRAPH] 审批拒绝,终止流程")
                        await stream_queue.put(("rejected", decision))
                        return
                    # 节点内 push 的 token 已先于本事件入队，直接入队即可保序
                    await stream_queue.put(("node", evt))
                # 恢复段:审批通过后从断点继续执行(事件经同一主循环处理)
                if resume_cmd is not None:
                    async for evt in graph.astream(resume_cmd, config, stream_mode="updates"):
                        event_count += 1
                        await stream_queue.put(("node", evt))
                logger.info(f"[SSE-GRAPH] graph.astream() 完成, 共 {event_count} 个事件")
            except GraphInterrupt as gi:
                # 异常路径兜底(中断以异常抛出时同样走流内等待)
                interrupt_data = _extract_interrupt_data(gi.args[0] if gi.args else {})
                await stream_queue.put(("approval", interrupt_data))
                decision = await hitl.wait_for(session_thread_id, timeout=300)
                if decision is None:
                    decision = {"approved": False, "comment": "审批超时（5 分钟），自动拒绝"}
                if decision.get("approved"):
                    try:
                        async for evt in graph.astream(Command(resume=decision), config, stream_mode="updates"):
                            await stream_queue.put(("node", evt))
                    except Exception as exc:
                        logger.exception("[SSE] 审批恢复执行异常")
                        await stream_queue.put(("error", exc))
                else:
                    await stream_queue.put(("rejected", decision))
            except Exception as exc:
                logger.exception("[SSE] Graph 流式执行异常")
                await stream_queue.put(("error", exc))
            finally:
                hitl.cancel(session_thread_id)
                await stream_queue.put(("done", None))

        graph_task = _asyncio.create_task(_forward_graph())

        # 阶段二 2.2：step_id 分配——node_started（节点开始）与节点完成事件双入口，
        # 同一节点的所有事件归入同一步骤，同轮次内自增从 1 开始
        step_counter = 0
        node_steps: dict[str, int] = {}

        def _next_step(agent: str) -> int:
            nonlocal step_counter
            step_counter += 1
            node_steps[agent] = step_counter
            return step_counter

        # 主循环：单消费者顺序读取队列，即时产出 SSE 事件
        while True:
            try:
                # 15s 无事件时发送 SSE 注释行心跳（": ping"），防代理空闲断连；前端无需处理
                source, data = await _asyncio.wait_for(stream_queue.get(), timeout=15)
            except _asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            logger.info(f"[SSE-LOOP] 事件源: {source}")

            if source == "done":
                logger.info("[SSE-LOOP] 收到 done 信号, 退出主循环")
                break

            if source == "error":
                exc = data
                yield _error_event(
                    f"图流执行异常: {str(exc)}",
                    code="GRAPH_STREAM_FAILED",
                    recoverable=True,
                )
                break

            if source == "approval":
                # ── HITL:审批卡下发,流保持打开(等待期间由 15s 心跳维持连接)──
                interrupt_data = data if isinstance(data, dict) else {}
                yield _sse_event({
                    "type": "approval_required",
                    "thread_id": session_thread_id,
                    "question": question,
                    "sql": interrupt_data.get("sql", "") if isinstance(interrupt_data, dict) else "",
                    "reason": interrupt_data.get("reason", "") if isinstance(interrupt_data, dict) else "",
                })
                continue

            if source == "rejected":
                decision = data if isinstance(data, dict) else {}
                yield _sse_event({
                    "type": "status",
                    "content": f"该高危操作已被拒绝，流程终止（{decision.get('comment') or '无审批意见'}）",
                    "approval_state": "rejected",
                })
                continue

            if source == "token":
                # 节点内推送的预组表事件（token/reasoning/node_started 等），直接产出
                if data.get("type") == "node_started":
                    # 节点开始：分配新 step_id（同节点重跑如质量打回重试时各为一步），
                    # 完成事件经 node_steps 映射归入对应步骤
                    agent = data.get("agent", "")
                    _sse_step_id.set(_next_step(agent))
                yield _sse_event(data)
                continue

            # source == "node": 处理节点完成事件
            for node_name, state_update in data.items():
                # ── DEF-009：节点级耗时埋点（间隔=本节点自身耗时）──
                _now = _time.monotonic()
                _node_timings.append(f"{node_name}={_now - _node_t_prev:.1f}s")
                logger.info("[PERF] 节点 %s 完成: 自身 %.2fs / 累计 %.2fs",
                            node_name, _now - _node_t_prev, _now - _run_t_start)
                _node_t_prev = _now
                # 阶段二 2.2：兜底分配 step_id（节点未推送 node_started 时）
                _sse_step_id.set(node_steps.get(node_name) or _next_step(node_name))
                logger.info(f"[SSE-LOOP] 处理节点事件: {node_name}")

                # ── clarify_plan: 意图澄清 + 执行计划（合并单次LLM调用）──────
                if node_name == "clarify_plan":
                    logger.info("[SSE] clarify_plan 阶段完成")
                    is_clear = state_update.get("is_clear", True)
                    clarification = state_update.get("clarification_text", "")
                    options = state_update.get("clarification_options", [])
                    intent = state_update.get("intent", "query_data")
                    plan_steps = state_update.get("plan_steps", [])

                    if not is_clear and clarification:
                        # 意图模糊：推送追问卡片给前端
                        logger.info(f"[SSE] 意图模糊，推送追问: {clarification[:80]}")
                        yield _sse_event({
                            "type": "clarification",
                            "text": clarification,
                            "options": options,
                        })
                        await _track(EventType.CLARIFICATION, role="system",
                                     content=clarification, payload={"options": options})
                    else:
                        # 意图明确：推送计划和思考
                        intent_labels = {
                            "query_data": "数据查询",
                            "chart_interaction": "图表操作",
                            "ask_help": "帮助咨询",
                            "write_data": "数据写入",
                            "other_questions": "其他问题",
                        }
                        step_names = [s.get("step", "?") for s in plan_steps]

                        yield _thinking_event("clarify_plan", "planning",
                                              f"分析意图并生成执行计划: {intent_labels.get(intent, intent)}")
                        yield _sse_event({
                            "type": "plan",
                            "intent": intent,
                            "intent_label": intent_labels.get(intent, intent),
                            "steps": step_names,
                            "chart_suitable": state_update.get("chart_suitable", False),
                        })
                        await _track(EventType.PLAN, role="system", payload={
                            "intent": intent,
                            "intent_label": intent_labels.get(intent, intent),
                            "steps": step_names,
                            "chart_suitable": state_update.get("chart_suitable", False),
                        })

                # ── clarifier: 意图澄清（旧版兼容）──────────
                elif node_name == "clarifier":
                    logger.info("[SSE] clarifier 阶段完成")
                    is_clear = state_update.get("is_clear", True)
                    clarification = state_update.get("clarification_text", "")
                    options = state_update.get("clarification_options", [])

                    if not is_clear and clarification:
                        logger.info(f"[SSE] 意图模糊，推送追问: {clarification[:80]}")
                        yield _sse_event({
                            "type": "clarification",
                            "text": clarification,
                            "options": options,
                        })
                    else:
                        yield _thinking_event("clarifier", "analyzing", "分析用户意图...")

                # ── planner: 执行计划生成（旧版兼容）───────
                elif node_name == "planner":
                    logger.info("[SSE] planner 阶段完成")
                    intent = state_update.get("intent", "query_data")
                    intent_labels = {
                        "query_data": "数据查询",
                        "chart_interaction": "图表操作",
                        "ask_help": "帮助咨询",
                        "write_data": "数据写入",
                        "other_questions": "其他问题",
                    }
                    plan_steps = state_update.get("plan_steps", [])
                    step_names = [s.get("step", "?") for s in plan_steps]

                    yield _thinking_event("planner", "planning", f"生成执行计划: {intent_labels.get(intent, intent)}")
                    yield _sse_event({
                        "type": "plan",
                        "intent": intent,
                        "intent_label": intent_labels.get(intent, intent),
                        "steps": step_names,
                        "chart_suitable": state_update.get("chart_suitable", False),
                    })

                # ── misc_agent: 杂项处理 ──────────
                elif node_name == "misc_agent":
                    yield _thinking_event("misc_agent", "processing", "处理请求...")
                    logger.info("[SSE] misc_agent 阶段")
                    content = state_update.get("analysis_text", "")
                    if content:
                        collected_analysis = str(content)[:200]  # 收集用于标题生成
                        logger.info(f"[SSE] misc_agent 结果={content[:80]}")
                        yield _tool_event("tool_call", "misc_agent", args={"question": question[:80]})
                        # misc_agent() 内部已通过 StreamContext.push_token 逐 token 推送，
                        # 此处不再二次 _stream_tokens，避免 token 重复推送导致 loading 感知翻倍（遗留1修复）
                        yield _tool_event("tool_result", "misc_agent", result=content[:200])
                        await _track(EventType.TOOL_CHAIN, role="tool",
                                     content=str(content)[:200],
                                     payload={"name": "misc_agent", "status": "done"})
                        await _track(EventType.ANALYSIS, role="assistant", content=str(content))
                    else:
                        # 尝试从 messages 中提取（兼容旧格式）
                        msg = state_update.get('messages')
                        if msg:
                            try:
                                content = msg[-1].content
                            except AttributeError:
                                content = msg[-1].get("content", "") if isinstance(msg[-1], dict) else ""
                            if content:
                                collected_analysis = str(content)[:200]
                                yield _tool_event("tool_call", "misc_agent", args={"question": question[:80]})
                                async for token in _stream_tokens(content):
                                    yield token
                                yield _tool_event("tool_result", "misc_agent", result=content[:200])
                                await _track(EventType.TOOL_CHAIN, role="tool",
                                             content=str(content)[:200],
                                             payload={"name": "misc_agent", "status": "done"})
                                await _track(EventType.ANALYSIS, role="assistant", content=str(content))
                # ── schema_agent: 加载表结构 ──────────────
                elif node_name == "schema_agent":
                    yield _thinking_event("schema_agent", "loading_schema", "加载数据表结构...")
                    error = state_update.get("error_message", "")
                    if error:
                        logger.warning(f"[SSE] schema_agent 错误: {error}")
                        yield _error_event(error, code="SCHEMA_LOAD_FAILED", recoverable=True)

                # ── sql_coder: SQL 生成 ──────────────────
                elif node_name == "sql_coder":
                    yield _thinking_event("sql_coder", "generating", "正在生成SQL查询...")
                    error = state_update.get("error_message", "")
                    if error:
                        logger.warning(f"[SSE] sql_coder 错误: {error}")
                        yield _error_event(error, code="SQL_GENERATE_FAILED", recoverable=True)
                    else:
                        sql = state_update.get("generated_sql", "")
                        if sql:
                            collected_sql = sql  # 收集用于标题生成
                            logger.info(f"[SSE] 推送 SQL: {sql[:80]}")
                            yield _sse_event({
                                "type": "sql",
                                "content": sql,
                            })
                            await _track(EventType.SQL, role="assistant", content=sql)

                # ── security: SQL 安全审核 ───────────────
                elif node_name == "security":
                    logger.info("[SSE] security 阶段完成")
                    risk_level = state_update.get("risk_level", "")
                    yield _thinking_event("security", "auditing", f"安全审核中, 风险等级: {risk_level or '评估中'}")

                # ── execute_sql: SQL 执行 ────────────────
                elif node_name == "execute_sql":
                    yield _thinking_event("execute_sql", "executing", "执行SQL查询...")
                    # 推送执行错误（如有）
                    error = state_update.get("error_message", "")
                    if error:
                        logger.warning(f"[SSE] SQL 执行异常: {error}")
                        yield _error_event(error, code="SQL_EXEC_FAILED", recoverable=False)
                        await _track(EventType.ERROR, role="assistant", content=error)

                    # 推送查询结果
                    results = state_update.get("query_result", [])
                    columns = state_update.get("query_columns", [])
                    if results:
                        logger.info(
                            "[SSE] 推送查询结果: %d 行 %d 列",
                            len(results),
                            len(columns),
                        )
                        yield _tool_event("tool_call", "execute_sql", rows=len(results), cols=len(columns))
                        yield _sse_event({
                            "type": "result",
                            "data": results,
                            "columns": columns,
                        })
                        yield _tool_event("tool_result", "execute_sql", row_count=len(results))
                        await _track(EventType.TOOL_CHAIN, role="tool",
                                     content=f"返回 {len(results)} 条记录",
                                     payload={"name": "execute_sql", "status": "done",
                                              "result": f"返回 {len(results)} 条记录"})
                        await _track(EventType.RESULT, role="assistant", payload={
                            "data": results[:MAX_RESULT_ROWS],
                            "columns": columns,
                        })

                # ── quality_gate: ReAct 质量评估（Phase E.9）──
                elif node_name == "quality_gate":
                    quality = state_update.get("query_quality", "good")
                    feedback = state_update.get("quality_feedback", "")
                    logger.info(f"[SSE] quality_gate 评估完成: quality={quality}")

                    yield _thinking_event("quality_gate", "evaluating", "评估查询结果质量...")

                    if quality != "good" and feedback:
                        # 质量不足时推送用户友好反馈
                        logger.info(f"[SSE] 质量不足，推送反馈: {feedback[:80]}")
                        yield _sse_event({
                            "type": "quality_feedback",
                            "quality": quality,
                            "feedback": feedback,
                        })

                # ── chart_direct: 图表快捷路径（Phase E.9）──
                elif node_name == "chart_direct":
                    logger.info("[SSE] chart_direct 快捷路径: 复用上轮缓存数据")
                    query_result = state_update.get("query_result", [])
                    yield _thinking_event("chart_direct", "loading_cache",
                                          f"复用上轮查询数据（{len(query_result)} 条记录）")

                # ── analyst: 数据分析 ────────────────────
                elif node_name == "analyst":
                    yield _thinking_event("analyst", "analyzing", "正在分析查询结果...")
                    analysis_text = state_update.get("analysis_text", "")
                    if analysis_text:
                        collected_analysis = analysis_text  # 收集用于标题生成
                        # 标题输入已齐备：后台预生成（与后续 chart 节点并行，DEF-009）
                        if title_task is None:
                            title_task = _asyncio.create_task(
                                generate_node_title(question, collected_analysis, provider)
                            )
                        logger.info(
                            "[SSE] 推送分析结果: %s",
                            analysis_text[:80],
                        )
                        # 分析文本已通过 StreamContext.push_token 实时推送
                        await _track(EventType.ANALYSIS, role="assistant", content=analysis_text)

                # ── reporter: 图表生成 ────────────────────
                elif node_name == "reporter":
                    yield _thinking_event("reporter", "generating_chart", "正在生成图表配置...")
                    chart_config = state_update.get("chart_config")
                    if chart_config:
                        chart_type = chart_config.get("chart_type", "unknown")
                        logger.info(f"[SSE] 推送图表配置: type={chart_type}")
                        yield _tool_event("tool_call", "reporter", chart_type=chart_type)
                        yield _sse_event({
                            "type": "chart",
                            "config": chart_config,
                        })
                        yield _tool_event("tool_result", "reporter", chart_type=chart_type)
                        await _track(EventType.TOOL_CHAIN, role="tool",
                                     content=f"生成 {chart_type} 图表",
                                     payload={"name": "reporter", "status": "done",
                                              "result": f"生成 {chart_type} 图表", "chart_type": chart_type})
                        await _track(EventType.CHART, role="assistant", payload={"config": chart_config})

                # ── answer: 纯文本回答（Phase E.3）───────────
                elif node_name == "answer":
                    yield _thinking_event("answer", "formatting", "生成纯文本回答...")

                # ── rag_agent: RAG 知识库检索 ────────────
                elif node_name == "rag_agent":
                    yield _thinking_event("rag_agent", "retrieving", "检索知识库...")
                    text = state_update.get("analysis_text", "")
                    if text:
                        collected_analysis = text[:200]  # 收集用于标题生成
                        # 标题输入已齐备：后台预生成（DEF-009）
                        if title_task is None:
                            title_task = _asyncio.create_task(
                                generate_node_title(question, collected_analysis, provider)
                            )
                        logger.info(f"[SSE] RAG 检索结果: {text[:80]}")
                        await _track(EventType.ANALYSIS, role="assistant", content=text)

                # ── __interrupt__: 高危 SQL 审批中断 ──
                # 已迁移至 _forward_graph 拦截处理(HITL 流内等待 + Command(resume) 续流),
                # 主循环不再见到 __interrupt__ 节点事件。

                # ── finish: 工作流结束 ────────────────────
                elif node_name == "finish":
                    yield _thinking_event("finish", "completed", "完成")
                    logger.info(f"[SSE] 工作流执行完毕, node_index={node_index}")
                    # DEF-009：输出本轮节点耗时序列（自身耗时），用于性能画像
                    logger.info("[PERF] 节点耗时序列: %s | 总计 %.1fs",
                                " > ".join(_node_timings), _time.monotonic() - _run_t_start)
                    # R16：turn 边界收尾
                    if es_enabled and turn_event_enabled():
                        await _track(EventType.TURN_END, role="system", payload={
                            "turn_index": node_index,
                            "elapsed_s": round(_time.monotonic() - _run_t_start, 1),
                        })

                    # done 先行：标题生成（1~3s LLM 调用）移出关键路径，
                    # 前端 onDone 后已解锁输入，title 为增量更新，挂连接等待安全
                    yield _sse_event({"type": "done"})

                    try:
                        answer_summary = collected_analysis or collected_sql or ""
                        # 复用 analyst 完成时已启动的预生成任务；未启动时现场生成
                        node_title = (
                            await title_task if title_task is not None
                            else await generate_node_title(question, answer_summary, provider)
                        )
                        # 使用 chat.py 层的 node_index（来自 MySQL count），而非 state_update 中的值
                        await _save_chat_node(session_thread_id, node_index, node_title, question, run_id)
                        if node_index == 0:
                            await _upsert_chat_session(session_thread_id, user_name, node_title)
                        logger.info("[TitleGen] 标题已保存: session=%s, run=%s, index=%d, title='%s'",
                                    session_thread_id, run_id, node_index, node_title)
                        # 通过 SSE 推送标题给前端（无需额外 HTTP 请求）
                        yield _sse_event({
                            "type": "title",
                            "content": node_title,
                            "thread_id": session_thread_id,
                            "node_index": node_index,
                        })
                    except Exception as title_exc:
                        logger.warning(f"[TitleGen] 标题生成/保存失败（不影响已发出的 done）: {title_exc}")

        # 单队列保序：done 由 _forward_graph 在 graph 全部节点完成后入队，
        # 此时所有节点内 push 的事件均已被单消费者按序消费，无需兜底排空

    except GraphInterrupt as gi:
        # Human-in-the-loop 中断：高危 SQL 需要人工审批
        # GraphInterrupt 是 LangGraph 的控制流机制，不是错误
        interrupt_data = gi.args[0] if gi.args else {}
        logger.info(
            "[SSE] Graph 中断，等待人工审批: session=%s, sql=%s",
            session_thread_id,
            interrupt_data.get("sql", "")[:80] if isinstance(interrupt_data, dict) else "",
        )
        yield _sse_event({
            "type": "approval_required",
            "thread_id": session_thread_id,
            "question": question,
            "sql": interrupt_data.get("sql", "") if isinstance(interrupt_data, dict) else "",
            "reason": interrupt_data.get("reason", "") if isinstance(interrupt_data, dict) else "",
        })
    except Exception as exc:
        from app.core.llm import describe_route, get_model_name
        logger.exception("[SSE] 流式对话异常 | 路由: %s", describe_route())
        yield _error_event(
            f"处理异常: {str(exc)}（实际模型: {get_model_name()}）",
            code="INTERNAL_ERROR",
            recoverable=True,
        )
    finally:
        # 清理后台任务 + 重置流式上下文，避免泄漏到下一次请求
        if 'graph_task' in locals() and not graph_task.done():
            graph_task.cancel()
        set_stream_context(StreamContext())


async def _stream_chat_deepagent(question: str, user_name: str, history: list[dict] | None = None, existing_thread_id: str | None = None, model: str | None = None, mode: str = "data", web_search: bool = False, runtime_context: str = ""):
    """
    DeepAgent 模式 SSE 流式生成器 —— 基于 deepagents 库的智能调度。

    与 _stream_chat 的区别：
        - 使用 DeepAgent 作为顶层调度中心（替代 Orchestrator）
        - 支持复杂任务自动拆解（TodoListMiddleware）
        - 支持动态子 Agent 委派（data-query / knowledge-retrieval）
        - 支持 Anthropic Skills 调用（企业微信通知等）

    DeepAgent 内部节点名称映射：
        - agent / model: LLM 推理阶段
        - tools: 工具/子Agent 调用阶段
        - __end__: 执行完毕

    参数:
        question: 用户自然语言问题
        user_name: 当前登录用户名
        history: 对话历史消息列表
        existing_thread_id: 前端传入的会话 thread_id（多轮复用）

    产出:
        SSE 事件字符串流
    """
    # 锁定当前模型 provider（动态路由：界面所选模型 → 实际 API 调用）
    from app.core.llm import set_provider, describe_route
    from app.core.config_manager import get_config_manager
    # 修复：显式保存 provider 引用，供 __end__ 阶段 generate_node_title 使用
    # （原先未赋值，task 模式标题生成抛 NameError 被静默吞掉）
    provider = get_config_manager().get_llm_config(model)
    set_provider(provider)
    logger.info("[LLM路由] 实际调用(DeepAgent): %s", describe_route())

    agent = await get_deep_agent()

    # 会话级 thread_id：多轮对话复用，新建会话生成新的
    session_thread_id = existing_thread_id if existing_thread_id else f"{user_name}:{uuid.uuid4()}"
    # 执行级 run_id：每次调用都生成新的
    run_id = f"{user_name}:{uuid.uuid4()}"
    # deepagents 编译期默认 recursion_limit=9999（近乎无上限），子 Agent 委派一旦
    # 陷入「model → tools → subagent」循环将永不收敛、不产出 done 且持续消耗额度。
    # 这里显式收紧步数上限；超出后 LangGraph 抛 GraphRecursionError，
    # 由下方 except 分支优雅收尾（status + title + done）。
    config = {
        "configurable": {"thread_id": run_id},
        "recursion_limit": int(_os.getenv("DEEPAGENT_RECURSION_LIMIT", "60")),
    }

    logger.info("[chat] _stream_chat_deepagent: session_thread_id=%s (reused=%s), run_id=%s, question=%s",
                session_thread_id, bool(existing_thread_id), run_id, question[:80])

    # 推送 session thread_id 给前端
    yield _sse_event({"type": "thread_id", "thread_id": session_thread_id})

    # 创建/更新会话元数据记录（新建与复用均走 upsert，顺带刷新 updated_at 时间戳）
    await _upsert_chat_session(session_thread_id, user_name)

    # 多轮对话：根据已有节点数确定本轮 node_index
    if existing_thread_id:
        node_index = await _count_nodes(session_thread_id)
    else:
        node_index = 0

    # ── 事件溯源双写（Phase 1）：feature flag 开启时，记录业务事件到 session_events ──
    es_enabled = event_sourcing_enabled()
    # 聚合本轮完整回答文本（messages 模式逐 token 累加，__end__ 时落为 analysis 事件）
    deep_full_text = ""

    # ── 阶段二 2.2：DeepAgent 以 node_name 为分组键分配 step_id（同轮次内自增从 1 开始）──
    deep_node_steps: dict[str, int] = {}

    def _deep_step(node_name: str) -> int:
        sid = deep_node_steps.get(node_name)
        if sid is None:
            sid = len(deep_node_steps) + 1
            deep_node_steps[node_name] = sid
        return sid

    async def _track(etype: str, role: str | None = None, content: str = "", payload: dict | None = None):
        """在事件溯源开启时追加一条事件（失败不阻断主流程）。"""
        if es_enabled:
            await SessionEventStore.append(
                session_thread_id, etype,
                run_id=run_id, node_index=node_index,
                role=role, content=content, payload=payload,
            )

    if es_enabled:
        await _track(EventType.USER_MESSAGE, role="user", content=question)
        # R16：turn 边界事件（DeepAgent 分支）
        if turn_event_enabled():
            await _track(EventType.TURN_START, role="system", payload={
                "turn_index": node_index, "question_preview": question[:100],
            })

    # DeepAgent 使用标准消息格式（含多轮历史）
    previous_msgs = history or []
    input_data = {"messages": [*previous_msgs, {"role": "user", "content": question}]}

    # 阶段4 B6：注入会话长期目标（对齐 Harness /goal 命令）
    if existing_thread_id:
        goal_text = await _get_session_goal(existing_thread_id)
        if goal_text:
            input_data["messages"] = [
                {"role": "system", "content": f"[会话长期目标] {goal_text}\n请始终围绕该目标执行任务并回答用户问题。"},
                *input_data["messages"],
            ]

    # ── R12：每请求运行时上下文（驱动器注入：用户/日期/模式/审批档位）──
    # DeepAgent 的 system_prompt 由全局单例构建一次，运行期变量以 system 消息逐请求注入
    if runtime_context:
        input_data["messages"] = [
            {"role": "system", "content": runtime_context},
            *input_data["messages"],
        ]

    # ── 联网搜索提示：web_search=True 时注入系统指令 ──
    if web_search:
        input_data["messages"][-1]["content"] += (
            "\n\n[提示] 你可以使用 web_search_tool 工具搜索互联网获取实时信息（天气、新闻、股价等）。"
            "对于需要最新数据的问题，请优先使用该工具进行搜索，然后基于搜索结果给出回答并注明信息来源。"
        )
        # yield _sse_event({"type": "status", "content": "联网搜索已开启"})

    yield _sse_event({
        "type": "status",
        "content": "DeepAgent 正在分析您的请求...",
    })

    # 用于标题生成的数据收集
    collected_deep_text = ""

    # 收尾函数：事件溯源落盘 + 标题生成保存 + done 事件。
    # 抽取为独立函数，供 __end__ 分支与"循环结束兜底"两处复用（DEF-008 伴生修复：
    # LangGraph updates 模式在 deepagents 图结束时可能不产出 __end__ 更新，
    # 若只挂 __end__ 处理器，task 模式会静默断流——无 title、无 done）。
    _done_emitted = False

    async def _finalize_run() -> list[dict]:
        """执行收尾并返回待推送的 SSE 事件列表（幂等：只允许执行一次）。"""
        nonlocal _done_emitted
        if _done_emitted:
            return []
        _done_emitted = True
        events: list[dict] = []
        # R16：turn 边界收尾
        if es_enabled and turn_event_enabled():
            await _track(EventType.TURN_END, role="system", payload={"turn_index": node_index})
        # 事件溯源：落盘本轮完整回答文本为 analysis 事件
        if es_enabled and deep_full_text:
            await _track(EventType.ANALYSIS, role="assistant", content=deep_full_text)
        # done 先行：标题生成（1~3s LLM 调用）移出关键路径——若 title 在 done 之前
        # 生成，前端 isLoading 会多转 1~3s 圈（阶段一 1.3 语义，合并时勿回退）
        events.append({"type": "done"})
        try:
            node_title = await generate_node_title(question, collected_deep_text, provider)
            logger.info("[DeepAgent] 标题生成: %s", node_title)
            await _save_chat_node(session_thread_id, node_index, node_title, question, run_id)
            logger.info("[DeepAgent] 节点已保存: thread_id=%s node_index=%d",
                        session_thread_id, node_index)
            if node_index == 0:
                await _upsert_chat_session(session_thread_id, user_name, node_title)
                logger.info("[DeepAgent] 会话已创建: session=%s title=%s",
                            session_thread_id, node_title)
            events.append({
                "type": "title",
                "content": node_title,
                "thread_id": session_thread_id,
                "node_index": node_index,
            })
        except Exception as title_exc:
            logger.warning("[DeepAgent] 标题/保存失败（不影响已发出的 done）: %s", title_exc, exc_info=True)
        return events

    # 迭代保护（DEF：子 Agent 委派可能陷入「model → tools → subagent」死循环，
    # 请求永不收敛、无 done 事件，并持续消耗 LLM 额度）。
    # 超过 DEEPAGENT_MAX_SECONDS 后主动中断流并走正常收尾（title + done）。
    import time as _time

    _started_at = _time.monotonic()
    _max_seconds = float(_os.getenv("DEEPAGENT_MAX_SECONDS", "300"))

    try:
        # stream_mode=["updates", "messages"] → 双模式：
        #  - "messages": (AIMessageChunk, metadata) 元组 — 逐 token 实时流式
        #  - "updates":  {node_name: state_update} — 节点完成事件（工具调用/完成）
        _aiter = agent.astream(input_data, config, stream_mode=["updates", "messages"]).__aiter__()
        while True:
            # 墙钟守卫：单步 await 本身也可能长时间挂起（子 Agent 全管线 20~40s），
            # 因此必须对 __anext__() 设置「剩余超时」，否则死循环永远无法中断。
            _remain = _max_seconds - (_time.monotonic() - _started_at)
            if _remain <= 0:
                logger.warning(
                    "[DeepAgent SSE] 执行超过 %.0fs 仍未收敛，主动中断: thread_id=%s",
                    _max_seconds, session_thread_id,
                )
                yield _sse_event({
                    "type": "status",
                    "content": f"任务执行超过 {int(_max_seconds)}s 仍未完成，已主动结束本次执行。",
                })
                break
            try:
                event = await _asyncio.wait_for(_aiter.__anext__(), timeout=_remain)
            except StopAsyncIteration:
                break
            except TimeoutError:
                logger.warning(
                    "[DeepAgent SSE] 单步等待超过 %.0fs，主动中断: thread_id=%s",
                    _max_seconds, session_thread_id,
                )
                yield _sse_event({
                    "type": "status",
                    "content": f"任务执行超过 {int(_max_seconds)}s 仍未完成，已主动结束本次执行。",
                })
                break
            mode, data = event

            if mode == "messages":
                # ── 逐 token 流式文本 ──
                chunk, metadata = data
                node = metadata.get("langgraph_node", "")
                # 阶段二 2.2：按节点归组，事件统一携带 step_id
                _sse_step_id.set(_deep_step(node))

                # 只处理 agent/model 节点的文本块
                if node in ("agent", "model"):
                    content = getattr(chunk, "content", "")

                    # ── 思考内容（reasoning）：与正文类型化隔离（Phase 4）──
                    # Qwen/DashScope OpenAI 兼容模式将思考增量放于 additional_kwargs.reasoning_content；
                    # 部分实现直接暴露 reasoning_content 属性，二者兼容取用。
                    reasoning = ""
                    add_kwargs = getattr(chunk, "additional_kwargs", None) or {}
                    if add_kwargs:
                        reasoning = add_kwargs.get("reasoning_content", "") or ""
                    if not reasoning:
                        reasoning = getattr(chunk, "reasoning_content", "") or ""
                    if reasoning:
                        yield _sse_event(make_event(SSEEventType.REASONING, content=reasoning))

                    if content and isinstance(content, str) and content.strip():
                        # 收集用于标题生成的首段文本
                        if not collected_deep_text:
                            collected_deep_text = content[:200]
                        # 累加完整回答文本（事件溯源投影用）
                        deep_full_text += content
                        yield _sse_event({"type": "token", "content": content})

                    # 工具调用块（增量）→ 结构化事件，前端渲染为可折叠卡片
                    tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
                    if tool_call_chunks:
                        for tc in tool_call_chunks:
                            name = tc.get("name")
                            if name:
                                args = tc.get("args") or ""
                                if isinstance(args, (dict, list)):
                                    import json as _json
                                    args = _json.dumps(args, ensure_ascii=False)
                                yield _sse_event({
                                    "type": "tool_call",
                                    "name": name,
                                    "args": str(args)[:500],
                                })

            elif mode == "updates":
                for node_name, state_update in data.items():
                    logger.info(f"[DeepAgent SSE] 节点: {node_name}")
                    # 阶段二 2.2：按节点归组，事件统一携带 step_id
                    _sse_step_id.set(_deep_step(node_name))

                    # agent/model 节点：仅处理工具调用（文本由 messages 模式流式处理）
                    if node_name in ("agent", "model"):
                        msgs = state_update.get("messages", [])
                        if msgs:
                            last_msg = msgs[-1]
                            content = getattr(last_msg, "content", "")
                            # 兜底：如果没有 messages 模式的文本被捕获，补充收集标题文本
                            if content and not collected_deep_text:
                                collected_deep_text = str(content)[:200]
                            # 工具调用（完整列表）→ 结构化事件
                            tool_calls = getattr(last_msg, "tool_calls", None)
                            if tool_calls and len(tool_calls) > 0:
                                for tc in tool_calls:
                                    name = tc.get("name", "?")
                                    args = tc.get("args", "")
                                    if isinstance(args, (dict, list)):
                                        import json as _json
                                        args = _json.dumps(args, ensure_ascii=False)
                                    yield _sse_event({
                                        "type": "tool_call",
                                        "name": name,
                                        "args": str(args)[:500],
                                    })

                    # 工具/子Agent 执行阶段 → 结构化结果事件
                    elif node_name == "tools":
                        msgs = state_update.get("messages", [])
                        for msg in msgs:
                            msg_content = getattr(msg, "content", "")
                            msg_name = getattr(msg, "name", "")
                            if msg_name == "task":
                                yield _sse_event({
                                    "type": "tool_result",
                                    "name": "subagent",
                                    "status": "running",
                                    "content": "子Agent 执行中...",
                                })
                            elif msg_content:
                                yield _sse_event({
                                    "type": "tool_result",
                                    "name": msg_name or "tool",
                                    "status": "done",
                                    "content": str(msg_content)[:800],
                                })
                                await _track(EventType.TOOL_CHAIN, role="tool",
                                             content=str(msg_content)[:800],
                                             payload={"name": msg_name or "tool", "status": "done"})

                    elif node_name == "__end__":
                        logger.info("[DeepAgent] __end__ 到达: thread_id=%s node_index=%d text_len=%d",
                                    session_thread_id, node_index, len(collected_deep_text) if collected_deep_text else 0)
                        for _ev in await _finalize_run():
                            yield _sse_event(_ev)

        # DEF-008 伴生修复：updates 模式可能不产出 __end__ 更新，
        # 循环正常结束但 done 未发出时兜底收尾，避免 task 模式静默断流。
        # 注意：本兜底必须位于 astream 循环「之外」（与 async for 同级），
        # 否则会在每个节点事件后提前收尾，导致 task 模式首帧即发 done、正文丢失。
        if not _done_emitted:
            logger.info("[DeepAgent SSE] astream 结束且未收到 __end__，兜底收尾: thread_id=%s", session_thread_id)
            for _ev in await _finalize_run():
                yield _sse_event(_ev)

    except GraphInterrupt as gi:
        interrupt_data = gi.args[0] if gi.args else {}
        logger.info(f"[DeepAgent SSE] 审批中断: thread_id={session_thread_id}")
        yield _sse_event({
            "type": "approval_required",
            "thread_id": session_thread_id,
            "question": question,
            "sql": interrupt_data.get("sql", "") if isinstance(interrupt_data, dict) else "",
            "reason": interrupt_data.get("reason", "") if isinstance(interrupt_data, dict) else "",
        })
    except GraphRecursionError:
        logger.warning(
            "[DeepAgent SSE] 达到步数上限（recursion_limit），优雅收尾: thread_id=%s",
            session_thread_id,
        )
        yield _sse_event({
            "type": "status",
            "content": "任务步数已达上限，已结束本次执行以避免无限循环。",
        })
        for _ev in await _finalize_run():
            yield _sse_event(_ev)
    except Exception as exc:
        from app.core.llm import describe_route, get_model_name
        logger.exception("[DeepAgent SSE] 流式对话异常 | 路由: %s", describe_route())

        # DEF-008：尚未产出任何正文时，降级到 legacy 工作流重试一次，
        # 避免 DeepAgent 分支因 LLM/初始化异常导致本次请求直接失败。
        if not (collected_deep_text or "").strip():
            fallback_mode = mode if mode in ("data", "report", "doc") else "data"
            logger.warning(
                "[DeepAgent SSE] 无有效输出，降级 legacy 工作流: thread_id=%s mode=%s",
                session_thread_id, fallback_mode,
            )
            try:
                async for fallback_ev in _stream_chat(
                    question, user_name, history, session_thread_id, model, fallback_mode, web_search
                ):
                    yield fallback_ev
                return
            except Exception as fallback_exc:
                logger.exception("[DeepAgent SSE] legacy 降级也失败: thread_id=%s", session_thread_id)
                yield _error_event(
                    f"DeepAgent 与降级工作流均失败: {fallback_exc}（实际模型: {get_model_name()}）",
                    code="INTERNAL_ERROR",
                    recoverable=True,
                )
                return

        yield _error_event(
            f"处理异常: {str(exc)}（实际模型: {get_model_name()}）",
            code="INTERNAL_ERROR",
            recoverable=True,
        )


# ================================================================
# API 路由
# ================================================================


@router.post("/completions", summary="SSE 流式对话")
async def chat_completions(body: ChatRequest, user: dict = Depends(get_current_user)):
    """
    SSE 流式对话接口 —— 接收用户问题，返回 Server-Sent Events 流。
    需要 Bearer token 认证。

    支持两种模式（通过环境变量 USE_DEEP_AGENT 切换）：
    - 传统模式 (USE_DEEP_AGENT=false): LangGraph 工作流 + Orchestrator 路由
    - DeepAgent 模式 (USE_DEEP_AGENT=true): DeepAgent 智能调度 + 子Agent委派

    thread_id 格式: {user_name}:{uuid}，实现用户间会话隔离。

    请求体：
        - messages: 对话历史（取最后一条作为当前用户问题）
        - stream: 是否启用流式响应（默认 true）

    响应：
        text/event-stream 格式的 SSE 事件流
    """
    question = body.messages[-1].content if body.messages else ""
    user_name = user["user_name"]

    # 提取对话历史（不含最后一条用户消息，最后一条将作为 question 单独传入）
    history_msgs = [
        {"role": m.role, "content": m.content}
        for m in body.messages[:-1]
    ] if len(body.messages) > 1 else []

    # 压缩前的原始历史（R20 影子比对基准：驱动器压缩结果 vs 旧路径压缩结果）
    _raw_history = list(history_msgs)

    # ── R20：统一循环驱动器（P2 第二步：驱动器接管分发）──
    # 无论开关如何都构造 LoopRequest（纯函数无副作用）；
    # AGENT_LOOP_ENABLED=true（默认）：采用驱动器产物（压缩/变量/上下文），
    #   分发由 _loop_req.profile 决定；
    # AGENT_LOOP_ENABLED=false：回退旧构造（仅压缩），分发规则不变——回滚通道。
    # AGENT_LOOP_SHADOW：影子比对（观察期工具，默认关闭）。
    _runtime_context = ""
    _loop_req = AgentLoopRunner.build_request(
        question=question,
        user_name=user_name,
        history=history_msgs,
        thread_id=body.thread_id,
        mode=body.mode,
        model=body.model,
        web_search=body.web_search,
        deepagent_on=use_deep_agent(),
    )
    if agent_loop_enabled():
        history_msgs = _loop_req.history
        _runtime_context = _loop_req.runtime_context
        if _loop_req.compaction_stats.get("triggered"):
            log.info(
                f"[chat_completions] 上下文已压缩: {_loop_req.compaction_stats['original']} 条 → "
                f"摘要+{_loop_req.compaction_stats['kept']} 条 "
                f"(digest {_loop_req.compaction_stats['digest_chars']} 字符)"
            )
        if agent_loop_shadow():
            # 影子比对（观察期工具）：与旧路径压缩结果比对，差异仅记日志
            _legacy_len = len(compact_history(_raw_history)[0])
            _shadow = AgentLoopRunner.shadow_compare(_loop_req, _legacy_len)
            log.info(
                f"[AgentLoop][shadow] profile={_loop_req.profile} history={len(history_msgs)} "
                f"比对={'OK' if _shadow['ok'] else _shadow['diffs']}"
            )
    else:
        history_msgs, _compaction = compact_history(history_msgs)
        if _compaction.get("triggered"):
            log.info(
                f"[chat_completions] 上下文已压缩: {_compaction['original']} 条 → "
                f"摘要+{_compaction['kept']} 条 (digest {_compaction['digest_chars']} 字符)"
            )

    # ── R16：不变量检查（"进入模型上下文的内容必须已落库"）──
    # 纯检查不阻断：未命中的历史消息记入日志（旧会话/溯源中途开启属预期）。
    # TURN_EVENT_ENABLED 开关控制；event_sourcing 关闭时自动跳过。
    if body.thread_id:
        _invariant = await check_history_invariant(body.thread_id, history_msgs)
        if _invariant.get("missing"):
            log.warning(
                f"[chat_completions][R16] 不变量检查: "
                f"{len(_invariant['missing'])}/{_invariant['checked']} 条历史未命中事件日志"
            )

    log.info(f"[chat_completions] SSE 流式对话, "
             f"user={user_name}, "
             f"mode={_loop_req.profile},"
             f" question={question}, history_len={len(history_msgs)}, "
             f"thread_id={body.thread_id or "(None — 新建会话)"}"
    )

    # ── HARNESS_MODE 分发(Phase 1:默认 off,行为与此前完全一致)──
    #   on:    data/report/doc 模式走 Harness 主循环(Phase 3 已扩展三模式)
    #   shadow:data 模式走 legacy,收尾后后台跑 Harness 双跑比对(见 shadow.py)
    #   off:   完全 legacy 行为
    # 配置来源:settings(.env / configs/patch.json 热更新),非进程环境变量——
    # 裸 os.getenv 读不到 pydantic 加载的 .env(项目无 load_dotenv)。
    _harness_mode = _resolve_harness_mode()
    # Phase 3:report/doc 的 legacy 流程只有 3 节点且核心能力(RAG 检索)已被
    # search_knowledge 工具覆盖,故一并纳入 Harness;SOP 片段按 mode 追加。
    if _harness_mode in ("on", "shadow") and body.mode in ("data", "report", "doc") \
            and not _loop_req.is_deepagent:
        from app.harness.stream_harness import stream_chat_harness

        if _harness_mode == "on":
            return StreamingResponse(
                _wrap_cancellable(
                    stream_chat_harness(question, user_name, history_msgs, body.thread_id,
                                        body.model, body.mode, body.web_search, _runtime_context)
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        # shadow:legacy 照常返回;**流结束后**挂后台双跑——必须等流结束才能
        # 拿到 legacy 的真实回答文本(Phase 2 门禁要的比对字段)。
        # 用 tap_stream 包裹:流以异常/取消结束时同样触发,否则采集管线静默丢样本。
        # TODO(下次采集时自然验证,勿专门补采):「客户端停止读取但连接未断开」
        # 这一场景未覆盖——此时流仍在跑,只有真正断开才走 tap_stream 的 finally。
        import asyncio as _a
        import time as _t

        from app.harness.shadow import run_shadow_comparison
        from app.harness.shadow_stream import tap_stream

        _req_started = _t.monotonic()
        _legacy_stream = _stream_chat(
            question, user_name, history_msgs, body.thread_id,
            body.model, body.mode, body.web_search,
        )

        async def _shadow_task(legacy_answer, legacy_tools=None):
            try:
                await _a.wait_for(
                    run_shadow_comparison(
                        question, legacy_answer=legacy_answer,
                        legacy_metrics={"duration_ms": int((_t.monotonic() - _req_started) * 1000)},
                        user_name=user_name, model=body.model,
                        # 构造路径与真实请求一致(否则比对的是环境差异而非模型差异)
                        runtime_context=_runtime_context, history=history_msgs,
                        legacy_tool_payloads=list(legacy_tools or []),
                    ),
                    timeout=float(settings.HARNESS_SHADOW_TIMEOUT),
                )
            except Exception as _se:  # noqa: BLE001
                log.warning("[Shadow] 后台任务异常(已忽略): %s", _se)

        def _fire_shadow(legacy_answer, legacy_tools=None) -> None:
            _t2 = _a.create_task(_shadow_task(legacy_answer, legacy_tools))
            _shadow_tasks.add(_t2)
            _t2.add_done_callback(_shadow_tasks.discard)
        return StreamingResponse(
            _wrap_cancellable(tap_stream(_legacy_stream, _fire_shadow)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # R20：分发由驱动器 Profile 决策接管（规则与旧逻辑一致：
    # USE_DEEP_AGENT 全局开启或 mode=task → deepagent，其余 → legacy-graph）
    if _loop_req.is_deepagent:
        return StreamingResponse(
            _wrap_cancellable(
                _stream_chat_deepagent(question, user_name, history_msgs, body.thread_id, body.model, body.mode, body.web_search, _runtime_context)
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return StreamingResponse(
        _wrap_cancellable(
            _stream_chat(question, user_name, history_msgs, body.thread_id, body.model, body.mode, body.web_search)
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class CancelRequest(BaseModel):
    """停止生成请求体"""
    thread_id: str = Field(..., description="要停止生成的会话 ID（chat 返回的 thread_id）")


@router.post("/cancel", summary="停止会话生成（阶段2 B3）")
async def cancel_generation(
    body: CancelRequest,
    user: dict = Depends(get_current_user),
):
    """
    停止指定会话正在进行的 SSE 生成（对齐 Harness 的"停止生成"）。

    权限：
        需登录；非 admin 用户仅能停止自己的会话。
    """
    task = _active_stream_tasks.get(body.thread_id)
    stop_event = _active_stream_events.get(body.thread_id)
    if not task and not stop_event:
        return {"success": False, "message": "该会话没有进行中的生成"}

    # 会话归属校验
    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"
    if not is_admin and ":" in body.thread_id:
        owner = body.thread_id.split(":", 1)[0]
        if owner != user_name:
            logger.warning("[cancel] 越权停止被拒绝: user=%s thread_id=%s", user_name, body.thread_id)
            raise HTTPException(status_code=403, detail="无权停止他人的会话")

    # 先设停止标志（生成器下次循环 break，SSE 正常结束），再 cancel 任务兜底
    if stop_event:
        stop_event.set()
    if task:
        task.cancel()
    logger.info("[cancel] 已发送停止指令: thread_id=%s", body.thread_id)
    return {"success": True, "message": "已发送停止指令"}


# ================================================================
# 问题建议 API（Phase E.7 — 基于表结构动态生成问题模板）
# ================================================================


@router.get("/suggestions", summary="获取基于表结构的问题建议")
async def get_suggestions(
    force_refresh: bool = False,
    model: str | None = None,
    user: dict = Depends(get_current_user),
):
    """
    基于数据库实际表结构，调用 LLM 生成 3-5 条自然语言分析问题建议。

    用于替代前端硬编码的问题模板（如「查询本月销售额Top10产品」等），
    使推荐问题与用户实际数据表结构相关，提升用户体验。

    LLM 路由：显式走「前端模型列表」(llm_providers.json 中 enabled 的 provider)，
    与聊天流一致；不回退到 .env 的 settings（避免 suggestions 与对话用不同账户）。
    model 为空时回退到第一个 enabled provider，仍不回退 env。

    缓存策略：
        - 默认返回模块级缓存（表结构不变则不重复调用 LLM）
        - 传入 ?force_refresh=true 可强制刷新

    参数:
        force_refresh: 是否强制刷新缓存（默认 false）
        model: 前端选中的模型 provider id（可选）

    返回:
        {"questions": ["问题1", "问题2", ...], "cached": bool}
    """
    try:
        # 解析 LLM provider（走前端模型列表，不回退 env）
        provider = _resolve_enabled_provider(model)
        if provider is not None:
            logger.info("[suggestions] LLM 路由: provider_id=%r model=%r",
                        provider.get("id"), provider.get("model"))

        # 先尝试从缓存获取
        if not force_refresh:
            cached = get_cached_suggestions()
            if cached is not None:
                return {"questions": cached, "cached": True}

        # 连接数据库获取表结构（带超时保护，DB 不可用时使用默认模板）
        try:
            engine = get_engine()
            schema_text = await _asyncio.wait_for(
                get_table_schemas(engine),
                timeout=8.0,
            )
        except (_asyncio.TimeoutError, Exception) as db_exc:
            logger.warning(f"[suggestions] 数据库连接超时/失败，使用默认模板: {db_exc}")
            return {
                "questions": [
                    "帮我分析数据库整体概况",
                    "统计各表的数据量",
                    "查看数据库表结构",
                ],
                "cached": False,
            }

        if not schema_text or schema_text == "（数据库中无用户表）":
            return {
                "questions": [
                    "帮我分析数据库整体概况",
                    "统计各表的数据量",
                    "查看数据库表结构",
                ],
                "cached": False,
            }

        # 调用 LLM 生成问题建议（显式传入 provider，走前端模型列表）
        questions = await generate_question_suggestions(
            schema_text, force_refresh=force_refresh, provider=provider
        )

        return {"questions": questions, "cached": False}

    except Exception as exc:
        logger.exception("[suggestions] 生成问题建议失败")
        # 不抛 HTTPException，返回默认建议保证前端正常渲染
        return {
            "questions": [
                "帮我分析数据库整体概况",
                "统计各表的数据量",
                "查看数据库表结构",
            ],
            "cached": False,
        }


# ================================================================
# 会话持久化辅助函数（MySQL 存储）
# ================================================================


async def _get_session_goal(thread_id: str) -> str:
    """读取会话长期目标（阶段4 B6，注入 system prompt）。失败返回空串。"""
    from app.models.session import ChatSession
    from app.db.session import _get_session_factory
    from sqlalchemy import select

    try:
        factory = _get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(ChatSession.goal).where(ChatSession.thread_id == thread_id)
            )
            goal = result.scalar_one_or_none()
            return goal or ""
    except Exception as exc:
        logger.warning("[goal] 读取会话目标失败: %s", exc)
        return ""


async def _upsert_chat_session(thread_id: str, user_name: str, title: str = ""):
    """创建或更新会话元数据记录（MySQL chat_sessions 表）"""
    from app.models.session import ChatSession
    from app.db.session import get_db

    try:
        async for db in get_db():
            from sqlalchemy import select
            result = await db.execute(
                select(ChatSession).where(ChatSession.thread_id == thread_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                if title:
                    existing.title = title
                logger.info("[sessions] _upsert_chat_session: thread_id=%s 已存在，更新 updated_at%s",
                            thread_id, f", title='{title}'" if title else "")
            else:
                session = ChatSession(
                    thread_id=thread_id,
                    user_name=user_name,
                    title=title,
                )
                db.add(session)
                logger.info(f"[sessions] _upsert_chat_session: thread_id={thread_id} 新建会话")
            await db.commit()
            return
    except Exception as exc:
        logger.warning(f"[sessions] MySQL 会话写入失败: {exc}")


async def _save_chat_node(thread_id: str, node_index: int, title: str, question: str, run_id: str = ""):
    """保存单轮问答节点标题（MySQL chat_nodes 表）"""
    from app.models.session import ChatNode
    from app.db.session import get_db

    try:
        async for db in get_db():
            node = ChatNode(
                thread_id=thread_id,
                node_index=node_index,
                title=title,
                question=question[:200] if question else "",
                run_id=run_id,
            )
            db.add(node)
            await db.commit()
            return
    except Exception as exc:
        logger.warning(f"[sessions] MySQL 节点写入失败: {exc}")


async def _count_nodes(thread_id: str) -> int:
    """统计指定会话下已有的节点数，作为新节点的 node_index"""
    from app.models.session import ChatNode
    from app.db.session import get_db
    from sqlalchemy import select, func

    try:
        async for db in get_db():
            result = await db.execute(
                select(func.count()).select_from(ChatNode).where(ChatNode.thread_id == thread_id)
            )
            count = result.scalar() or 0
            return count
    except Exception as exc:
        logger.warning(f"[sessions] MySQL 节点计数失败: {exc}")
        return 0


async def _get_last_run_state(session_thread_id: str) -> dict | None:
    """
    从 Redis checkpointer 获取该会话最近一次运行的状态数据。

    用于多轮对话中恢复上一轮的查询结果（query_result / query_columns），
    使 chart_interaction 可以跳过 SQL 全链路直接复用已有数据。

    参数:
        session_thread_id: 会话 ID

    返回:
        包含 query_result / query_columns 等字段的字典，无数据时返回 None
    """
    from app.models.session import ChatNode
    from app.db.session import get_db
    from sqlalchemy import select

    try:
        logger.info(f"[cache] 开始恢复上轮缓存: session_thread_id={session_thread_id}")
        # 从 MySQL 获取最后一个节点的 run_id
        async for db in get_db():
            result = await db.execute(
                select(ChatNode)
                .where(ChatNode.thread_id == session_thread_id)
                .order_by(ChatNode.node_index.desc())
                .limit(1)
            )
            last_node = result.scalar_one_or_none()
            if not last_node:
                logger.warning(f"[cache] 未找到节点: session_thread_id={session_thread_id}")
                return None
            last_run_id = getattr(last_node, "run_id", "") or ""
            logger.info("[cache] 找到最新节点: node_index=%d, run_id=%s",
                        getattr(last_node, "node_index", -1), last_run_id)
            break
        else:
            logger.warning("[cache] get_db() 未产生迭代")
            return None

        if not last_run_id:
            logger.warning(f"[cache] 节点的 run_id 为空: session_thread_id={session_thread_id}")
            return None

        # 从 Redis checkpointer 获取状态
        from app.graph.workflow import get_graph
        graph = get_graph()
        config = {"configurable": {"thread_id": last_run_id}}
        state = await graph.aget_state(config)
        if state and hasattr(state, "values") and state.values:
            sv = state.values
            query_result = sv.get("query_result", [])
            query_columns = sv.get("query_columns", [])
            logger.info("[cache] 成功恢复缓存: %d 行 %d 列, run_id=%s",
                        len(query_result), len(query_columns), last_run_id)
            return {
                "query_result": query_result,
                "query_columns": query_columns,
            }
        logger.warning(f"[cache] Redis 状态为空: run_id={last_run_id}")
    except Exception as exc:
        logger.warning(f"[sessions] 恢复上轮状态失败: {exc}")
    return None


async def _delete_session_mysql(thread_id: str) -> int:
    """从 MySQL 删除会话元数据和所有节点。

    返回:
        被删除的会话行数（0 表示会话不存在）
    """
    from app.models.session import ChatSession, ChatNode
    from app.db.session import get_db
    from sqlalchemy import delete

    try:
        async for db in get_db():
            await db.execute(delete(ChatNode).where(ChatNode.thread_id == thread_id))
            result = await db.execute(
                delete(ChatSession).where(ChatSession.thread_id == thread_id)
            )
            await db.commit()
            return result.rowcount or 0
    except Exception as exc:
        logger.warning(f"[sessions] MySQL 删除失败: {exc}")
        return 0


# ================================================================
# 会话历史管理 API
# ================================================================


class SessionInfo(BaseModel):
    """会话摘要信息"""
    thread_id: str = Field(..., description="会话 thread_id")
    title: str = Field("", description="会话标题")
    question: str = Field("", description="用户首次提问")
    created_at: str = Field("", description="创建时间 ISO 字符串")
    message_count: int = Field(0, description="消息数量")


@router.get("/sessions", summary="获取会话列表")
async def list_sessions(
    user: dict = Depends(get_current_user),
    all_users: bool = False,
):
    """
    返回当前用户（或管理员查看全部）的历史会话列表。

    优先从 MySQL chat_sessions 表查询，
    补充 Redis checkpointer 中的消息数量。

    Admin (user_type='00') 可通过 ?all=true 查看所有用户会话。

    参数:
        all_users: 仅 Admin 可用，查看所有用户的会话

    返回:
        list[dict] 会话摘要列表
    """
    from app.models.session import ChatSession, ChatNode
    from app.db.session import get_db
    from sqlalchemy import select, func

    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"
    view_all = all_users and is_admin

    try:
        async for db in get_db():
            # 构建查询
            if view_all:
                stmt = select(ChatSession).order_by(ChatSession.updated_at.desc())
            else:
                stmt = (
                    select(ChatSession)
                    .where(ChatSession.user_name == user_name)
                    .order_by(ChatSession.updated_at.desc())
                )
            result = await db.execute(stmt)
            db_sessions = result.scalars().all()

            sessions = []
            for s in db_sessions:
                # 查询该会话的节点数
                node_result = await db.execute(
                    select(func.count()).select_from(ChatNode).where(ChatNode.thread_id == s.thread_id)
                )
                node_count = node_result.scalar() or 0

                # 取最早的用户提问作为侧边栏快捷跳转文本
                question = ""
                try:
                    q_result = await db.execute(
                        select(ChatNode.question)
                        .where(ChatNode.thread_id == s.thread_id, ChatNode.node_index == 0)
                        .limit(1)
                    )
                    q_row = q_result.scalar_one_or_none()
                    if q_row:
                        question = q_row or ""
                except Exception:
                    pass

                sessions.append({
                    "thread_id": s.thread_id,
                    "title": s.title,
                    "question": question,
                    "created_at": s.created_at.isoformat() if s.created_at else "",
                    "message_count": node_count,
                })

            return sessions
    except Exception as exc:
        logger.warning(f"[sessions] MySQL 查询失败，回退 Redis: {exc}")

    # 回退：从 Redis checkpointer 读取（兼容旧数据）
    return await _list_sessions_from_redis(user_name, is_admin, view_all)


async def _list_sessions_from_redis(user_name: str, is_admin: bool, view_all: bool):
    """从 Redis checkpointer 读取会话列表（兼容旧数据）"""
    try:
        from app.graph.workflow import get_graph
        graph = get_graph()
        checkpointer = graph.checkpointer

        sessions: list[dict] = []

        if checkpointer is None:
            logger.warning("[sessions] checkpointer 未初始化")
            return sessions

        checkpoints = []
        try:
            if hasattr(checkpointer, "alist"):
                result = checkpointer.alist(None)
                import inspect
                if inspect.isasyncgen(result):
                    async for item in result:
                        checkpoints.append(item)
                elif inspect.isawaitable(result):
                    checkpoints = await result
                else:
                    checkpoints = list(result) if result else []
            elif hasattr(checkpointer, "list"):
                checkpoints = list(checkpointer.list(None) or [])
        except Exception as exc:
            logger.warning(f"[sessions] checkpointer 读取列表失败: {exc}")
            return sessions

        for ct in checkpoints:
            cfg = getattr(ct, "config", ct) if not isinstance(ct, dict) else ct
            thread_id = (cfg.get("configurable", {}) if isinstance(cfg, dict) else getattr(cfg, "configurable", {})).get("thread_id", "")
            if not thread_id:
                continue

            # 用户过滤
            if not view_all:
                if ":" not in thread_id:
                    if not is_admin:
                        continue
                else:
                    thread_user = thread_id.split(":", 1)[0]
                    if thread_user != user_name and not is_admin:
                        continue

            state = getattr(ct, "checkpoint", None) if hasattr(ct, "checkpoint") else None
            if state is None:
                try:
                    if hasattr(checkpointer, "aget"):
                        state = await checkpointer.aget(cfg)
                    elif hasattr(checkpointer, "get"):
                        state = checkpointer.get(cfg)
                except Exception:
                    pass
            if not state:
                continue

            channel_values = state.get("channel_values", {}) if isinstance(state, dict) else {}
            question = _extract_question(channel_values)
            msg_count = _count_messages(channel_values)

            sessions.append({
                "thread_id": thread_id,
                "title": "",
                "question": question,
                "created_at": "",
                "message_count": msg_count,
            })

        seen = {}
        for s in sessions:
            seen[s["thread_id"]] = s
        sessions = list(seen.values())
        sessions.sort(key=lambda s: s.get("thread_id", ""), reverse=True)
        return sessions

    except Exception as exc:
        logger.exception("[sessions] 获取会话列表失败")
        return []


def _extract_question(state: dict) -> str:
    """从检查点状态中提取用户首条问题。"""
    messages = state.get("messages", []) if isinstance(state, dict) else []
    for m in messages:
        content = getattr(m, "content", "")
        role = getattr(m, "role", "") or getattr(m, "type", "")
        cls_name = getattr(m, "__class__", None)
        cls_str = cls_name.__name__ if cls_name else ""
        if role in ("user", "human") or "Human" in cls_str:
            return str(content)[:200]
    return ""


def _count_messages(state: dict) -> int:
    """统计检查点状态中的消息数量。"""
    messages = state.get("messages", []) if isinstance(state, dict) else []
    return len(messages)


class SessionUpdate(BaseModel):
    """会话更新请求体"""
    title: str = Field(..., min_length=1, max_length=200, description="新标题")


@router.patch("/sessions/{thread_id}", summary="更新会话标题")
async def update_session_title(
    thread_id: str,
    body: SessionUpdate,
    user: dict = Depends(get_current_user),
):
    """
    更新会话标题（手动编辑）。

    权限检查：
    - 普通用户只能编辑自己的会话
    - Admin 可编辑任意会话
    """
    from app.models.session import ChatSession
    from app.db.session import get_db
    from sqlalchemy import select

    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"

    # 权限检查
    if not is_admin and ":" in thread_id:
        thread_user = thread_id.split(":", 1)[0]
        if thread_user != user_name:
            return {"success": False, "thread_id": thread_id, "error": "无权编辑他人的会话"}

    try:
        async for db in get_db():
            result = await db.execute(
                select(ChatSession).where(ChatSession.thread_id == thread_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                return {"success": False, "thread_id": thread_id, "error": "会话不存在"}

            session.title = body.title
            await db.commit()
            return {"success": True, "thread_id": thread_id, "title": body.title}
    except Exception as exc:
        logger.exception("[sessions] 更新标题失败")
        return {"success": False, "thread_id": thread_id, "error": str(exc)}


@router.get("/sessions/{thread_id}", summary="恢复历史会话消息")
async def get_session_messages(
    thread_id: str,
    user: dict = Depends(get_current_user),
):
    """
    从 Redis checkpoint + MySQL 恢复完整历史会话消息（Phase E.5）。

    流程：
        1. 验证用户权限（是否拥有此会话）
        2. 从 MySQL 查询节点标题列表
        3. 从 Redis checkpointer 获取最新状态
        4. 提取状态中的各字段（SQL/结果/分析/图表）
        5. 组装为前端可直接渲染的消息格式

    参数:
        thread_id: 会话 ID

    返回:
        {thread_id, title, nodes, messages}
    """
    from app.models.session import ChatSession, ChatNode
    from app.db.session import get_db
    from sqlalchemy import select

    # 1. 权限检查：非 admin 访问他人会话直接 403
    #    说明：admin 允许跨用户访问（管理用途），但会记录审计日志
    user_name = _check_thread_owner(thread_id, user)
    is_admin = user.get("user_type") == "00"
    if is_admin and ":" in thread_id and not thread_id.startswith(f"{user_name}:"):
        logger.info("[sessions] 管理员跨用户读取会话: admin=%s thread_id=%s", user_name, thread_id)

    # 2. 查询节点标题和会话标题
    title = ""
    nodes: list[dict] = []
    latest_run_id = ""  # 初始化，避免 except 分支中未定义
    session_exists = False
    try:
        async for db in get_db():
            session_result = await db.execute(
                select(ChatSession).where(ChatSession.thread_id == thread_id)
            )
            session_row = session_result.scalar_one_or_none()
            session_exists = session_row is not None
            if session_row:
                title = session_row.title or ""

            node_result = await db.execute(
                select(ChatNode)
                .where(ChatNode.thread_id == thread_id)
                .order_by(ChatNode.node_index)
            )
            node_rows = node_result.scalars().all()
            nodes = [
                {"index": n.node_index, "title": n.title, "question": n.question or "", "run_id": getattr(n, "run_id", "") or ""}
                for n in node_rows
            ]
            # 取最后一个节点的 run_id 用于 Redis 状态恢复
            latest_run_id = getattr(node_rows[-1], "run_id", "") if node_rows else ""
            break
    except Exception as exc:
        logger.warning(f"[sessions] MySQL 节点查询失败: {exc}")

    # 2.1 会话不存在 → 404（避免返回空 200 造成前端误判为"存在但无内容"）
    if not session_exists and not nodes:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 3. 优先从事件日志投影恢复（Phase 1 事件溯源：append-only + surface 投影）
    if event_sourcing_enabled():
        try:
            derived = await SessionEventStore.derive_messages(thread_id)
            if derived:
                logger.info("[sessions] 历史会话从事件日志投影恢复: thread_id=%s, 消息数=%d",
                            thread_id, len(derived))
                return {
                    "thread_id": thread_id,
                    "title": title,
                    "nodes": nodes,
                    "messages": derived,
                }
            logger.info("[sessions] 事件日志为空，回退 Redis: thread_id=%s", thread_id)
        except Exception as exc:
            logger.warning(f"[sessions] 事件日志投影失败，回退 Redis: {exc}")

    # 4. 从 Redis checkpointer 获取所有节点的状态（回退路径，兼容旧数据）
    from app.graph.workflow import get_graph
    graph = get_graph()
    all_messages: list[dict] = []

    for node in nodes:
        run_id = node.get("run_id", "")
        if not run_id:
            continue
        try:
            config = {"configurable": {"thread_id": run_id}}
            state = await graph.aget_state(config)
            if not state or not hasattr(state, "values") or not state.values:
                continue
            sv = state.values
        except Exception:
            continue

        # 从状态重建该轮的消息
        turn_msgs: list[dict] = []

        user_q = sv.get("user_question", "") or node.get("question", "")
        if user_q:
            turn_msgs.append({"role": "user", "type": "text", "content": user_q})

        sql = sv.get("generated_sql", "")
        if sql:
            turn_msgs.append({"role": "assistant", "type": "sql", "sql": sql})

        query_result = sv.get("query_result", [])
        query_columns = sv.get("query_columns", [])
        if query_result:
            # 历史会话仅返回前 50 行，避免大数组导致前端卡顿
            total_rows = len(query_result)
            capped = query_result[:50] if total_rows > 50 else query_result
            turn_msgs.append({
                "role": "assistant", "type": "result",
                "data": capped, "columns": query_columns,
                "content": f"{total_rows} 条记录（仅展示前 50 条）" if total_rows > 50 else f"{total_rows} 条记录",
            })

        analysis_text = sv.get("analysis_text", "")
        if analysis_text:
            turn_msgs.append({"role": "assistant", "type": "text", "content": analysis_text})

        chart_config = sv.get("chart_config")
        if chart_config:
            turn_msgs.append({"role": "assistant", "type": "chart", "chartConfig": chart_config})

        error_message = sv.get("error_message", "")
        if error_message:
            turn_msgs.append({"role": "assistant", "type": "error", "content": error_message})


        all_messages.extend(turn_msgs)

    # 5. 兜底：事件日志与 Redis 均无数据（如 14 天前旧会话，事件溯源未启用/快照已过期）
    #    时，从 chat_nodes.question 构建最低限度消息，保证历史会话不空白（对齐 Harness 永不丢失会话）。
    if not all_messages and nodes:
        all_messages = [
            {"role": "user", "type": "text", "content": n["question"]}
            for n in nodes
            if n.get("question")
        ]
        logger.info("[sessions] 事件/Redis 均空，使用节点题兜底: thread_id=%s, 消息数=%d",
                    thread_id, len(all_messages))

    logger.info("[sessions] 历史会话已恢复: thread_id=%s, 消息数=%d, 节点数=%d",
                thread_id, len(all_messages), len(nodes))

    return {
        "thread_id": thread_id,
        "title": title,
        "nodes": nodes,
        "messages": all_messages,
    }


@router.get("/sessions/{thread_id}/export", summary="导出会话事件日志（JSONL）")
async def export_session_events(
    thread_id: str,
    user: dict = Depends(get_current_user),
):
    """
    导出会话的完整事件日志（含过程态事件 plan/clarification/tool_chain）为 JSONL。

    对齐 DeepSeek Harness 的 /export 命令（Session ZIP 归档）：
    事件溯源（session_events 表）是会话的唯一事实来源，导出即为可审计、可重放的
    完整事件流。

    权限：
        与 get_session_messages 一致——非 admin 仅能导出自己的会话。
    """
    from fastapi.responses import Response

    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"

    # 权限检查
    if not is_admin and ":" in thread_id:
        thread_user = thread_id.split(":", 1)[0]
        if thread_user != user_name:
            raise HTTPException(status_code=403, detail="无权导出他人的会话")

    events = await SessionEventStore.list_events(thread_id)
    if not events:
        raise HTTPException(status_code=404, detail="会话事件日志为空")

    lines = []
    for evt in events:
        try:
            payload_obj = json.loads(evt.payload) if evt.payload else None
        except (json.JSONDecodeError, TypeError):
            payload_obj = None
        lines.append(json.dumps({
            "id": evt.id,
            "thread_id": evt.thread_id,
            "run_id": evt.run_id,
            "node_index": evt.node_index,
            "event_type": evt.event_type,
            "role": evt.role,
            "content": evt.content,
            "payload": payload_obj,
            "created_at": evt.created_at.isoformat() if evt.created_at else None,
        }, ensure_ascii=False))

    filename = f"session-{thread_id.replace(':', '_')}.jsonl"
    return Response(
        content="\n".join(lines),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{thread_id}/trajectory", summary="会话轨迹（阶段4 B2 / R17 来源检查）")
async def get_session_trajectory(
    thread_id: str,
    full: bool = False,
    user: dict = Depends(get_current_user),
):
    """
    返回会话的完整事件轨迹（含过程态事件 plan/clarification/tool_chain），
    供前端轨迹时间线渲染（对齐 Harness 的 Trajectory step 级记录）。

    参数:
        full: 为 true 时 content 返回完整正文（默认截断 200 字符作预览）；
              同时返回 payload 与 run_id，供前端"来源检查"展开查看。

    权限：
        非 admin 仅能查看自己的会话。
    """
    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"
    if not is_admin and ":" in thread_id:
        thread_user = thread_id.split(":", 1)[0]
        if thread_user != user_name:
            raise HTTPException(status_code=403, detail="无权查看他人的会话")

    events = await SessionEventStore.list_events(thread_id)
    trajectory = [
        {
            "id": evt.id,
            "event_type": evt.event_type,
            "role": evt.role,
            "content": (evt.content or "") if full else (evt.content or "")[:200],
            "payload": evt.payload,
            "run_id": evt.run_id,
            "node_index": evt.node_index,
            "created_at": evt.created_at.isoformat() if evt.created_at else None,
        }
        for evt in events
    ]
    return {"thread_id": thread_id, "events": trajectory}


@router.get("/sessions/{thread_id}/derived-messages", summary="LLM 视角派生历史（R16）")
async def get_session_derived_messages(
    thread_id: str,
    user: dict = Depends(get_current_user),
):
    """
    从事件日志派生模型可见的对话历史（{"role","content"} 格式）。

    R16 事件底座的验证接口：与前端回传的 history 并行比对，
    一致性验证通过后，R20 统一循环将以本接口替代前端全量回传。
    权限：非 admin 仅能查看自己的会话。
    """
    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"
    if not is_admin and ":" in thread_id:
        thread_user = thread_id.split(":", 1)[0]
        if thread_user != user_name:
            raise HTTPException(status_code=403, detail="无权查看他人的会话")

    messages = await SessionEventStore.derive_llm_messages(thread_id)
    return {"thread_id": thread_id, "messages": messages, "total": len(messages)}


@router.post("/sessions/{thread_id}/fork", summary="分支会话（阶段2 A6）")
async def fork_session(
    thread_id: str,
    user: dict = Depends(get_current_user),
):
    """
    将源会话的事件日志复制到新会话（事件溯源 Fork，对齐 Harness "在新对话中分支"）。

    新会话 thread_id = {user_name}:{uuid}，仅含分支前事件（默认复制全部事件）。

    权限：
        非 admin 仅能分支自己的会话。
    """
    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"

    # 权限检查
    if not is_admin and ":" in thread_id:
        thread_user = thread_id.split(":", 1)[0]
        if thread_user != user_name:
            raise HTTPException(status_code=403, detail="无权分支他人的会话")

    new_thread_id = f"{user_name}:{uuid.uuid4()}"
    # 复制源会话全部事件（before_event_id 用极大值）
    copied = await SessionEventStore.fork(thread_id, new_thread_id, before_event_id=1 << 31)
    logger.info("[fork] 会话分支: %s -> %s (copied=%d)", thread_id, new_thread_id, copied)
    # 补写 chat_sessions 元数据，确保新会话出现在会话列表中（对齐 Harness "在新对话中分支"）
    try:
        from app.models.session import ChatSession
        from app.db.session import get_db
        async for db in get_db():
            from sqlalchemy import select
            result = await db.execute(
                select(ChatSession).where(ChatSession.thread_id == thread_id)
            )
            src = result.scalar_one_or_none()
            src_title = (src.title or "") if src else ""
            if src_title:
                src_title += "(分支)"
            new_sess = ChatSession(
                thread_id=new_thread_id,
                user_name=user_name,
                title=src_title,
            )
            db.add(new_sess)
            await db.commit()
    except Exception as exc:
        logger.warning("[fork] 写入 chat_sessions 失败: %s", exc)
    return {"success": True, "new_thread_id": new_thread_id, "copied_events": copied}


class GoalRequest(BaseModel):
    """设置会话长期目标请求体"""
    goal: str = Field("", max_length=2000, description="会话长期目标")


def _check_thread_owner(thread_id: str, user: dict) -> str:
    """会话归属校验，返回 user_name。非 admin 仅能操作自己的会话。"""
    user_name = user["user_name"]
    is_admin = user.get("user_type") == "00"
    if not is_admin and ":" in thread_id:
        thread_user = thread_id.split(":", 1)[0]
        if thread_user != user_name:
            raise HTTPException(status_code=403, detail="无权操作他人的会话")
    return user_name


@router.get("/sessions/{thread_id}/goal", summary="获取会话目标（阶段4 B6）")
async def get_session_goal(
    thread_id: str,
    user: dict = Depends(get_current_user),
):
    """获取会话长期目标（对齐 Harness /goal 命令）。"""
    _check_thread_owner(thread_id, user)
    goal = await _get_session_goal(thread_id)
    return {"thread_id": thread_id, "goal": goal}


@router.put("/sessions/{thread_id}/goal", summary="设置会话目标（阶段4 B6）")
async def set_session_goal(
    thread_id: str,
    body: GoalRequest,
    user: dict = Depends(get_current_user),
):
    """设置会话长期目标（对齐 Harness /goal 命令）。

    目标在下一轮 DeepAgent 请求时注入 system prompt，引导模型持续围绕目标执行。
    """
    _check_thread_owner(thread_id, user)
    from app.models.session import ChatSession
    from app.db.session import _get_session_factory
    from sqlalchemy import select

    try:
        factory = _get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(ChatSession).where(ChatSession.thread_id == thread_id)
            )
            chat = result.scalar_one_or_none()
            if chat is None:
                raise HTTPException(status_code=404, detail="会话不存在")
            chat.goal = body.goal
            await session.commit()
        logger.info("[goal] 已设置会话目标: thread_id=%s len=%d", thread_id, len(body.goal))
        return {"success": True, "goal": body.goal}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[goal] 设置会话目标失败: %s", exc)
        raise HTTPException(status_code=500, detail="设置会话目标失败")


@router.delete("/sessions/{thread_id}", summary="删除会话")
async def delete_session(thread_id: str, user: dict = Depends(get_current_user)):
    """
    删除指定会话及其所有状态（MySQL + Redis 双删）。

    权限检查：
    - 普通用户只能删除自己的会话（thread_id 以 {user_name}: 开头）
    - Admin 可删除任意会话

    参数:
        thread_id: 要删除的会话 ID

    返回:
        {"success": bool, "thread_id": str}
    """
    import inspect

    # 权限检查：复用统一归属校验（非 admin 仅能删除自己的会话）
    user_name = _check_thread_owner(thread_id, user)

    # 0. 存在性检查：会话不存在时返回 404，避免静默 success:true 误导前端
    from app.models.session import ChatSession
    from app.db.session import get_db
    from sqlalchemy import select
    try:
        async for db in get_db():
            result = await db.execute(
                select(ChatSession.thread_id).where(ChatSession.thread_id == thread_id)
            )
            if result.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="会话不存在")
            break
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[sessions] 会话存在性检查失败（继续删除流程）: {exc}")

    # 1. MySQL 删除
    await _delete_session_mysql(thread_id)

    # 2. Redis checkpointer 删除
    try:
        from app.graph.workflow import get_graph
        graph = get_graph()
        checkpointer = graph.checkpointer

        if checkpointer is not None:
            cfg = {"configurable": {"thread_id": thread_id}}
            if hasattr(checkpointer, "adelete"):
                result = checkpointer.adelete(cfg)
                if inspect.isawaitable(result):
                    await result
            elif hasattr(checkpointer, "delete"):
                checkpointer.delete(cfg)
    except Exception as exc:
        logger.warning(f"[sessions] Redis 删除失败（不影响主流程）: {exc}")

    logger.info(f"[sessions] 用户 {user_name} 删除会话: thread_id={thread_id}")
    return {"success": True, "thread_id": thread_id}
