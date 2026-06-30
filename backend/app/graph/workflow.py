"""
LangGraph 工作流定义（Phase E.9 ReAct 改造）
Plan-and-Execute + ReAct 架构：
Clarifier → Planner → Schema → SQL → Security → Execute → QualityGate → Analyst → Reporter

完整处理链路：
    clarifier ──┬── planner ──┬── schema_agent → sql_coder → security ──┬── execute_sql ──┬── quality_gate ──┬── analyst ──┬── reporter → finish
                │ (明确意图)  │                               (高危拦截)  │                 │ (ReAct质量门)    │             └── answer → finish
                │             └── rag_agent → finish                     └── misc(降级)    └── misc(降级)     └── answer → finish
                └── finish (返回追问，重新输入后进入clarifier)

ReAct 质量门（Phase E.9）：
    每个关键决策点引入 LLM 质量评估，替代简单的 if/else 规则：
    - QualityGate: 执行后 LLM 评估结果质量 → good → analyst, insufficient → misc_agent
    - Analyst: 分析同时动态判断 chart_suitable（替代 Planner 静态猜测）

条件边短路规则：
    - Clarifier: 模糊意图 → 返回追问给前端，等待用户重新输入
    - Schema: 加载失败 → finish（含友好提示）
    - SQL Coder: 生成失败 → rag_agent（知识库兜底）
    - Security: 高危/驳回 → finish
    - Execute: 空结果 → misc_agent（降级提示）
    - QualityGate: good → analyst, insufficient/empty → misc_agent（含质量反馈）
    - Analyst: dynamic_chart_suitable=true → reporter, false → answer（纯文本）
"""
import logging

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command

from app.agents.misc_agent import misc_agent
from app.agents.orchestrator import clarify_and_plan, route_planner
from app.agents.rag_agent import answer_with_rag
from app.agents.schema_agent import get_table_schemas, filter_relevant_tables
from app.agents.sql_coder import generate_sql, execute_sql, generate_and_execute_sql
from app.agents.security import classify_sql
from app.agents.analyst import analyze_results
from app.agents.reporter import generate_chart_config
from app.agents.quality_evaluator import evaluate_query_quality
from app.db.session import get_engine
from app.graph.state import AgentState
from app.core.stream import get_stream_context

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# Clarifier 最大追问次数
MAX_CLARIFIER_COUNT = 2

# ── 前端管道进度映射 ──────────────────────────────
_PIPELINE_LABELS = {
    "clarify_plan": "意图分析",
    "misc_agent": "处理请求",
    "schema_agent": "加载表结构",
    "sql_coder": "生成SQL",
    "security": "安全审核",
    "execute_sql": "执行查询",
    "quality_gate": "质量评估",
    "analyst": "数据分析",
    "reporter": "生成图表",
    "answer": "生成回答",
    "rag_agent": "知识检索",
    "chart_direct": "加载缓存",
    "finish": "完成",
}


async def _push_node_started(agent: str):
    """通过 StreamContext 向前端实时推送节点开始事件（绕过 token 队列，直写 merge_queue）。"""
    ctx = get_stream_context()
    await ctx.push_priority({
        "type": "node_started",
        "agent": agent,
        "label": _PIPELINE_LABELS.get(agent, agent),
    })

# ================================================================
# 节点函数
# ================================================================


async def clarify_plan_node(state: AgentState) -> dict:
    """
    合并 Clarifier + Planner 节点 —— 单次 LLM 调用同时完成意图澄清和执行计划生成。

    相比旧的 clarifier → planner 两次调用，节省一次 LLM 往返（~2-3s）。

    参数:
        state: 当前 Agent 全局状态，需包含 user_question

    返回:
        包含 is_clear、clarification、intent、plan_steps、chart_suitable 等字段
    """
    user_question = state.get("user_question", "")
    history = state.get("messages", [])
    clarifier_count = state.get("clarifier_count", 0)
    cached_result = state.get("_cached_query_result", [])

    await _push_node_started("clarify_plan")

    if not user_question.strip():
        return {
            "is_clear": False,
            "clarification_text": "请输入您的问题",
            "clarification_options": [],
            "intent": "query_data",
            "stage": "clarify_planned",
        }

    # ── 快速通道：关键词匹配，跳过 LLM 调用（节省 ~15s）──
    _fast_other = [
        "你好", "你是谁", "你能做什么", "帮助", "help",
        "hello", "hi", "what can you do", "who are you",
        "谢谢", "thanks", "thank you", "再见", "bye",
        "天气", "今天", "吃饭", "你是谁", "叫什么",
    ]
    _question_lower = user_question.strip().lower()
    if any(kw in _question_lower for kw in _fast_other):
        logger.info("[ClarifyPlan] 快速通道: 检测到简单对话/问候, 直接路由 misc_agent")
        return {
            "is_clear": True,
            "clarification_text": "",
            "clarification_options": [],
            "intent": "other_questions",
            "intent_confidence": 1.0,
            "plan_steps": [],
            "chart_suitable": False,
            "clarifier_count": clarifier_count,
            "stage": "clarify_planned",
        }

    # 追问次数超过限制，直接放行（防止死循环）
    if clarifier_count >= MAX_CLARIFIER_COUNT:
        logger.info(f"[ClarifyPlan] 追问次数已达上限({clarifier_count})，直接放行")
        return {
            "is_clear": True,
            "clarification_text": "",
            "clarification_options": [],
            "intent": "query_data",
            "intent_confidence": 0.5,
            "plan_steps": [
                {"step": "load_schema", "agent": "schema", "priority": 1},
                {"step": "generate_sql", "agent": "sql_coder", "priority": 2},
                {"step": "security_check", "agent": "security", "priority": 3},
                {"step": "execute_query", "agent": "execute", "priority": 4},
                {"step": "analyze_data", "agent": "analyst", "priority": 5},
                {"step": "generate_chart", "agent": "reporter", "priority": 6},
            ],
            "chart_suitable": True,
            "clarifier_count": clarifier_count,
            "stage": "clarify_planned",
        }

    # 图表追问快捷识别：有缓存数据 + 图表类型关键词 → 直接放行
    _chart_keywords = [
        "折线图", "饼图", "柱状图", "散点图", "条形图", "面积图",
        "雷达图", "图表", "可视化", "换一种图表", "换个图表",
        "换个可视化", "换图表", "用折线", "用饼", "用柱状",
        "line chart", "pie chart", "bar chart", "scatter plot",
    ]
    _question_lower = user_question.strip().lower()
    if cached_result and any(kw in _question_lower for kw in _chart_keywords):
        logger.info(f"[ClarifyPlan] 检测到图表追问(有缓存数据{len(cached_result)}行), 直接放行: {user_question[:80]}")
        return {
            "is_clear": True,
            "clarification_text": "",
            "clarification_options": [],
            "intent": "chart_interaction",
            "intent_confidence": 1.0,
            "plan_steps": [],
            "chart_suitable": True,
            "clarifier_count": clarifier_count,
            "stage": "clarify_planned",
        }

    logger.info(f"[ClarifyPlan] 合并分析意图与生成计划: {user_question[:80]}")
    result = await clarify_and_plan(user_question, history, cached_result)

    logger.info(
        "[ClarifyPlan] 结果: is_clear=%s, intent=%s, steps=%d, chart_suitable=%s",
        result["is_clear"],
        result.get("intent", "?"),
        len(result.get("plan_steps", [])),
        result.get("chart_suitable", False),
    )

    return {
        "is_clear": result["is_clear"],
        "clarification_text": result["clarification"],
        "clarification_options": result["options"],
        "intent": result["intent"],
        "intent_confidence": result["confidence"],
        "plan_steps": result["plan_steps"],
        "chart_suitable": result["chart_suitable"],
        "clarifier_count": clarifier_count + 1,
        "stage": "clarify_planned",
    }


