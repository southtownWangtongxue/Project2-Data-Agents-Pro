"""
Orchestrator Agent - 控制枢纽（Phase E.3 重设计）
拆分为 Clarifier（意图澄清）+ Planner（执行计划）双阶段。

Clarifier: 分析用户意图模糊度，必要时触发追问
Planner: 生成结构化执行计划，包含 chart_suitable 标志
"""
import json

from app.core.config import settings
from app.core.llm import get_llm
from app.core.stream import get_stream_context
from app.utils.log_utils import log

# ── Clarifier 阶段 ────────────────────────────────────────────────


async def clarify_intent(user_question: str, history: list[dict] | None = None) -> dict:
    """
    分析用户意图的明确程度，必要时生成追问选项。

    返回:
        {
            "is_clear": bool,          # 意图是否明确
            "clarification": str,      # 追问文本（不明确时）
            "options": list[str],      # 追问选项（不明确时）
        }
    """
    client = get_llm()

    system_prompt = (
        "你是一个智能意图分析专家。"
        "请分析用户的问题是否表述清晰，能够直接转换为数据分析任务。\n\n"
        "模糊度判断标准：\n"
        "- 高模糊：问题范围太宽泛，缺少关键信息。例如：\n"
        '  "我当前有哪些数据" → 用户可能想看表列表，也可能想查具体数据\n'
        '  "帮我分析一下" → 缺少分析目标和范围\n\n'
        "- 中模糊：主题明确但缺少维度/时间/指标。例如：\n"
        '  "分析销售趋势" → 需要指定时间范围和指标\n'
        '  "用户增长情况" → 需要指定时间段\n\n'
        "- 低模糊（明确）：包含具体的表名、时间范围、指标等。例如：\n"
        '  "查询a_sheet1表上个月销售额TOP10"\n'
        '  "统计本月订单总数"\n\n'
        "- 闲聊/通用问题：问候、能力询问等。例如：\n"
        '  "你好" "你能做什么" → 直接回答即可，无需执行数据任务\n\n'
        "- **图表追问（重要）**：如果用户仅输入图表类型名称（如\"折线图\"\"饼图\"\"柱状图\"等），\n"
        '  或要求更换图表展示（如\"换一种图表\"），且对话历史中已有数据查询结果，则is_clear必须为true，\n'
        '  这属于图表操作类追问，不需要额外澄清。\n\n'
        "严格要求：\n"
        "1. 只返回一个 JSON 对象，不要包含任何其他文字\n"
        "2. JSON 格式: {\"is_clear\": true/false, \"clarification\": \"追问文本\", \"options\": [\"选项1\", \"选项2\"]}\n"
        "3. 如果意图明确，clarification 和 options 可以留空（空字符串和空数组）\n"
        "4. 如果意图不明确，options 提供 2-4 个具体可点击的选项\n"
        "5. 不要使用 markdown 代码块包裹 JSON"
    )

    user_message = f"请分析以下用户问题的明确程度：\n\n{user_question}"
    if history:
        history_text = "\n".join(
            [f"[{_get_msg_role(m)}]: {_get_msg_content(m)[:200]}" for m in history[-6:]]
        )
        user_message = (
            f"## 对话历史\n{history_text}\n\n## 当前问题\n{user_question}"
        )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            stream=True,
        )
        ctx = get_stream_context()
        content_chunks = []
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                content_chunks.append(token)
                # 不推送到 stream_queue：Clarifier 输出的是内部 JSON，非用户可见内容
        content = "".join(content_chunks).strip()

        if content.startswith("```"):
            content = _extract_json_from_markdown(content)

        result = json.loads(content)
        return {
            "is_clear": result.get("is_clear", True),
            "clarification": result.get("clarification", ""),
            "options": result.get("options", []),
        }
    except (json.JSONDecodeError, Exception):
        # 解析失败默认视为明确意图，走原有流程
        return {"is_clear": True, "clarification": "", "options": []}




# ── Planner 阶段 ──────────────────────────────────────────────────


