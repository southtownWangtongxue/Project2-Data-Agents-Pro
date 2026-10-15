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
3. 分析结果:基于返回的 rows/columns 做统计与洞察(计数/汇总/对比/异常);
4. 可视化:数据适合图表时调用 make_chart 生成图表配置(用户指定了图表类型时,
   通过 chart_type 参数传入);
5. 输出回答:先给结论,再给关键数字,最后给数据口径(SQL 与行数)。

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


def build_harness_agent() -> Any:
    """构建(首次)/返回(全局单例)Harness 主循环 Agent。

    单例按「构建时的 provider 指纹」缓存:管理台切换模型(或 patch 变更 provider)
    后指纹变化,下次调用自动重建 Agent——否则换模型必须重启后端才生效。
    """
    global _agent, _agent_fingerprint
    fingerprint = _provider_fingerprint()
    if _agent is not None and fingerprint == _agent_fingerprint:
        return _agent

    from app.deepagent.tools import web_search_tool

    tools = apply_tool_pipeline([*get_data_tools(), web_search_tool])
    _agent = _create(
        model=_build_model(),
        tools=tools,
        middleware=[SqlGateMiddleware()],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=_build_checkpointer(),
    )
    _agent_fingerprint = fingerprint
    log.info(
        "[Harness] 主循环装配完成: tools=%d middleware=SqlGate checkpointer=on fingerprint=%s",
        len(tools), fingerprint,
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