def route_clarify_plan(state: AgentState) -> str:
    """
    ClarifyPlan 路由 —— 根据合并结果决定下一步。

    - is_clear=False → finish（返回追问给前端）
    - is_clear=True → 根据 intent 路由到对应节点
    """
    is_clear = state.get("is_clear", True)
    if not is_clear:
        return "finish"

    # 意图明确时，使用 planner 路由逻辑
    return route_planner(state)


async def misc_node(state: AgentState) -> dict:
    """
    杂项节点 —— 调用 misc Agent 回答用户。

    用于：
    - other_questions 类型问题
    - execute_sql 空结果降级提示
    - SQL 兜底回答
    """
    user_question = state.get("user_question", "")

    await _push_node_started("misc_agent")

    if not user_question.strip():
        return {
            "messages": [],
            "error_message": "用户问题为空",
            "stage": "misc",
        }

    logger.info(f"[Misc] 调用 misc Agent: {user_question[:80]}")
    result = await misc_agent(user_question)

    # 提取响应文本（兼容 AIMessage 对象和 dict 回退）
    misc_content = ""
    if hasattr(result, "content"):
        misc_content = result.content
    elif isinstance(result, dict):
        misc_content = result.get("content", "")

    logger.info(f"[Misc] Agent 完成, 响应长度={len(str(misc_content))}")
    from langchain_core.messages import AIMessage
    return {
        "messages": [AIMessage(content=misc_content)],
        "analysis_text": str(misc_content),  # 用于前端推送和标题生成
        "stage": "misc",
    }


async def schema_node(state: AgentState) -> dict:
    """
    Schema Agent 节点 —— 连接业务数据库，加载表结构并筛选相关表。

    处理步骤：
        1. 获取数据库中所有表的完整结构信息
        2. 根据用户问题中的关键词匹配，筛选出相关表
        3. 若筛选成功则仅保留相关表结构，降低后续 LLM 调用的 Token 消耗
        4. 若筛选失败则保留全部表结构作为兜底

    参数:
        state: 当前 Agent 全局状态，需包含 user_question

    返回:
        包含 schema_info、relevant_tables 和 stage 的部分状态更新；
        数据库连接失败时设置 error_message
    """
    user_question = state.get("user_question", "")

    await _push_node_started("schema_agent")

    try:
        engine = get_engine()

        # 根据用户问题筛选相关表，降低 Token 消耗
        relevant_tables = await filter_relevant_tables(engine, user_question)
        # 根据筛选结果只获取一次表结构
        schema_text = await get_table_schemas(engine, relevant_tables if relevant_tables else None)

        logger.info(
            f"[SchemaAgent] 表结构加载完成，相关表: {relevant_tables if relevant_tables else '全部'}",
        )

        return {
            "schema_info": schema_text,
            "relevant_tables": relevant_tables,
            "stage": "schema_loaded",
        }
    except Exception as exc:
        logger.exception("[SchemaAgent] 表结构加载失败")
        return {
            "error_message": f"加载表结构失败: {str(exc)}",
            "stage": "schema_loaded",
        }