async def generate_plan(
    user_question: str, history: list[dict] | None = None
) -> dict:
    """
    生成结构化执行计划，包含意图分类、步骤顺序和图表适用性判断。

    返回:
        {
            "intent": "query_data" | "ask_help" | "write_data" | "chart_interaction" | "other_questions",
            "confidence": float,
            "plan_steps": [{"step": str, "agent": str, "priority": int}, ...],
            "chart_suitable": bool,
            "reasoning": str,
        }
    """
    client = get_llm()

    system_prompt = (
        "你是一个数据任务执行计划专家。根据用户问题，生成结构化的执行计划。\n\n"
        "意图分类：\n"
        "1. query_data —— 数据查询/统计（生成 SQL → 执行 → 分析）\n"
        "2. ask_help —— 帮助咨询（走 RAG 知识库检索）\n"
        "3. write_data —— 数据写入/修改（需要审批）\n"
        "4. chart_interaction —— 图表操作（换图表类型等）\n"
        "5. other_questions —— 其他问题（闲聊/通用）\n\n"
        "执行步骤命名规范（agent 字段）：\n"
        "- load_schema: 加载表结构 (agent: schema)\n"
        "- generate_sql: 生成 SQL (agent: sql_coder)\n"
        "- security_check: 安全检查 (agent: security)\n"
        "- execute_query: 执行查询 (agent: execute)\n"
        "- analyze_data: 数据分析 (agent: analyst)\n"
        "- generate_chart: 生成图表 (agent: reporter)\n"
        "- rag_retrieval: 知识库检索 (agent: rag)\n"
        "- answer_text: 文本回答 (agent: misc)\n\n"
        "chart_suitable 判断：\n"
        "- 用户明确问排行/趋势/占比/对比 → true\n"
        "- 用户问列表/详情/具体值 → false\n"
        "- 数据查询类默认 true（可被 analyst 覆盖）\n"
        "- 帮助咨询/其他问题 → false\n\n"
        "图表追问识别（重要）：\n"
        "- 若用户输入的是简短的图表类型名称（如\"折线图\"\"饼图\"\"柱状图\"\"散点图\"），或者表示要更换图表展示方式\n"
        "  （如\"换一种图表\"\"换个可视化\"\"用XX图展示\"），则意图必须归类为 chart_interaction\n"
        "- 若用户问题仅提到图表类型但没有任何数据查询描述，也应归类为 chart_interaction\n\n"
        "严格要求：只返回 JSON，不要 markdown 包裹"
    )

    user_message = f"请为以下用户问题生成执行计划：\n\n{user_question}"
    if history:
        history_text = "\n".join(
            [f"[{_get_msg_role(m)}]: {_get_msg_content(m)[:200]}" for m in history[-6:]]
        )
        user_message = (
            f"## 对话历史\n{history_text}\n\n## 当前问题\n{user_question}"
        )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            stream=True,
        )
        ctx = get_stream_context()
        content_chunks = []
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                content_chunks.append(token)
                # 不推送到 stream_queue：Planner 输出的是内部 JSON，非用户可见内容
        content = "".join(content_chunks).strip()

        if content.startswith("```"):
            content = _extract_json_from_markdown(content)

        result = json.loads(content)
        valid_intents = {"query_data", "ask_help", "write_data", "chart_interaction", "other_questions"}
        intent = result.get("intent", "query_data")
        if intent not in valid_intents:
            intent = "query_data"

        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.5))))

        return {
            "intent": intent,
            "confidence": confidence,
            "plan_steps": result.get("plan_steps", []),
            "chart_suitable": result.get("chart_suitable", intent == "query_data"),
            "reasoning": result.get("reasoning", ""),
        }
    except (json.JSONDecodeError, Exception):
        return {
            "intent": "query_data",
            "confidence": 0.5,
            "plan_steps": [
                {"step": "load_schema", "agent": "schema", "priority": 1},
                {"step": "generate_sql", "agent": "sql_coder", "priority": 2},
                {"step": "security_check", "agent": "security", "priority": 3},
                {"step": "execute_query", "agent": "execute", "priority": 4},
                {"step": "analyze_data", "agent": "analyst", "priority": 5},
                {"step": "generate_chart", "agent": "reporter", "priority": 6},
            ],
            "chart_suitable": True,
            "reasoning": "默认查询计划（LLM 解析失败兜底）",
        }


