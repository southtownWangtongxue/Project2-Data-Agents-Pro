"""
工具执行流水线（R9，对齐 Harness 的 tools/pre-execute → execute → post-execute）

为 DeepAgent 的所有工具（Skill 执行器 / 固定工具 / MCP 工具 / load_skill）
统一提供执行期保障：

- pre-execute：调用参数审计日志（截断记录，便于回溯）
- 超时保护：单次执行超过 TOOL_EXEC_TIMEOUT 秒强制中断，返回超时提示
- 异常兜底：工具抛异常转为错误字符串返回给模型，不中断 Agent 循环
- post-execute：耗时埋点 + 结果截断（TOOL_RESULT_MAX_LEN），控制上下文膨胀

MCP 工具客户端内部自带的进程复活/重试逻辑与本流水线正交叠加：
本层管"单次调用的超时与结果治理"，MCP 层管"连接与进程存活"。

普通异步函数原地包装（functools.wraps 保留签名元数据）；StructuredTool
（MCP 工具）以相同 args_schema 重建副本并替换协程，保证 LangChain 工具
协议不变。
"""
from __future__ import annotations

import asyncio
import functools
import time
from typing import Any

from app.core.config import settings
from app.utils.log_utils import log


def _truncate_result(result: Any) -> str:
    """将工具结果规整为字符串并按 TOOL_RESULT_MAX_LEN 截断。"""
    text = result if isinstance(result, str) else str(result)
    limit = settings.TOOL_RESULT_MAX_LEN
    if limit > 0 and len(text) > limit:
        text = text[:limit] + f"\n…[结果已截断，原始长度 {len(text)} 字符]"
    return text


def _wrap(fn, name: str):
    """为单个工具协程包装 pre → execute(timeout) → post 流水线。"""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        log.info(f"[ToolPipeline][pre] {name} args={str(kwargs)[:200]}")
        try:
            result = await asyncio.wait_for(
                fn(*args, **kwargs), timeout=settings.TOOL_EXEC_TIMEOUT
            )
        except asyncio.TimeoutError:
            log.warning(f"[ToolPipeline] {name} 超时（>{settings.TOOL_EXEC_TIMEOUT}s）")
            return f"工具 {name} 执行超时（>{settings.TOOL_EXEC_TIMEOUT}s）。请缩小请求范围后重试。"
        except Exception as exc:
            log.warning(f"[ToolPipeline] {name} 执行异常: {exc}")
            return f"工具 {name} 执行失败: {exc}"

        elapsed = time.monotonic() - t0
        out = _truncate_result(result)
        log.info(f"[ToolPipeline][post] {name} ok {elapsed:.2f}s result_len={len(out)}")
        return out

    return wrapper


def apply_tool_pipeline(tools: list) -> list:
    """
    对工具列表统一应用执行流水线（R9）。

    规则：
        - StructuredTool（含 args_schema + coroutine）：以原 args_schema 重建副本，
          协程替换为包装后的版本；
        - 普通异步函数：原地包装；
        - 其他对象或包装失败：原样保留并告警（不阻塞 Agent 装配）。
    """
    if not settings.TOOL_PIPELINE_ENABLED:
        log.info("[ToolPipeline] 未启用（TOOL_PIPELINE_ENABLED=false），工具保持原样")
        return list(tools)

    out: list = []
    for tool in tools:
        name = getattr(tool, "name", None) or getattr(tool, "__name__", "tool")
        try:
            if hasattr(tool, "args_schema") and getattr(tool, "coroutine", None):
                # LangChain StructuredTool：重建副本，替换协程
                from langchain_core.tools import StructuredTool

                rebuilt = StructuredTool.from_function(
                    name=tool.name,
                    description=tool.description or name,
                    args_schema=tool.args_schema,
                    coroutine=_wrap(tool.coroutine, tool.name),
                )
                out.append(rebuilt)
                log.info(f"[ToolPipeline] 已包装 StructuredTool: {tool.name}")
            elif asyncio.iscoroutinefunction(tool):
                out.append(_wrap(tool, name))
                log.info(f"[ToolPipeline] 已包装工具: {name}")
            else:
                out.append(tool)
        except Exception as exc:
            log.warning(f"[ToolPipeline] 包装 {name} 失败，保留原工具: {exc}")
            out.append(tool)
    return out