async def sql_coder_node(state: AgentState) -> dict:
    """
    SQL Coder 节点 —— 调用 LLM 将自然语言问题与表结构转换为目标 SQL。

    图表追问处理（chart_interaction）：
        当用户意图为 chart_interaction（如"换一种图表"）时，当前 user_question
        仅包含图表操作请求，不含数据查询描述。此时从对话历史中提取上一轮
        用户的原始查询问题，用于重新生成 SQL，确保查询到的数据能被 Reporter
        渲染为不同类型的图表。

    关键约束：
        - 仅生成 SQL，不在此节点执行
        - SQL 执行将在 Security 节点审核通过之后，由 execute_sql 节点完成
        - 如需自校正（生成失败时重试），请在后续迭代中集成
          sql_coder.generate_and_execute_sql

    参数:
        state: 当前 Agent 全局状态，需包含 user_question 和 schema_info

    返回:
        包含 generated_sql 和 stage 的部分状态更新；
        schema_info 为空或 LLM 调用失败时设置 error_message
    """
    user_question = state.get("user_question", "")
    schema_info = state.get("schema_info", "")
    intent = state.get("intent", "query_data")

    await _push_node_started("sql_coder")

    if not schema_info:
        logger.warning("[SQLCoder] 表结构信息为空，无法生成 SQL")
        return {
            "error_message": "表结构信息为空，无法生成 SQL",
            "stage": "sql_generated",
        }

    # 图表追问：提取上一轮用户原始查询作为 context
    if intent == "chart_interaction":
        history = state.get("messages", [])
        # 从历史中找上一轮用户消息（兼容 dict 和 Message 对象）
        for m in reversed(history):
            role = _safe_get(m, "role", "") or _safe_get(m, "type", "")
            if role in ("user", "human"):
                prev_question = _safe_get(m, "content", "")
                if prev_question and prev_question.strip() != user_question.strip():
                    logger.info(f"[SQLCoder] 图表追问，使用历史问题: {prev_question[:80]}")
                    user_question = prev_question
                    break

    try:
        sql = await generate_sql(
            user_question=user_question,
            schema_info=schema_info,
        )
        logger.info(f"[SQLCoder] SQL 生成完成: {sql[:120]}")
        return {
            "generated_sql": sql,
            "stage": "sql_generated",
        }
    except Exception as exc:
        logger.exception("[SQLCoder] SQL 生成失败")
        return {
            "error_message": f"SQL 生成失败: {str(exc)}",
            "stage": "sql_generated",
        }


async def security_node(state: AgentState) -> dict:
    """
    Security 节点 —— 调用 Security Agent 审核生成的 SQL，高危操作触发审批中断。

    审核流程：
        1. 调用 security.classify_sql() 对 SQL 进行安全分类
           （采用正则 + LLM 双检策略，返回 category: "safe" 或 "dangerous"）
        2. 若为 "dangerous" 高危操作：
           a. 调用 interrupt() 挂起 Graph 执行，等待外部审批
           b. Graph 恢复时，interrupt() 返回 Command(resume=...) 传入的审批结果
           c. 审批通过 → sql_category 设为 "safe" 放行
           d. 审批驳回 → 设置 error_message，后续由 route_security 路由至 finish
        3. 若为 "safe" 安全操作：直接放行

    Human-in-the-loop 说明：
        当 interrupt() 被调用时，LangGraph 保存当前检查点并挂起执行。
        外部系统通过以下方式恢复：
            from langgraph.types import Command
            graph.invoke(Command(resume={"approved": True}), config)

        由于 LangGraph 在中断恢复后会完全重新执行节点函数，
        classify_sql() 会被调用两次（首次执行和恢复时各一次）。
        classify_sql 通过正则优先匹配保证确定性，LLM 二次确认开销可控。

    参数:
        state: 当前 Agent 全局状态，需包含 generated_sql

    返回:
        包含 sql_category、stage 的部分状态更新；
        审批驳回时额外设置 error_message
    """
    sql = state.get("generated_sql", "")

    await _push_node_started("security")

    if not sql:
        logger.warning("[Security] SQL 为空，跳过安全检查")
        return {
            "sql_category": "safe",
            "error_message": "SQL 生成结果为空，跳过安全检查",
            "stage": "security_checked",
        }

    # 调用 Security Agent 进行安全分类（正则 + LLM 双检）
    logger.info(f"[Security] 审核 SQL: {sql[:120]}")
    result = await classify_sql(sql)
    category = result["category"]

    logger.info(
        "[Security] 分类结果: category=%s, method=%s, reason=%s",
        category,
        result["method"],
        result["reason"],
    )

    if category == "dangerous":
        # ── Human-in-the-loop 审批中断 ──
        # 首次执行: interrupt() 抛出 GraphInterrupt，Graph 挂起
        # 恢复执行: interrupt() 返回 Command(resume=...) 传入的审批结果
        logger.warning("[Security] 检测到高危 SQL，等待人工审批")

        approval = interrupt({
            "type": "approval_required",
            "message": "检测到高危 SQL 操作（非只读），需要管理员审批",
            "sql": sql,
            "reason": result.get("reason", ""),
        })

        # approval 格式: {"approved": True/False, "comment": "审批备注"}
        if approval.get("approved"):
            logger.info("[Security] 审批通过，放行执行")
            return {
                "sql_category": "safe",
                "stage": "security_checked",
            }
        else:
            logger.info(
                "[Security] 审批被驳回: %s",
                approval.get("comment", "无备注"),
            )
            return {
                "sql_category": category,
                "error_message": f"审批被驳回: {approval.get('comment', '无备注')}",
                "stage": "security_checked",
            }

    # 安全操作：直接放行
    logger.info("[Security] SQL 安全检查通过（只读操作）")
    return {
        "sql_category": category,
        "stage": "security_checked",
    }


def route_security(state: AgentState) -> str:
    """
    Security 路由 —— 根据安全审查结果决定下一节点。

    路由规则（优先级从高到低）：
        1. error_message 中包含 "驳回" → "finish"（审批被拒绝，终止执行）
        2. sql_category == "safe" → "execute_sql"（安全操作或审批通过，执行 SQL）
        3. 其他情况 → "finish"（兜底终止）

    参数:
        state: 当前 Agent 全局状态，需包含 sql_category 和 error_message

    返回:
        下游节点名称: "execute_sql" 或 "finish"
    """
    sql_category = state.get("sql_category", "")
    error_message = state.get("error_message", "")

    # 审批被驳回：终止流程
    if error_message and "驳回" in error_message:
        logger.info("[Security] 路由: 审批被驳回 → finish")
        return "finish"

    # 安全操作或审批通过：进入执行
    if sql_category == "safe":
        logger.info("[Security] 路由: 安全/审批通过 → execute_sql")
        return "execute_sql"

    # 兜底：未知状态，终止流程
    logger.warning(
        "[Security] 路由: 未知状态 (category=%s) → finish",
        sql_category,
    )
    return "finish"


