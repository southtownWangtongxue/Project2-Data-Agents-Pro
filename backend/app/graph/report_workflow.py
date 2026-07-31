"""
研究报告模式：RAG 检索知识库 → LLM 结构化报告生成。

阶段 7（本期）: 纯 RAG — 基于知识库文档检索 + LLM 报告生成
阶段 9（升级）: RAG + 数据混合 — 支持 report_type=hybrid

工作流:
    START → report_planner → report_writer → finish → END
"""
from langgraph.graph import StateGraph, START, END
from app.graph.state import AgentState
from app.graph.mode_router import register_mode
from app.graph.workflow import _push_node_started, finish_node
from app.utils.log_utils import log
from app.core.llm import get_llm
from app.core.config import settings
from app.core.llm import get_model_name
from app.core.stream import get_stream_context


async def report_planner_node(state: AgentState) -> dict:
    """研究报告规划节点：意图澄清 + 计划生成"""
    await _push_node_started("report_planner")
    user_question = state.get("user_question", "")
    history = state.get("messages", [])

    if not user_question.strip():
        return {"is_clear": False, "clarification_text": "请输入您的研究主题", "stage": "report_planned"}

    log.info(f"[ReportPlanner] 分析研究主题: {user_question[:80]}")

    client = get_llm()
    try:
        history_text = "\n".join(
            [f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:200]}" for m in (history or [])[-6:]]
        ) if history else "（无历史）"

        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[{
                "role": "system",
                "content": (
                    "你是一个研究规划专家。根据用户的研究主题，判断意图是否清晰。\n"
                    "返回 JSON: {\"is_clear\": true/false, \"clarification\": \"追问文本\", "
                    "\"options\": [\"选项1\",\"选项2\"], \"reasoning\": \"推理\"}\n"
                    "如果用户提供了具体的研究主题、行业或文档范围，is_clear 为 true。"
                ),
            }, {
                "role": "user",
                "content": f"## 对话历史\n{history_text}\n\n## 当前主题\n{user_question}",
            }],
            temperature=0.0,
            max_tokens=300,
        )
        content = response.choices[0].message.content.strip()
        import json
        result = json.loads(content)
        return {
            "is_clear": result.get("is_clear", True),
            "clarification_text": result.get("clarification", ""),
            "clarification_options": result.get("options", []),
            "intent": "report",
            "stage": "report_planned",
        }
    except Exception:
        return {"is_clear": True, "intent": "report", "stage": "report_planned"}


async def report_writer_node(state: AgentState) -> dict:
    """研究报告生成节点：RAG 检索 + LLM 流式输出报告"""
    await _push_node_started("report_writer")
    user_question = state.get("user_question", "")
    enable_web_search = state.get("enable_web_search", False)

    log.info(f"[ReportWriter] 生成研究报告: {user_question[:80]}, web_search={enable_web_search}")

    # RAG 检索知识库
    rag_context = ""
    try:
        from app.rag.retriever import search_similar
        results = await search_similar(user_question, top_k=3)
        if results:
            rag_context = "\n\n参考文档片段:\n" + "\n---\n".join(
                r.get("text", r.get("content", ""))[:500] for r in results
            )
            log.info(f"[ReportWriter] RAG 检索到 {len(results)} 条相关内容")
    except Exception as e:
        log.warning(f"[ReportWriter] RAG 检索跳过: {e}")

    client = get_llm()
    ctx = get_stream_context()

    system_prompt = (
        "你是一个专业的研究报告撰写专家。"
        "根据用户提供的研究主题和参考资料，生成一份结构清晰、论据充分的研究报告。\n\n"
        "报告格式要求:\n"
        "- 使用 Markdown 格式排版\n"
        "- ### 标题层级组织章节\n"
        "- **粗体** 强调关键数据\n"
        "- - 列表组织要点\n"
        "- > 引用块突出重要观点\n\n"
        "如果用户未提供具体细节，请根据知识库检索结果和相关领域知识进行合理补充。"
    )
    if enable_web_search:
        system_prompt += "\n你已启用联网搜索能力，可以引用最新的互联网信息。"

    response = await client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请撰写一份关于以下主题的研究报告:\n\n{user_question}{rag_context}"},
        ],
        temperature=0.5,
        max_tokens=3000,
        stream=True,
    )

    # 流式输出
    content_chunks = []
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            content_chunks.append(token)
            if ctx.queue:
                await ctx.push_token(token)

    analysis_text = "".join(content_chunks).strip()
    return {"analysis_text": analysis_text, "stage": "report_done"}


@register_mode("report")
def get_report_workflow() -> StateGraph:
    """编译并返回研究报告模式 StateGraph"""
    from app.graph.state import AgentState
    builder = StateGraph(AgentState)
    builder.add_node("report_planner", report_planner_node)
    builder.add_node("report_writer", report_writer_node)
    builder.add_node("finish", finish_node)
    builder.set_entry_point("report_planner")
    builder.add_edge("report_planner", "report_writer")
    builder.add_edge("report_writer", "finish")
    builder.add_edge("finish", END)
    return builder
