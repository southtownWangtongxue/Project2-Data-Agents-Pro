"""Harness 主循环装配工厂(Phase 1)。

用 deepagents.create_deep_agent 装配顶层 Agent:
- 工具:Phase 0 数据能力工具(过 R9 流水线)
- 中间件:SqlGateMiddleware(安全闸)+ deepagents 默认中间件
  (TodoList/Filesystem/Summarization 等由 create_deep_agent 内置)
- system_prompt:只读优先 + 工具使用 SOP(分析流程沉淀为提示词规则,
  替代 legacy 的 quality_gate 节点;Phase 3 再迁 Skills)

Agent 为全局单例:构建期变量(模型/工具集)首次调用时确定;每请求变量
(user_name/today/mode)由 chat.py 以 system 消息注入(既有模式)。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.tool_pipeline import apply_tool_pipeline
from app.core.llm import _resolve_key_and_base, get_current_provider
from app.harness.sql_gate_middleware import SqlGateMiddleware
from app.harness.tools import get_data_tools
from app.utils.log_utils import log

SYSTEM_PROMPT = """你是 DataAgent Pro 的数据智能体,基于只读业务数据库回答用户的数据问题。

## 能力边界(硬约束)
- 你只能通过工具访问数据库,禁止凭记忆猜测表名/字段名;写 SQL 前必须先调用
  get_table_schema 了解结构。
- 只读优先:默认只生成 SELECT 类查询。写入/结构变更(INSERT/UPDATE/DELETE/
  DROP/ALTER 等)会被安全闸拦截并要求人工审批,除非用户明确要求且审批通过。
- 禁止多语句(分号分隔的多条 SQL),每条 SQL 只做一件事。

## 标准流程(SOP)
1. 理解问题:需要库内数据时,先 get_table_schema(keywords=问题关键词) 取相关表结构;
2. 生成并执行 SQL:写出单条 SELECT,调用 run_sql(sql, purpose) 执行;
   - 失败时阅读返回的 error,修正 SQL 后重试(最多换 2 种写法);
   - 连续失败就明确告知用户"查不到",不要反复试同一写法;
   - **多表统计/对比必须用单条 SQL(UNION ALL 或 JOIN)一次查完**,不要为每张表
     各发一次 run_sql —— 实测 5 张表发了 5 条,往返与耗时白翻数倍;
   - 需要多步时(≥2 次工具调用)先建 todo 清单再动手,单步简单查询不用建;
3. 分析结果:基于返回的 rows/columns 做统计与洞察(计数/汇总/对比/异常);
4. 可视化:数据适合图表时调用 make_chart 生成图表配置(用户指定了图表类型时,
   通过 chart_type 参数传入);
5. 输出回答:先给结论,再按**分析维度**逐项展开(对比/趋势/构成/异常/排名中相关的),每个维度下标明**数据来源查询**(如「依据:统计各表行数的那次查询」),不得只罗列数字。

## 其它
- 涉及指标口径/系统使用说明的问题,优先 search_knowledge 检索知识库;
- 回答使用简体中文;数字保留原始精度,单位写清楚;
- 用户问题超出数据库范围(闲聊/常识)时直接回答,不要强行查库。
"""

_agent: Any = None
_agent_fingerprint: str | None = None


def _create(**kwargs: Any) -> Any:
    """间接层:便于测试替换(不建真实模型)。"""
    from app.deepagent.harness import create_deep_agent

    return create_deep_agent(**kwargs)


def _build_model():
    """复用 DeepAgent 的模型构建逻辑(显式注入 provider key/base)。"""
    from app.deepagent.harness import _build_model as build

    return build()


def _build_checkpointer():
    """HITL Command(resume) 必须有 checkpointer(与 legacy graph 对齐)。

    优先全局 PlainRedisSaver(Redis 不可用时 workflow 已回退 InMemorySaver),
    再兜底本地 InMemorySaver——缺它时审批恢复段会抛
    "Cannot use Command(resume=...) without checkpointer"。
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from app.graph.workflow import get_checkpointer

    return get_checkpointer() or InMemorySaver()


def _agent_spec() -> dict[str, Any]:
    """装配 Agent 的**全部行为影响参数**(单一来源)。

    指纹与构建都从这里取:新增任何影响行为的参数只需加进本 spec,
    指纹自动覆盖——避免「指纹漏了新参数」这类坑(与 _build_model 硬编码
    temperature 是同一种错误模式)。

    刻意不含线程/请求级变量(thread_id、history、runtime_context)——那些
    每次请求都变,进指纹会导致每次都重建。
    """
    from app.deepagent.harness import _resolve_temperature
    from app.deepagent.tools import web_search_tool

    provider = get_current_provider()
    return {
        "system_prompt": SYSTEM_PROMPT,
        "tools": [getattr(t, "__name__", str(t)) for t in [*get_data_tools(), web_search_tool]],
        "middleware": [type(m).__name__ for m in (SqlGateMiddleware(),)],
        "provider": _provider_fingerprint(),
        "temperature": _resolve_temperature(provider),
    }


def _spec_fingerprint(spec: dict[str, Any]) -> str:
    """spec 的稳定指纹(内容哈希,短十六进制,便于日志阅读)。"""
    blob = json.dumps(spec, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_harness_agent() -> Any:
    """构建(首次)/返回(全局单例)Harness 主循环 Agent。

    单例按「装配 spec 指纹」缓存:管理台切换模型、改温度、改 SOP 等任一
    行为影响参数变化,下次请求自动重建——否则这些变更必须重启后端才生效
    (Phase 2 实测:换了含 UNION 指引的 SOP 却仍跑旧提示词,baseline 白采一轮)。
    """
    global _agent, _agent_fingerprint
    spec = _agent_spec()
    fingerprint = _spec_fingerprint(spec)
    if _agent is not None and fingerprint == _agent_fingerprint:
        return _agent

    from app.deepagent.tools import web_search_tool

    tools = apply_tool_pipeline([*get_data_tools(), web_search_tool])
    _agent = _create(
        model=_build_model(),
        tools=tools,
        middleware=[SqlGateMiddleware()],
        system_prompt=spec["system_prompt"],
        checkpointer=_build_checkpointer(),
    )
    _agent_fingerprint = fingerprint
    log.info(
        f"[Harness] 主循环装配完成: tools={len(tools)} fingerprint={fingerprint} "
        f"provider={spec['provider']} temperature={spec['temperature']}"
    )
    return _agent


def _provider_fingerprint() -> str:
    """当前 provider 的身份标识(id + model + api_base + key 前缀)。

    用于检测管理台/配置变更;不含完整 key,避免泄露到日志。
    """
    provider = get_current_provider()
    if not provider:
        return "default"
    key, base = _resolve_key_and_base(provider)
    return "|".join([
        str(provider.get("id")),
        str(provider.get("model")),
        base or "",
        (key[:6] + "…") if key else "nokey",
    ])


def reset_agent() -> None:
    """清空单例(测试用)。"""
    global _agent, _agent_fingerprint
    _agent = None
    _agent_fingerprint = None