def route_schema(state: AgentState) -> str:
    """
    Schema 错误短路路由 —— 检测表结构加载是否出错。

    路由规则：
        - error_message 非空 → "finish"（短路，跳过后续 SQL 生成等节点）
        - error_message 为空 → "sql_coder"（正常流转）

    参数:
        state: 当前 Agent 全局状态

    返回:
        下游节点名称: "sql_coder" 或 "finish"
    """
    error_message = state.get("error_message", "")
    if error_message:
        logger.warning(f"[Schema] 检测到错误，短路到 finish: {error_message}")
        return "finish"
    return "sql_coder"


def route_sql_coder(state: AgentState) -> str:
    """
    SQL Coder 错误短路路由 —— 检测 SQL 生成是否出错。

    路由规则（Phase E.3 更新）：
        - error_message 非空 → "rag_agent"（知识库兜底回答，不直接结束）
        - error_message 为空 → "security"（正常流转）

    参数:
        state: 当前 Agent 全局状态

    返回:
        下游节点名称: "security" 或 "rag_agent"
    """
    error_message = state.get("error_message", "")
    if error_message:
        logger.warning(f"[SQLCoder] SQL 生成失败，回退到 rag_agent: {error_message}")
        return "rag_agent"
    return "security"


async def execute_node(state: AgentState) -> dict:
    """
    SQL 执行节点 —— 在业务数据库上执行已通过安全审核的 SQL。

    内置自纠错机制：
        使用 generate_and_execute_sql 替代直接执行，当 SQL 执行失败时
        （如语法错误、字段不存在），自动将错误信息反馈给 LLM 重新生成
        修正后的 SQL，最多重试 2 次，避免单次失败即终止的脆弱性。

    参数:
        state: 当前 Agent 全局状态，需包含 generated_sql、user_question、
               schema_info

    返回:
        成功时：包含 query_result、query_columns、generated_sql（可能已修正）
               和 stage
        失败时：额外设置 error_message 描述失败原因
    """
    engine = get_engine()
    sql = state.get("generated_sql", "")
    user_question = state.get("user_question", "")
    schema_info = state.get("schema_info", "")

    await _push_node_started("execute_sql")

    if not sql:
        logger.warning("[Executor] 无可执行的 SQL")
        return {
            "error_message": "无可执行的 SQL",
            "stage": "executed",
        }

    logger.info(f"[Executor] 执行 SQL（启用自纠错，最多 2 次重试）: {sql[:120]}")

    try:
        # 使用 generate_and_execute_sql 获得自动重试能力
        # 首次执行失败时，将错误反馈给 LLM 修正 SQL 后重新执行
        result = await generate_and_execute_sql(
            user_question=user_question,
            engine=engine,
            schema_info=schema_info,
            max_retries=2,
            initial_sql=sql,  # 传入 SQL Coder 已生成的 SQL，避免重复生成
        )

        if not result["success"]:
            logger.error(
                "[Executor] SQL 执行失败（已重试 %d 次）: %s",
                result["retries"],
                result["error"],
            )
            return {
                "query_result": [],
                "query_columns": [],
                "error_message": (
                    f"SQL 执行失败（已重试 {result['retries']} 次）: {result['error']}"
                ),
                "stage": "executed",
            }

        rows = result["data"]
        columns = list(rows[0].keys()) if rows else []
        final_sql = result["sql"]

        logger.info(
            "[Executor] 查询完成，返回 %d 行数据（重试 %d 次）",
            len(rows),
            result["retries"],
        )

        return {
            "query_result": rows,
            "query_columns": columns,
            "generated_sql": final_sql,  # 可能已被 LLM 修正
            "stage": "executed",
        }
    except Exception as exc:
        logger.exception("[Executor] SQL 执行异常")
        return {
            "query_result": [],
            "query_columns": [],
            "error_message": f"SQL 执行异常: {str(exc)}",
            "stage": "executed",
        }


def route_execute(state: AgentState) -> str:
    """
    Execute 执行后路由 —— 空结果降级，有数据进入 QualityGate。

    路由规则（Phase E.9 ReAct 改造）：
        - 查询结果为空或存在错误 → "misc_agent"（降级提示）
        - 有查询结果 → "quality_gate"（LLM 评估质量后再决定去向）

    参数:
        state: 当前 Agent 全局状态

    返回:
        下游节点名称: "quality_gate" 或 "misc_agent"
    """
    query_result = state.get("query_result", [])
    error_message = state.get("error_message", "")
    if not query_result or error_message:
        logger.info("[Execute] 路由: 空结果或错误 → misc_agent（降级）")
        return "misc_agent"
    logger.info(f"[Execute] 路由: 有数据 ({len(query_result)} 行) → quality_gate（ReAct 质量评估）")
    return "quality_gate"


# ================================================================
# QualityGate 节点（Phase E.9 — ReAct 质量门）
# ================================================================