async def analyze_intent(user_question: str, history: list[dict] | None = None) -> dict:
    """
    调用 LLM 分析用户意图，分类为查询数据、询问帮助或写入数据。

    参数:
        user_question: 用户输入的自然语言问题
        history: 对话历史消息列表（用于多轮追问的上下文理解）

    返回:
        {
            "intent": "query_data" | "ask_help" | "write_data" | "chart_interaction" | "other_questions",
            "confidence": float  # 置信度，范围 0.0 ~ 1.0
        }

        若 LLM 返回解析失败，默认返回 query_data 兜底。
    """
    client = get_llm()

    system_prompt = (
        "你是一个智能路由分析专家。"
        "请分析用户的问题，判断其意图属于以下哪一类：\n\n"
        "1. query_data —— 用户想要查询、检索或统计数据（生成 SQL 查询）\n"
        "   示例: \"上个月销量最高的产品是什么？\" \"有多少注册用户？\"\n\n"
        "2. ask_help —— 用户询问系统使用方法、功能说明或概念性问题（走 RAG 知识库）\n"
        "   示例: \"怎么导出报表？\" \"这个系统支持哪些数据库？\" \"什么是索引？\"\n\n"
        "3. write_data —— 用户想要插入、更新、删除数据或修改表结构（需要审批流）\n"
        "   示例: \"把所有北京用户的等级改成 VIP\" \"删除无效订单\"\n\n"
        "4. chart_interaction —— 用户想更换图表展示方式、切换图表类型、调整可视化，或者是在已有查询结果之上进行图表操作\n"
        "   示例: \"换一种图表\" \"用饼图展示\" \"改成折线图\" \"换个可视化方式\"\n"
        "   **重要**: 如果用户上一轮已经查询了数据，当前只是想要换个图表展示，应归类为 chart_interaction\n\n"
        "5. other_questions —— 其他类型的问题\n"
        "   示例: \"长沙今天天气怎么样\"\n\n"
        "严格要求：\n"
        "1. 只返回一个 JSON 对象，不要包含任何其他文字\n"
        "2. JSON 格式为: {\"intent\": \"<类型>\", \"confidence\": <0.0~1.0>}\n"
        "3. 不要使用 markdown 代码块包裹 JSON"
    )

    # 构建包含历史上下文的用户消息
    user_message = f"请分析以下用户意图：\n\n{user_question}"
    if history:
        history_text = "\n".join(
            [f"[{_get_msg_role(m)}]: {_get_msg_content(m)[:200]}" for m in history[-6:]]  # 最近6轮
        )
        user_message = (
            f"## 对话历史（最近几轮）\n{history_text}\n\n"
            f"## 当前用户问题（请结合上述历史上下文判断意图）\n{user_question}"
        )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            stream=True,
        )
        ctx = get_stream_context()
        content_chunks = []
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                content_chunks.append(token)
                # 不推送到 stream_queue：analyze_intent 输出的是内部 JSON
        content = "".join(content_chunks).strip()

        # 尝试从 markdown 代码块中提取 JSON
        if content.startswith("```"):
            content = _extract_json_from_markdown(content)
        log.info(content)
        result = json.loads(content)

        # 校验返回字段的合法性
        valid_intents = {"query_data", "ask_help", "write_data", "chart_interaction", "other_questions"}
        intent = result.get("intent", "query_data")
        confidence = float(result.get("confidence", 0.5))

        if intent not in valid_intents:
            intent = "query_data"  # 非法值兜底

        # 将 confidence 钳制在 0.0 ~ 1.0 范围
        confidence = max(0.0, min(1.0, confidence))

        return {"intent": intent, "confidence": confidence}

    except (json.JSONDecodeError, Exception):
        # LLM 返回解析失败，默认按查询数据处理
        return {"intent": "query_data", "confidence": 0.5}


def _extract_json_from_markdown(text: str) -> str:
    """
    从 markdown 代码块中提取 JSON 内容。

    参数:
        text: 可能包含 markdown 标记的文本

    返回:
        提取后的纯 JSON 字符串
    """
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _get_msg_role(m) -> str:
    """从消息对象（dict 或 LangChain Message）中提取角色。"""
    if isinstance(m, dict):
        return m.get("role", "unknown")
    return getattr(m, "type", "unknown")


