"""
通用任务模式：基于 deepagents 的通用 Agent 调度。

阶段 10 完整实现：
  - 三层记忆：短期(Redis) + 长期(Milvus) + 工作记忆(对话上下文)
  - 动态工具集：从 ConfigManager 获取启用的 Skill + MCP Tools
  - LLM 动态绑定：从 ConfigManager 获取模式默认模型
  - 流式输出：逐 token 推送前端

工作流:
    START → task_agent → finish → END
"""
from langgraph.graph import StateGraph, START, END
from app.graph.state import AgentState
from app.graph.mode_router import register_mode
from app.graph.workflow import _push_node_started, finish_node
from app.utils.log_utils import log
from app.core.llm import get_llm
from app.core.config import settings
from app.core.llm import get_model_name
from app.core.config_manager import get_config_manager
from app.core.stream import get_stream_context


async def task_agent_node(state: AgentState) -> dict:
    """通用任务 Agent：集成三层记忆 + 动态工具 + 流式输出"""
    await _push_node_started("task_agent")
    user_question = state.get("user_question", "")
    messages = state.get("messages", [])
    enable_web_search = state.get("enable_web_search", False)

    log.info(f"[TaskAgent] 执行通用任务: {user_question[:80]}, web_search={enable_web_search}")

    # 1. 三层记忆
    from app.core.memory_layer import get_memory
    memory = get_memory()
    short_mem = await memory.short_get("user", 5)
    long_mem = await memory.long_search("user", user_question, top_k=3)
    working_mem = memory.working_context(messages)

    # 2. 动态工具集
    cfg = get_config_manager()
    llm_config = cfg.get_llm_config()
    enabled_skills = cfg.get_enabled_skills("task")
    skill_names = [s["name"] for s in enabled_skills]
    log.info(f"[TaskAgent] 加载 {len(enabled_skills)} 个 Skill: {skill_names}")

    # 构建增强提示词
    memory_context = ""
    if short_mem:
        memory_context += "\n短期记忆:\n" + "\n".join(
            f"- [{m['role']}]: {m['content'][:100]}" for m in short_mem
        )
    if long_mem:
        memory_context += "\n长期记忆 (知识库):\n" + "\n".join(
            f"- {m[:200]}" for m in long_mem
        )
    if working_mem:
        memory_context += f"\n当前对话上下文:\n{working_mem}"

    # 3. LLM 动态绑定 + 流式输出
    client = get_llm()
    ctx = get_stream_context()

    system_prompt = (
        "你是一个通用的 AI 任务助手，拥有三层记忆系统和动态工具集。\n\n"
        f"可用技能: {', '.join(skill_names)}.\n"
        f"联网搜索: {'已启用' if enable_web_search else '未启用'}.\n"
        + (f"模型: {llm_config['name']} ({llm_config['model']})\n" if llm_config else "")
        + "\n请根据用户需求和上下文记忆，完成用户的任务。"
    )

    response = await client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{memory_context}\n\n用户任务: {user_question}"},
        ],
        temperature=0.5,
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

    # 保存短期记忆
    await memory.short_add("user", "user", user_question)
    await memory.short_add("user", "assistant", analysis_text[:500])

    return {"analysis_text": analysis_text, "stage": "task_done"}


@register_mode("task")
def get_task_workflow() -> StateGraph:
    """编译并返回通用任务模式 StateGraph"""
    builder = StateGraph(AgentState)
    builder.add_node("task_agent", task_agent_node)
    builder.add_node("finish", finish_node)
    builder.set_entry_point("task_agent")
    builder.add_edge("task_agent", "finish")
    builder.add_edge("finish", END)
    return builder