async def quality_gate_node(state: AgentState) -> dict:
    """
    QualityGate 节点 —— ReAct 范式：执行后评估结果质量，决定后续路由。

    使用 LLM 判断查询结果是否充分回答了用户问题：
    - "good": 结果有意义 → 进入 Analyst 分析
    - "insufficient": 数据太少/无意义 → 进入 Misc 降级处理
    - "empty": 空结果 → 进入 Misc 降级处理

    参数:
        state: 当前 Agent 全局状态，需包含 user_question、generated_sql、
               query_result、query_columns

    返回:
        包含 query_quality、quality_feedback、stage 的部分状态更新
    """
    user_question = state.get("user_question", "")
    sql = state.get("generated_sql", "")
    data = state.get("query_result", [])
    columns = state.get("query_columns", [])

    await _push_node_started("quality_gate")

    logger.info(f"[QualityGate] 开始 ReAct 质量评估: {user_question[:60]}, rows={len(data)}")

    try:
        result = await evaluate_query_quality(
            question=user_question,
            sql=sql,
            data=data,
            columns=columns,
        )

        quality = result["quality"]
        feedback = result.get("feedback", "")
        reason = result.get("reason", "")

        logger.info(
            "[QualityGate] 评估完成: quality=%s, reason=%s",
            quality,
            reason[:100] if reason else "",
        )

        return {
            "query_quality": quality,
            "quality_feedback": feedback,
            "stage": "quality_evaluated",
        }

    except Exception as exc:
        logger.exception("[QualityGate] 评估失败，默认放行")
        return {
            "query_quality": "good",
            "quality_feedback": "",
            "stage": "quality_evaluated",
        }


def route_quality_gate(state: AgentState) -> str:
    """
    QualityGate 路由 —— 根据质量评估结果决定去向。

    路由规则（ReAct 范式）：
        - quality="good" → "analyst"（继续分析）
        - quality="insufficient" → "misc_agent"（降级，告知用户数据不足）
        - quality="empty" → "misc_agent"（降级）

    参数:
        state: 当前 Agent 全局状态

    返回:
        下游节点名称: "analyst" 或 "misc_agent"
    """
    quality = state.get("query_quality", "good")

    if quality == "good":
        logger.info("[QualityGate] 路由: 质量达标 → analyst")
        return "analyst"

    logger.info(
        "[QualityGate] 路由: 质量不足 (quality=%s) → misc_agent（降级）",
        quality,
    )
    return "misc_agent"


async def analyst_node(state: AgentState) -> dict:
    """
    Analyst 节点 —— 对 SQL 查询结果进行统计分析与洞察生成。

    调用 Analyst Agent 对查询返回的数据做数值统计（计数、求和、
    均值、最大最小值等）并生成自然语言洞察和异常检测结果。
    分析失败不阻塞流程：异常时仅设置 error_message 而不中断。

    Phase E.9 ReAct 改造:
        分析完成后调用 evaluate_chart_suitability 动态判断数据是否适合
        生成图表，替代 Planner 阶段静态的 chart_suitable 判断。

    参数:
        state: 当前 Agent 全局状态，需包含 user_question、generated_sql、
               query_result、query_columns

    返回:
        包含 analysis_text、dynamic_chart_suitable 和 stage 的部分状态更新
    """
    query_result = state.get("query_result", [])
    query_columns = state.get("query_columns", [])
    user_question = state.get("user_question", "")
    sql = state.get("generated_sql", "")

    await _push_node_started("analyst")

    # 查询结果为空时跳过分析
    if not query_result or not query_columns:
        logger.info("[Analyst] 查询结果为空，跳过数据分析")
        return {
            "stage": "analyzed",
            "dynamic_chart_suitable": False,
        }

    analysis_text = ""
    dynamic_chart_suitable = False

    try:
        logger.info(
            "[Analyst] 开始分析结果: %d 行 %d 列",
            len(query_result),
            len(query_columns),
        )
        result = await analyze_results(
            question=user_question,
            sql=sql,
            data=query_result,
            columns=query_columns,
        )

        # analysis_text 现在是 LLM 实时流式输出的完整 Markdown 文本
        # token 已通过 StreamContext.push_token 实时推送到前端，无需再拼装
        analysis_text = result.get("summary", "")

        logger.info(f"[Analyst] 分析完成: 文本长度 {len(analysis_text)}, chart_suitable={dynamic_chart_suitable}")

        # ── ReAct: 从分析结果中获取动态图表适配性 ──────
        # analyze_results 已在同一 LLM 调用中判断 chart_suitable
        dynamic_chart_suitable = result.get("chart_suitable", False)
        logger.info(
            "[Analyst] 动态图表适配性: suitable=%s (来自分析LLM)",
            dynamic_chart_suitable,
        )

        return {
            "analysis_text": analysis_text,
            "dynamic_chart_suitable": dynamic_chart_suitable,
            "stage": "analyzed",
        }
    except Exception as exc:
        # 分析失败不中断流程，仅记录错误信息
        logger.exception("[Analyst] 数据分析失败")
        return {
            "error_message": f"数据分析失败: {str(exc)}",
            "dynamic_chart_suitable": False,
            "stage": "analyzed",
        }


def route_analyst(state: AgentState) -> str:
    """
    Analyst 路由 —— 根据 dynamic_chart_suitable 决定是否生成图表。

    路由规则（Phase E.9 ReAct 改造）：
        - dynamic_chart_suitable=True → "reporter"（生成 ECharts 图表）
        - dynamic_chart_suitable=False → "answer"（纯文本输出）
        - 若 dynamic_chart_suitable 未设置，回退到 Planner 的 chart_suitable

    参数:
        state: 当前 Agent 全局状态

    返回:
        下游节点名称: "reporter" 或 "answer"
    """
    # 优先使用 Analyst 动态评估结果，回退到 Planner 的静态判断
    dynamic = state.get("dynamic_chart_suitable")
    if dynamic is not None:
        if dynamic:
            logger.info("[Analyst] 路由: dynamic_chart_suitable=true → reporter")
            return "reporter"
        logger.info("[Analyst] 路由: dynamic_chart_suitable=false → answer（纯文本）")
        return "answer"

    # 回退: 使用 Planner 的静态判断
    chart_suitable = state.get("chart_suitable", False)
    if chart_suitable:
        logger.info("[Analyst] 路由: chart_suitable=true（静态） → reporter")
        return "reporter"
    logger.info("[Analyst] 路由: chart_suitable=false（静态） → answer（纯文本）")
    return "answer"


