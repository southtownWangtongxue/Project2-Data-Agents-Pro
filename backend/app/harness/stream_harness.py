"""Harness 主循环 SSE 流式生成器(Phase 1)。

与 _stream_chat_deepagent 的差异:
- Agent 来自 agent_factory.build_harness_agent(数据工具 + 安全闸中间件)
- 事件翻译走 HarnessEventBridge(todo→plan / 工具富事件 / 中断信号)
- HITL 采用 legacy 同款流内等待-恢复:approval_required 下发后
  hitl.wait_for 等待决策,Command(resume) 恢复并续流(超时自动拒)

复用 chat.py 的既有助手;chat.py 侧对本模块为懒加载 import(避免循环依赖),
因此这里可以模块级 import chat.py 的名称(测试亦可直接 patch 本模块属性)。
Phase 3 收敛时与另外两个生成器合并。
"""
from __future__ import annotations

import asyncio as _asyncio
import os as _os
import time as _time
import uuid

from langgraph.types import Command

from app.api.v1.chat import (
    _count_nodes,
    _get_session_goal,
    _save_chat_node,
    _sse_event,
    _upsert_chat_session,
)
from app.agents.title_generator import generate_node_title
from app.core import hitl
from app.core.config_manager import get_config_manager
from app.core.event_sourcing import (
    EventType,
    SessionEventStore,
    event_sourcing_enabled,
    turn_event_enabled,
)
from app.core.llm import set_provider
from app.core.config import settings
from app.core.llm_retry import (
    MAX_RETRIES as LLM_MAX_RETRIES,
)
from app.core.llm_retry import is_retryable_exception, next_retry_delay

# SSE 心跳间隔(秒):长静默期发注释行维持连接,防代理空闲断开。
# 必要性:report/doc 单轮实测可达 149s,期间若无事件输出,代理会按空闲断连。
_HEARTBEAT_SECONDS = 15
from app.harness.agent_factory import build_harness_agent, set_current_mode
from app.harness.sse_bridge import HarnessEventBridge
from app.utils.log_utils import log


def _recursion_limit_for(mode: str) -> int:
    """按模式给图递归上限(设计批准:data 20 步 / report 40 步,一次往返约 2 层)。

    report 类任务需要多轮检索+多维查询,与 data 共用一套预算会被墙钟/递归
    熔断在产出正文之前(实测 report 300s 内跑了 18 次工具调用后被切断、答案为空)。
    """
    base = int(settings.HARNESS_RECURSION_LIMIT)
    if mode == "report":
        return base * 2
    return base


def _max_seconds_for(mode: str) -> float:
    """按模式给墙钟熔断(report 需要更长;doc 与 data 同档)。"""
    base = float(settings.HARNESS_MAX_SECONDS)
    if mode == "report":
        return base * 2
    return base


