"""
文档智读模式：用户上传文档 → 向量化存储 → RAG 问答。

阶段 7（本期）: 基础文档问答 — 对已上传文档进行 RAG 检索 + LLM 问答
阶段 9（升级）: 完整知识库管理 — 前端上传 + 后端向量化流水线

工作流:
    START → doc_planner → doc_qa → finish → END
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


async def doc_planner_node(state: AgentState) -> dict:
    """文档智读规划节点：分析用户问题"""
    await _push_node_started("doc_planner")
    user_question = state.get("user_question", "")

    if not user_question.strip():
        return {"is_clear": False, "clarification_text": "请输入您想了解的问题", "stage": "doc_planned"}

    log.info(f"[DocPlanner] 分析文档问题: {user_question[:80]}")
    return {"is_clear": True, "intent": "doc", "stage": "doc_planned"}


async def doc_qa_node(state: AgentState) -> dict:
    """文档问答节点：RAG 检索 + LLM 流式回答"""
    await _push_node_started("doc_qa")
    user_question = state.get("user_question", "")
    enable_web_search = state.get("enable_web_search", False)

    log.info(f"[DocQA] 文档问答: {user_question[:80]}, web_search={enable_web_search}")

    # RAG 检索知识库
    rag_context = ""
    try:
        from app.rag.retriever import search_similar
        results = await search_similar(user_question, top_k=3)
        if results:
            rag_context = "\n\n参考文档:\n" + "\n---\n".join(
                r.get("text", r.get("content", ""))[:500] for r in results
            )
    except Exception:
        pass

    client = get_llm()
    ctx = get_stream_context()

    system_prompt = (
        "你是一个专业的文档分析助手。"
        "根据知识库中的文档内容和用户问题，提供准确、清晰的回答。\n\n"
        "要求:\n"
        "- 使用 Markdown 格式排版\n"
        "- 引用文档中的关键信息时请注明出处\n"
        "- 如果文档中无法找到相关信息，请明确告知用户\n"
    )
    if enable_web_search:
        system_prompt += "\n你已启用联网搜索能力，可以引用最新的互联网信息作为补充。"

    response = await client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请根据文档内容回答以下问题:\n\n{user_question}{rag_context}"},
        ],
        temperature=0.3,
        max_tokens=2000,
        stream=True,
    )

    content_chunks = []
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            content_chunks.append(token)
            if ctx.queue:
                await ctx.push_token(token)

    analysis_text = "".join(content_chunks).strip()
    return {"analysis_text": analysis_text, "stage": "doc_done"}


@register_mode("doc")
def get_doc_workflow() -> StateGraph:
    """编译并返回文档智读模式 StateGraph"""
    from app.graph.state import AgentState
    builder = StateGraph(AgentState)
    builder.add_node("doc_planner", doc_planner_node)
    builder.add_node("doc_qa", doc_qa_node)
    builder.add_node("finish", finish_node)
    builder.set_entry_point("doc_planner")
    builder.add_edge("doc_planner", "doc_qa")
    builder.add_edge("doc_qa", "finish")
    builder.add_edge("finish", END)
    return builder