async def reporter_node(state: AgentState) -> dict:
    """
    Reporter 节点 —— 根据查询结果生成 ECharts 图表配置。

    调用 Reporter Agent 根据数据特征自动选择图表类型（柱状图/
    饼图/折线图）并生成前端渲染所需的完整 ECharts option JSON。
    图表生成失败不阻塞流程：异常时仅设置 error_message 而不中断。

    图表追问（chart_interaction）：
        当意图为 chart_interaction 时，将当前的 follow-up 问题
        （如"换一种图表""用饼图展示"）传递给 Reporter，LLM 会根据
        用户明确的图表类型偏好生成不同配置。

    参数:
        state: 当前 Agent 全局状态，需包含 user_question、
               query_result、query_columns

    返回:
        包含 chart_config 和 stage 的部分状态更新
    """
    query_result = state.get("query_result", [])
    query_columns = state.get("query_columns", [])
    user_question = state.get("user_question", "")
    intent = state.get("intent", "query_data")

    await _push_node_started("reporter")

    # 查询结果为空时跳过图表生成
    if not query_result or not query_columns:
        logger.info("[Reporter] 查询结果为空，跳过图表生成")
        return {"stage": "reported"}

    # 图表追问：使用当前问题（包含"换一种图表"等指令）传递给 Reporter，
    # 让 LLM 知道用户想换图表类型
    report_question = user_question
    if intent == "chart_interaction":
        logger.info(f"[Reporter] 图表追问模式，问题: {user_question[:80]}")

    try:
        logger.info("[Reporter] 开始生成图表配置")
        result = await generate_chart_config(
            question=report_question,
            data=query_result,
            columns=query_columns,
        )

        logger.info(f"[Reporter] 图表生成完成: type={result.get("chart_type")}")

        return {
            "chart_config": result if result.get("chart_type") != "none" else None,
            "stage": "reported",
        }
    except Exception as exc:
        # 图表生成失败不中断流程，仅记录错误信息
        logger.exception("[Reporter] 图表生成失败")
        return {
            "error_message": f"图表生成失败: {str(exc)}",
            "stage": "reported",
        }


async def answer_node(state: AgentState) -> dict:
    """
    Answer 节点 —— 纯文本回答（chart_suitable=false 时替代 reporter）。

    当 Analyst 判断数据不适合用图表展示时，工作流路由到此节点，
    直接以纯文本形式输出分析结果。此节点无需额外处理，
    仅标记阶段状态。

    参数:
        state: 当前 Agent 全局状态，需包含 analysis_text

    返回:
        包含 stage 的部分状态更新
    """
    analysis_text = state.get("analysis_text", "")
    await _push_node_started("answer")
    logger.info(f"[Answer] 纯文本回答: {analysis_text[:80] if analysis_text else "无内容"}")
    return {"stage": "answered"}


async def rag_node(state: AgentState) -> dict:
    """
    RAG 检索节点 —— 处理帮助咨询类问题。

    当用户意图为 ask_help 时，Orchestrator 会将请求路由到此节点。
    调用 RAG Agent 从 Milvus 向量数据库检索相关操作规范和指标定义，
    然后由 LLM 基于检索结果生成自然语言回答。

    参数:
        state: 当前 Agent 全局状态，需包含 user_question

    返回:
        包含 analysis_text 和 stage 的部分状态更新；
        检索或 LLM 调用失败时设置 error_message
    """
    user_question = state.get("user_question", "")

    await _push_node_started("rag_agent")

    if not user_question.strip():
        logger.warning("[RAGAgent] 用户问题为空")
        return {
            "error_message": "用户问题为空",
            "stage": "rag_done",
        }

    try:
        logger.info(f"[RAGAgent] 开始 RAG 检索与回答: {user_question[:80]}")
        answer = await answer_with_rag(user_question)
        logger.info(f"[RAGAgent] RAG 回答完成: {answer[:80]}")

        return {
            "analysis_text": answer,
            "stage": "rag_done",
        }
    except Exception as exc:
        logger.exception("[RAGAgent] RAG 检索失败")
        return {
            "error_message": f"RAG 检索失败: {str(exc)}",
            "stage": "rag_done",
        }


def _safe_get(msg, key: str, default=""):
    """安全地从 dict 或 Message 对象中获取字段值。"""
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


async def chart_direct_node(state: AgentState) -> dict:
    """
    图表直接渲染节点 —— chart_interaction 快捷路径。

    当用户意图为 chart_interaction 且已有上轮查询缓存数据时，
    跳过 schema → sql → security → execute → quality_gate 全链路，
    直接将上轮的查询结果和列名写入当前状态，交由 analyst → reporter 处理。

    参数:
        state: 当前 Agent 全局状态，需包含 _cached_query_result 和 _cached_query_columns

    返回:
        包含 query_result、query_columns、query_quality 的部分状态更新
    """
    cached_result = state.get("_cached_query_result", [])
    cached_columns = state.get("_cached_query_columns", [])

    await _push_node_started("chart_direct")

    logger.info(
        "[ChartDirect] 图表快捷路径: 复用上轮数据 %d 行 %d 列",
        len(cached_result),
        len(cached_columns),
    )

    return {
        "query_result": cached_result,
        "query_columns": cached_columns,
        "query_quality": "good",  # 跳过 quality_gate
        "stage": "chart_direct",
    }


async def finish_node(state: AgentState) -> dict:
    """
    结束节点 —— 标记工作流执行完毕。

    作为 Graph 的最终节点，将 stage 设置为 "finished" 以表示整个
    Multi-Agent 协作流程已完成。此节点连接到 END 终止符。

    参数:
        state: 当前 Agent 全局状态

    返回:
        包含 stage 的部分状态更新
    """
    # 递增节点索引（每轮对话+1，从0开始）
    current_index = state.get("node_index", 0)
    await _push_node_started("finish")
    logger.info(f"[Finish] 工作流执行完毕，stage={state.get("stage")}, node_index={"unknown"}")
    return {"stage": "finished", "node_index": current_index + 1}