async def stream_chat_harness(
    question: str,
    user_name: str,
    history: list[dict] | None = None,
    existing_thread_id: str | None = None,
    model: str | None = None,
    mode: str = "data",
    web_search: bool = False,
    runtime_context: str = "",
):
    """Harness 主循环 SSE 生成器(接口与 _stream_chat/_stream_chat_deepagent 一致)。"""
    # 按请求指定的模型锁定 provider(与 legacy _stream_chat 的 set_provider 同款):
    # 缺失这一步会沿用启动时的 provider,管理台切模型后请求仍打到旧模型。
    set_provider(get_config_manager().get_llm_config(model))
    # 按请求模式选 SOP 片段(data 基座 + report/doc 专属),模式变化会改变
    # Agent 装配指纹 → 自动重建
    set_current_mode(mode)

    agent = build_harness_agent()
    session_thread_id = existing_thread_id or f"{user_name}:{uuid.uuid4()}"
    run_id = f"{user_name}:{uuid.uuid4()}"
    config = {
        "configurable": {"thread_id": run_id},
        "recursion_limit": _recursion_limit_for(mode),
    }

    yield _sse_event({"type": "thread_id", "thread_id": session_thread_id})
    await _upsert_chat_session(session_thread_id, user_name)
    node_index = await _count_nodes(session_thread_id) if existing_thread_id else 0

    es_enabled = event_sourcing_enabled()
    full_text = ""
    bridge = HarnessEventBridge()

    async def _track(etype, role=None, content="", payload=None):
        if es_enabled:
            await SessionEventStore.append(
                session_thread_id, etype, run_id=run_id,
                node_index=node_index, role=role, content=content, payload=payload,
            )

    if es_enabled:
        await _track(EventType.USER_MESSAGE, role="user", content=question)
        if turn_event_enabled():
            await _track(EventType.TURN_START, role="system",
                         payload={"turn_index": node_index, "question_preview": question[:100]})

    # ── 输入组装:多轮历史 + 长期目标 + 运行时上下文 + 联网提示 ──
    input_data: object = {"messages": [*(history or []), {"role": "user", "content": question}]}
    if existing_thread_id:
        goal = await _get_session_goal(existing_thread_id)
        if goal:
            input_data["messages"] = [
                {"role": "system",
                 "content": f"[会话长期目标] {goal}\n请始终围绕该目标执行任务并回答用户问题。"},
                *input_data["messages"],
            ]
    if runtime_context:
        input_data["messages"] = [
            {"role": "system", "content": runtime_context}, *input_data["messages"],
        ]
    if web_search:
        input_data["messages"][-1]["content"] += (
            "\n\n[提示] 可以使用 web_search_tool 搜索互联网获取实时信息。"
        )

    # 瞬时 LLM 错误重放用:原始输入(重试时不带审批 Command)
    _replay_input = input_data

    yield _sse_event({"type": "status", "content": "正在分析您的请求..."})

    started = _time.monotonic()
    max_seconds = _max_seconds_for(mode)

    def _remaining() -> float:
        return max_seconds - (_time.monotonic() - started)

    try:
        # 注:hitl 等待者由下方 hitl.wait_for 内部 register_waiter 登记;
        # finally 的 cancel 负责在流退出(含客户端断连)时清理,防悬挂 waiter。
        # ── 主循环:astream →(审批中断)→ Command(resume) → 重新 astream ──
        # 瞬时 LLM 错误(OpenRouter 免费档间歇性 403/429/5xx)整段重放:
        # 实测同一请求 8 次失败 1 次,不重试则用户每次都要手动重发。
        transient_attempt = 0
        while True:
            remain = _remaining()
            if remain <= 0:
                yield _sse_event({"type": "status",
                                  "content": f"任务执行超过 {int(max_seconds)}s 仍未完成，已主动结束。"})
                break

            interrupted = False
            retry_from_start = False
            # SSE 注释行心跳(与 legacy _stream_chat 同款):report/doc 单轮实测
            # 可达 149s,长静默期若无事件输出,代理会按空闲断开连接。
            heartbeat = _HEARTBEAT_SECONDS
            try:
                aiter = agent.astream(
                    input_data, config, stream_mode=["updates", "messages"],
                ).__aiter__()
                while True:
                    remain = _remaining()
                    if remain <= 0:
                        yield _sse_event({"type": "status",
                                          "content": f"任务执行超过 {int(max_seconds)}s 仍未完成，已主动结束。"})
                        break
                    try:
                        event = await _asyncio.wait_for(aiter.__anext__(), timeout=heartbeat)
                        heartbeat = _HEARTBEAT_SECONDS  # 有事件即重置计时
                    except StopAsyncIteration:
                        break
                    except TimeoutError:
                        # 只是静默,不是卡死:发心跳维持连接,继续等
                        yield ": ping\n\n"
                        continue

                    for sse in bridge.feed(event):
                        if sse["type"] == "token":
                            full_text += sse.get("content", "")
                        if sse["type"] == "approval_required":
                            # ── HITL 流内等待-恢复(legacy 同款)──
                            yield _sse_event({
                                "type": "approval_required",
                                "thread_id": session_thread_id,
                                "question": question,
                                "sql": sse.get("sql", ""),
                                "reason": sse.get("reason", ""),
                            })
                            decision = await hitl.wait_for(session_thread_id, timeout=300)
                            if decision is None:
                                decision = {"approved": False,
                                            "comment": "审批超时（5 分钟），自动拒绝"}
                                yield _sse_event({
                                    "type": "status",
                                    "content": "审批超时（5 分钟），已自动拒绝。",
                                    "approval_state": "rejected",
                                })
                            input_data = Command(resume=decision)
                            interrupted = True
                            break
                        yield _sse_event(sse)
                    if interrupted:
                        break
            except Exception as exc:  # noqa: BLE001 —— 瞬时错误重试,其余转错误事件
                if is_retryable_exception(exc) and transient_attempt < LLM_MAX_RETRIES:
                    transient_attempt += 1
                    delay = next_retry_delay(transient_attempt)
                    log.warning(
                        "[Harness SSE] LLM 瞬时错误(第 %d/%d 次),%.1fs 后重放: %s",
                        transient_attempt, LLM_MAX_RETRIES, delay, str(exc)[:160],
                    )
                    yield _sse_event({
                        "type": "status",
                        "content": f"模型服务暂时繁忙，正在重试（{transient_attempt}/{LLM_MAX_RETRIES}）…",
                    })
                    await _asyncio.sleep(delay)
                    # 整段重放:回到首个模型回合(approval 决策保持不变)
                    input_data = _replay_input
                    retry_from_start = True
                    continue
                log.exception("[Harness SSE] 流式异常")
                yield _sse_event({"type": "error", "content": f"执行异常: {exc}", "recoverable": True})
                break
            if retry_from_start:
                continue
            if not interrupted:
                break
    finally:
        # 清理 hitl 等待登记(legacy 同款):客户端断连/取消不留悬挂 waiter
        hitl.cancel(session_thread_id)

    # ── 收尾:done 先行,标题后置(已修复语义,合并时勿回退)────────
    if es_enabled and turn_event_enabled():
        await _track(EventType.TURN_END, role="system", payload={"turn_index": node_index})
    if es_enabled and full_text:
        await _track(EventType.ANALYSIS, role="assistant", content=full_text)
    yield _sse_event({"type": "done"})
    try:
        title = await generate_node_title(question, full_text[:200])
        await _save_chat_node(session_thread_id, node_index, title, question, run_id)
        if node_index == 0:
            await _upsert_chat_session(session_thread_id, user_name, title)
        yield _sse_event({"type": "title", "content": title,
                          "thread_id": session_thread_id, "node_index": node_index})
    except Exception as title_exc:
        log.warning("[Harness SSE] 标题生成失败(不影响已发出的 done): %s", title_exc)