def _get_msg_content(m) -> str:
    """从消息对象（dict 或 LangChain Message）中提取内容。"""
    if isinstance(m, dict):
        return m.get("content", "")
    return getattr(m, "content", "")


def route_by_intent(intent_result: dict) -> str:
    """
    根据意图分析结果，返回下一步应调用的 Agent 节点名称。

    路由规则：
    - query_data         → schema_agent（查数据，走 Schema → SQL → 执行链路）
    - ask_help           → rag_agent（咨询类问题，走 RAG 知识库检索）
    - write_data         → schema_agent（写入数据，也走 Schema → SQL → Security 链路）
    - chart_interaction  → schema_agent（图表追问，重新查询后生成新图表）
    - other_questions    → misc_agent（其他类型，回答用户，不是本Agent专业领域，无法回答）
    - 未知意图           → schema_agent（默认尝试走查询链路）

    参数:
        intent_result: analyze_intent() 的返回结果，
                       包含 "intent" 和 "confidence" 字段

    返回:
        下游 Agent 节点名称字符串
    """
    intent = intent_result.get("intent", "query_data")

    # 路由映射表
    route_map = {
        "query_data": "schema_agent",
        "ask_help": "rag_agent",
        "write_data": "schema_agent",  # 也走 Schema → SQL → Security 链路
        "chart_interaction": "schema_agent",  # 图表追问也走查询链路（重新查数据+换图表）
        "other_questions": "misc_agent",
    }

    return route_map.get(intent, "schema_agent")


async def clarify_and_plan(
    user_question: str, history: list[dict] | None = None, cached_result: list | None = None
) -> dict:
    """
    合并 Clarifier + Planner：单次 LLM 调用同时完成意图澄清和执行计划生成。

    相比旧的 clarify_intent → generate_plan 两次调用，节省一次 LLM 往返（~2-3s）。

    返回:
        {
            "is_clear": bool,
            "clarification": str,
            "options": list[str],
            "intent": str,
            "confidence": float,
            "plan_steps": list[dict],
            "chart_suitable": bool,
            "reasoning": str,
        }
    """
    client = get_llm()

    system_prompt = (
        "你是一个智能数据任务协调专家。请同时完成两项任务：\n"
        "1. 分析用户意图的明确程度（是否需要追问）\n"
        "2. 为明确的意图生成结构化的执行计划\n\n"
        "## 意图模糊度判断标准\n"
        "- 高模糊：问题范围太宽泛，缺少关键信息。如\"帮我分析一下\"\n"
        "- 中模糊：主题明确但缺少维度/时间/指标。如\"分析销售趋势\"\n"
        "- 低模糊（明确）：包含具体的表名、时间范围、指标等。如\"查询a_sheet1表上个月销售额TOP10\"\n"
        "- 闲聊/通用问题：问候、能力询问、天气等。如\"你好\"\"你能做什么\"\n"
        "- 图表追问：如果用户仅输入图表类型名称（如\"折线图\"\"饼图\"），"
        "  或要求更换图表展示（如\"换一种图表\"），且对话历史中已有数据查询结果，"
        "  则is_clear必须为true，意图归类为chart_interaction\n\n"
        "## 意图分类\n"
        "1. query_data — 数据查询/统计\n"
        "2. ask_help — 帮助咨询（走知识库检索）\n"
        "3. write_data — 数据写入/修改（需要审批）\n"
        "4. chart_interaction — 图表操作（换图表类型等）\n"
        "5. other_questions — 其他问题\n\n"
        "## chart_suitable 判断\n"
        "- 用户明确问排行/趋势/占比/对比 → true\n"
        "- 用户问列表/详情/具体值 → false\n"
        "- 数据查询类默认 true（可被 analyst 覆盖）\n\n"
        "## 执行步骤命名规范（agent 字段）\n"
        "- load_schema (agent: schema)\n"
        "- generate_sql (agent: sql_coder)\n"
        "- security_check (agent: security)\n"
        "- execute_query (agent: execute)\n"
        "- analyze_data (agent: analyst)\n"
        "- generate_chart (agent: reporter)\n"
        "- rag_retrieval (agent: rag)\n"
        "- answer_text (agent: misc)\n\n"
        "严格要求：\n"
        "1. 只返回一个 JSON 对象，不要包含任何其他文字或 markdown 标记\n"
        "2. JSON 格式:\n"
        "{\n"
        '  "is_clear": true/false,\n'
        '  "clarification": "追问文本（不明确时填写）",\n'
        '  "options": ["选项1", "选项2"],\n'
        '  "intent": "query_data|ask_help|write_data|chart_interaction|other_questions",\n'
        '  "confidence": 0.0~1.0,\n'
        '  "plan_steps": [{"step": "步骤名", "agent": "agent名", "priority": 1}],\n'
        '  "chart_suitable": true/false,\n'
        '  "reasoning": "简短推理说明"\n'
        "}\n"
        "3. 如果意图明确，clarification 和 options 留空\n"
        "4. 如果意图不明确，options 提供 2-4 个具体可点击的选项"
    )

    user_message = f"请分析以下用户问题：\n\n{user_question}"
    if history:
        history_text = "\n".join(
            [f"[{_get_msg_role(m)}]: {_get_msg_content(m)[:200]}" for m in history[-6:]]
        )
        user_message = (
            f"## 对话历史\n{history_text}\n\n## 当前问题\n{user_question}"
        )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.0,
            stream=True,
        )
        ctx = get_stream_context()
        content_chunks = []
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                content_chunks.append(token)
        content = "".join(content_chunks).strip()

        if content.startswith("```"):
            content = _extract_json_from_markdown(content)

        result = json.loads(content)

        valid_intents = {"query_data", "ask_help", "write_data", "chart_interaction", "other_questions"}
        intent = result.get("intent", "query_data")
        if intent not in valid_intents:
            intent = "query_data"

        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.5))))

        return {
            "is_clear": result.get("is_clear", True),
            "clarification": result.get("clarification", ""),
            "options": result.get("options", []),
            "intent": intent,
            "confidence": confidence,
            "plan_steps": result.get("plan_steps", []),
            "chart_suitable": result.get("chart_suitable", intent == "query_data"),
            "reasoning": result.get("reasoning", ""),
        }
    except (json.JSONDecodeError, Exception):
        return {
            "is_clear": True,
            "clarification": "",
            "options": [],
            "intent": "query_data",
            "confidence": 0.5,
            "plan_steps": [
                {"step": "load_schema", "agent": "schema", "priority": 1},
                {"step": "generate_sql", "agent": "sql_coder", "priority": 2},
                {"step": "security_check", "agent": "security", "priority": 3},
                {"step": "execute_query", "agent": "execute", "priority": 4},
                {"step": "analyze_data", "agent": "analyst", "priority": 5},
                {"step": "generate_chart", "agent": "reporter", "priority": 6},
            ],
            "chart_suitable": True,
            "reasoning": "默认查询计划（LLM 解析失败兜底）",
        }