# ================================================================
# 检查点管理（应用生命周期级别）
# ================================================================

_checkpointer = None    # 全局检查点实例


async def init_checkpointer():
    """
    在应用启动时初始化检查点保存器。
    必须在 async 环境（FastAPI lifespan）中调用。

    优先使用 PlainRedisSaver（纯 Redis，不依赖 RediSearch 模块），
    Redis 不可用时回退到 InMemorySaver。
    """
    global _checkpointer
    from app.core.config import settings

    try:
        from app.graph.redis_saver import PlainRedisSaver

        logger.info(f"[Workflow] PlainRedis 检查点初始化: {settings.REDIS_URL}")
        _checkpointer = PlainRedisSaver(redis_url=settings.REDIS_URL)
        await _checkpointer.asetup()

        logger.info(f"[Workflow] PlainRedis 检查点初始化成功: {settings.REDIS_URL}")
    except Exception as exc:
        logger.warning(
            "[Workflow] PlainRedis 检查点不可用 (%s)，回退到 MemorySaver",
            str(exc),
        )
        from langgraph.checkpoint.memory import InMemorySaver
        _checkpointer = InMemorySaver()


async def close_checkpointer():
    """
    在应用关闭时清理检查点资源。
    必须在 async 环境（FastAPI lifespan）中调用。
    """
    global _checkpointer
    if _checkpointer is not None:
        if hasattr(_checkpointer, "aclose"):
            try:
                await _checkpointer.aclose()
                logger.info("[Workflow] 检查点已关闭")
            except Exception as exc:
                logger.warning(f"[Workflow] 关闭检查点异常: {exc}")
    _checkpointer = None
# ================================================================
# Graph 构建与编译
# ================================================================

# 全局编译后的 Graph 单例
_graph = None


def get_graph():
    """
    获取已编译的 LangGraph 工作流实例（全局单例）。

    首次调用时：
        1. 构建 StateGraph 并注册所有节点和边
        2. 创建检查点保存器（优先 Redis，回退 MemorySaver）
        3. 编译 Graph 并缓存为全局单例

    后续调用直接返回缓存实例，避免重复编译开销。

    检查点策略：
        - 优先尝试 Redis AsyncRedisSaver（支持持久化、分布式、中断恢复）
        - 若 Redis 不可用（依赖未安装或连接失败），回退到 MemorySaver
        - 检查点是 interrupt() 中断/恢复机制的必要依赖

    返回:
        编译好的 StateGraph 实例，可通过 .invoke() / .astream() 执行
    """
    global _graph
    if _graph is not None:
        return _graph

    # ── 构建状态图（Phase E.3 Plan-and-Execute 架构） ──
    builder = StateGraph(AgentState)

    # 注册所有节点
    builder.add_node("clarify_plan", clarify_plan_node)  # 合并 Clarifier + Planner
    builder.add_node("misc_agent", misc_node)
    builder.add_node("schema_agent", schema_node)
    builder.add_node("sql_coder", sql_coder_node)
    builder.add_node("security", security_node)
    builder.add_node("execute_sql", execute_node)
    builder.add_node("quality_gate", quality_gate_node)  # Phase E.9 ReAct 质量门
    builder.add_node("analyst", analyst_node)
    builder.add_node("reporter", reporter_node)
    builder.add_node("answer", answer_node)
    builder.add_node("rag_agent", rag_node)
    builder.add_node("chart_direct", chart_direct_node)  # chart_interaction 快捷路径
    builder.add_node("finish", finish_node)

    # ── 注册边（定义节点间的流转关系） ────────────────

    # 入口：clarify_plan 为起始节点（合并 Clarifier + Planner）
    builder.set_entry_point("clarify_plan")

    # ① clarify_plan → 条件路由：模糊→finish，明确→按意图分发
    builder.add_conditional_edges(
        "clarify_plan",
        route_clarify_plan,
        {
            "finish": "finish",
            "schema_agent": "schema_agent",
            "rag_agent": "rag_agent",
            "misc_agent": "misc_agent",
            "chart_direct": "chart_direct",
        },
    )

    # ③ schema_agent → 条件路由：加载失败 → finish，成功 → sql_coder
    builder.add_conditional_edges(
        "schema_agent",
        route_schema,
        {
            "sql_coder": "sql_coder",
            "finish": "finish",
        },
    )

    # ④ sql_coder → 条件路由：生成失败 → rag_agent（知识库兜底），成功 → security
    builder.add_conditional_edges(
        "sql_coder",
        route_sql_coder,
        {
            "security": "security",
            "rag_agent": "rag_agent",
        },
    )

    # ⑤ security → 条件路由：安全/审批通过 → execute_sql，驳回 → finish
    builder.add_conditional_edges(
        "security",
        route_security,
        {
            "execute_sql": "execute_sql",
            "finish": "finish",
        },
    )

    # ⑥ execute_sql → 条件路由：空结果/错误 → misc_agent（降级），有数据 → quality_gate（ReAct质量门）
    builder.add_conditional_edges(
        "execute_sql",
        route_execute,
        {
            "quality_gate": "quality_gate",
            "misc_agent": "misc_agent",
        },
    )

    # ⑥½ quality_gate → 条件路由：good → analyst，insufficient/empty → misc_agent（ReAct质量门）
    builder.add_conditional_edges(
        "quality_gate",
        route_quality_gate,
        {
            "analyst": "analyst",
            "misc_agent": "misc_agent",
        },
    )

    # ⑦ analyst → 条件路由：dynamic_chart_suitable=true → reporter，false → answer（纯文本）
    builder.add_conditional_edges(
        "analyst",
        route_analyst,
        {
            "reporter": "reporter",
            "answer": "answer",
        },
    )

    # ⑧ reporter → finish（图表生成完毕）
    builder.add_edge("reporter", "finish")

    # ⑧½ chart_direct → analyst → reporter（chart_interaction 快捷路径）
    builder.add_edge("chart_direct", "analyst")

    # ⑨ answer → finish（纯文本回答完毕）
    builder.add_edge("answer", "finish")

    # ⑩ misc_agent → finish（杂项处理完毕）
    builder.add_edge("misc_agent", "finish")

    # ⑪ rag_agent → finish（知识库检索完毕）
    builder.add_edge("rag_agent", "finish")

    # ⑫ finish → END（终止节点）
    builder.add_edge("finish", END)

    # ✅ 使用全局已初始化的检查点实例
    if _checkpointer is None:
        logger.warning("[Workflow] 检查点未初始化，使用 None（不支持中断恢复）")

    _graph = builder.compile(checkpointer=_checkpointer)
    logger.info("[Workflow] LangGraph 工作流编译完成")
    return _graph


