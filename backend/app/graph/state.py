"""
LangGraph 全局状态定义

定义 Agent 工作流中所有节点共享的全局状态结构，
基于 TypedDict 实现类型安全的状态传递。
"""
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Agent 工作流的全局状态

    贯穿整个 LangGraph 流程，各节点通过读写该状态来协作完成
    "用户问题 -> 意图澄清 -> 计划生成 -> 表结构分析 -> SQL 生成 -> 安全检查 -> 执行 -> 分析 -> 图表" 的完整链路。
    """

    # ── 输入 ──────────────────────────────────────────
    # 用户原始自然语言问题
    user_question: str

    # ── 对话历史 ──────────────────────────────────────
    # 多轮对话消息历史，使用 add_messages 归并器自动追加新消息
    messages: Annotated[list, add_messages]

    # ── Clarifier 产出 ────────────────────────────────
    # 意图是否明确（False 时触发追问）
    is_clear: bool
    # 追问文本（只有 is_clear=False 时有效）
    clarification_text: str
    # 追问选项列表
    clarification_options: list[str]
    # Clarifier 追问次数计数器（防止死循环）
    clarifier_count: int

    # ── Planner 产出 ──────────────────────────────────
    # 用户意图类型: query_data / ask_help / write_data / chart_interaction / other_questions
    intent: str
    # 意图分类的置信度，范围 0.0 ~ 1.0
    intent_confidence: float
    # 执行计划步骤列表: [{"step": "load_schema", "agent": "schema", "priority": 1}, ...]
    plan_steps: list[dict]
    # 数据是否适合用图表展示
    chart_suitable: bool

    # ── Schema Agent 产出 ─────────────────────────────
    # 格式化的数据库表结构信息字符串（供 LLM 上下文使用）
    schema_info: str
    # 根据用户意图匹配到的相关表名列表
    relevant_tables: list[str]

    # ── SQL Coder 产出 ────────────────────────────────
    # LLM 生成的目标 SQL 语句
    generated_sql: str

    # ── SQL 安全审查产出 ──────────────────────────────
    # SQL 安全分类结果，取值为 "safe"（只读查询）或 "dangerous"（写操作）
    sql_category: str

    # ── SQL 执行产出 ──────────────────────────────────
    # SQL 执行结果，每行为一个字典，键为列名
    query_result: list[dict]
    # 查询结果的列名列表（保持顺序）
    query_columns: list[str]

    # ── Quality Evaluator 产出（ReAct 质量门）───────
    # 查询结果质量: "good" | "insufficient" | "empty"
    query_quality: str
    # 质量评估的自然语言反馈（前端展示）
    quality_feedback: str
    # Analyst 基于实际数据动态判断的图表适配性
    dynamic_chart_suitable: bool

    # ── 分析 Agent 产出 ───────────────────────────────
    # 基于查询结果的自然语言分析洞察文本
    analysis_text: str
    # ECharts 图表配置 JSON，无图表时为 None
    chart_config: dict | None

    # ── 错误处理 ──────────────────────────────────────
    # 流程中发生的错误信息，无错误时为空字符串
    error_message: str

    # ── 跨轮缓存（多轮对话：上一轮的查询数据，用于 chart_interaction 快捷路径）──
    # 上一轮的查询结果，chart_interaction 时复用
    _cached_query_result: list[dict]
    # 上一轮的列名
    _cached_query_columns: list[str]

    # ── 流程控制 ──────────────────────────────────────
    # 当前流程所处的阶段标识，如 "schema_loading" / "sql_generating" / "done"
    stage: str
    # 节点索引计数器（每轮对话递增，用于标题关联）
    node_index: int