def route_planner(state: dict) -> str:
    """
    Planner 路由 —— 根据生成的执行计划决定第一个下游节点。

    路由规则（Phase E.3）：
    - query_data / write_data → schema_agent
    - chart_interaction → chart_direct（有缓存数据时跳过 SQL 链路，直接复用上轮查询结果）
    - ask_help → rag_agent
    - other_questions → misc_agent

    chart_interaction 智能路由：
        当意图为 chart_interaction 且已有缓存数据时，走 chart_direct 快捷路径，
        跳过 schema → sql → security → execute 全链路，直接进入 analyst → reporter；
        若无缓存数据则回退到 schema_agent（走完整 SQL 查询链路）

    参数:
        state: AgentState（含 intent、_cached_query_result 字段）

    返回:
        下游节点名称
    """
    intent = state.get("intent", "query_data")

    # chart_interaction 智能路由：有缓存数据走 chart_direct 快捷路径
    if intent == "chart_interaction":
        cached = state.get("_cached_query_result", [])
        if cached:
            return "chart_direct"
        # 无缓存数据：不走完整 SQL 链路（仅图表类型名无法生成有意义 SQL），
        # 改为走 misc_agent 提示用户先查询数据
        return "misc_agent"

    route_map = {
        "query_data": "schema_agent",
        "ask_help": "rag_agent",
        "write_data": "schema_agent",
        "other_questions": "misc_agent",
    }
    return route_map.get(intent, "schema_agent")