# ================================================================
# DeepAgent 模式：基于 deepagents 库的智能调度入口
# ================================================================

# DeepAgent 全局单例
_deep_agent = None

# 是否启用 DeepAgent 模式（通过环境变量 USE_DEEP_AGENT=true 控制）
import os as _os
_USE_DEEP_AGENT = _os.getenv("USE_DEEP_AGENT", "false").lower() in ("true", "1", "yes")


def use_deep_agent() -> bool:
    """检查当前是否启用了 DeepAgent 模式。"""
    return _USE_DEEP_AGENT


async def get_deep_agent():
    """
    获取 DeepAgent 实例（全局单例，首次调用时异步初始化）。

    DeepAgent 作为顶层调度中心，集成：
    - TodoListMiddleware:  复杂任务自动拆解与跟踪
    - FilesystemMiddleware: 中间结果持久化 / 长期记忆
    - SubAgentMiddleware:   动态子 Agent 委派（data-query / knowledge-retrieval）
    - Anthropic Skills:     企业微信通知 / 定时报表 / 外部API

    返回:
        DeepAgent 实例，支持 .astream() 和 .invoke() 方法
    """
    global _deep_agent
    if _deep_agent is not None:
        return _deep_agent

    from app.deepagent.harness import create_deep_agent, create_skill_tools
    from app.deepagent.prompts import build_system_prompt
    from app.graph.subagents import (
        build_sql_pipeline_subagent,
        build_rag_subagent,
    )

    logger.info("[DeepAgent] 开始初始化 DeepAgent 模式...")

    # 1. 加载 Anthropic Skills
    skill_tools, skills_instructions = await create_skill_tools()

    # 2. 构建预编译子 Agent
    sql_sub = await build_sql_pipeline_subagent()
    rag_sub = await build_rag_subagent()

    # 3. 构建系统提示词（含 Skills 指令）
    system_prompt = build_system_prompt(skills_instructions)

    # 4. 创建 DeepAgent
    _deep_agent = create_deep_agent(
        subagents=[sql_sub, rag_sub],
        tools=skill_tools,
        system_prompt=system_prompt,
    )

    logger.info(
        "[DeepAgent] 初始化完成: subagents=%d, skills=%d",
        2,
        len(skill_tools),
    )
    return _deep_agent


async def get_graph_async():
    """
    统一的 Graph 获取入口（异步版本）。

    根据 USE_DEEP_AGENT 环境变量自动选择：
    - USE_DEEP_AGENT=true → 返回 DeepAgent 实例（新架构）
    - USE_DEEP_AGENT=false → 返回传统 LangGraph 工作流（旧架构，默认）

    返回:
        支持 .astream() / .invoke() 的 Graph 实例
    """
    if use_deep_agent():
        return await get_deep_agent()
    return get_graph()


# ================================================================
# DeepAgent 桥接适配器：将 AgentState 格式桥接到 DeepAgent
# ================================================================


class DeepAgentBridge:
    """
    DeepAgent 桥接器 — 将传统 AgentState 格式与 DeepAgent 消息格式互转。

    DeepAgent 使用标准消息格式:
        {"messages": [{"role": "user", "content": "..."}]}

    传统 AgentState 使用:
        {"user_question": "..."}
    """

    @staticmethod
    def state_to_messages(state: dict) -> dict:
        """将 AgentState 转换为 DeepAgent 输入格式。"""
        question = state.get("user_question", "")
        return {"messages": [{"role": "user", "content": question}]}

    @staticmethod
    async def astream_deep_agent(deep_agent, state: dict, config: dict):
        """
        使用 DeepAgent 处理请求并流式产出状态更新。

        包装 deep_agent.astream()，将输出转换为兼容 AgentState 的格式，
        保持与现有 SSE 流式处理逻辑的兼容。

        参数:
            deep_agent: DeepAgent 实例
            state: 原始 AgentState（含 user_question）
            config: LangGraph 配置（含 thread_id）

        产出:
            每个事件一个 (node_name, state_update) 元组，格式兼容现有 SSE 逻辑
        """
        input_data = DeepAgentBridge.state_to_messages(state)

        try:
            async for event in deep_agent.astream(input_data, config):
                # DeepAgent 的 astream 事件格式为 {node_name: update}
                for node_name, update in event.items():
                    # 将 DeepAgent 的消息格式映射回 AgentState
                    mapped = {"stage": node_name}
                    if "messages" in update:
                        for msg in update["messages"]:
                            if hasattr(msg, "content"):
                                mapped["analysis_text"] = msg.content
                    yield (node_name, mapped)
        except Exception as exc:
            logger.exception("[DeepAgentBridge] 流式处理异常")
            yield ("error", {"error_message": str(exc), "stage": "error"})



