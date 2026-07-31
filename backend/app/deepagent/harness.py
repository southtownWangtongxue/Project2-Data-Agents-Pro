"""
DeepAgent Harness — 工厂函数，创建顶层 DeepAgent 实例

整合三个核心 Middleware:
- TodoListMiddleware:    复杂任务自动拆解与跟踪
- FilesystemMiddleware:  中间结果持久化 / 长期记忆
- SubAgentMiddleware:     动态子 Agent 创建与委派

集成 Anthropic Skills: Skill 指令注入 system_prompt，执行脚本作为工具挂载
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.llm import get_current_provider, get_model_name, _resolve_key_and_base
from app.core.config_manager import get_config_manager
from app.skills.loader import SkillLoader
from app.skills.registry import skill_registry
from app.utils.log_utils import log
from langchain.chat_models import init_chat_model
from app.deepagent.tools import get_fixed_tools


async def create_skill_tools() -> tuple[list[Any], str]:
    """
    初始化 Skills 系统，返回工具列表和指令文本。

    返回:
        (tools_list, instructions_text)
        - tools_list: 可供 DeepAgent 使用的工具函数列表
        - instructions_text: 拼接后的 SKILL.md 指令文本（注入 system_prompt）
    """
    # 初始化 Skills（如果尚未初始化）
    if skill_registry.count == 0:
        loader = SkillLoader()
        skills = loader.scan()
        skill_registry.register_all(skills)

    # 同步 skills.json 中的 enabled 状态（使 UI 启用/禁用真正生效）
    mgr = get_config_manager()
    enabled_map = {s["id"]: s.get("enabled", True) for s in mgr.skills}
    for name, entry in skill_registry._skills.items():
        entry["enabled"] = enabled_map.get(name, entry.get("enabled", True))

    # 仅提取「已启用」技能的执行器作为工具
    tools = []
    for skill in skill_registry.list_all(enabled_only=True):
        executor = skill_registry.get_executor(skill["name"])
        if executor is not None:
            tools.append(executor)

    # 拼接「已启用」技能的 SKILL.md 指令（注入 system_prompt）
    parts = []
    for skill in skill_registry.list_all(enabled_only=True):
        instructions_text = skill.get("instructions", "")
        if instructions_text:
            parts.append(f"## {skill['name']}\n{instructions_text}")
    instructions = "\n\n".join(parts)

    log.info(
        "[DeepAgent] Skills 工具加载完成: %d 个工具, %d 个 Skill",
        len(tools),
        skill_registry.count,
    )
    return tools, instructions


def _build_model():
    """
    构建 DeepAgent 实际使用的 ChatModel 实例。

    关键修复：显式注入当前 provider 的 api_key / base_url，避免 DeepAgent 底层
    langchain `init_chat_model("openai:...")` 回退读取 OPENAI_API_KEY / OPENAI_BASE_URL
    环境变量——而 .env 中这两个变量指向 DashScope（sk-8250... / 默认 api.openai.com），
    会导致 task 模式调用智谱 glm-4.5-air 时 Connection error。
    同时禁用 Responses API（智谱 BigModel 不兼容），改用 Chat Completions。
    """
    model_name = get_model_name()
    provider = get_current_provider()
    # 复用与 legacy 模式一致的解析逻辑：provider 为空（如未指定 model 且无默认
    # provider 时 get_llm_config(None) 返回 None）时回退到全局 settings，
    # 避免 task 模式（DeepAgent 分支）在此处崩 AttributeError 中断 SSE 流。
    key, base = _resolve_key_and_base(provider)
    return init_chat_model(
        model=model_name,
        model_provider="openai",
        temperature=1.0,
        api_key=key,
        base_url=base,
        use_responses_api=False,
    )


def create_deep_agent(
    subagents: list[Any] | None = None,
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
    **kwargs: Any,
):
    """
    创建顶层 DeepAgent 实例。

    参数:
        subagents: 预编译的子 Agent 列表（CompiledSubAgent 或 dict）
        tools: 额外的工具函数列表
        system_prompt: 自定义系统提示词
        **kwargs: 传递给 deepagents.create_deep_agent 的其他参数

    返回:
        DeepAgent 实例
    """
    try:
        from deepagents import create_deep_agent as _create
    except ImportError as exc:
        raise ImportError(
            "deepagents 库未安装，请执行: pip install deepagents>=0.5.0"
        ) from exc

    model = _build_model()
    subagents = subagents or []
    tools = tools or []

    agent_kwargs: dict[str, Any] = {
        "model": model,
        "tools": tools,
        "subagents": subagents,
    }
    if system_prompt:
        agent_kwargs["system_prompt"] = system_prompt

    agent_kwargs.update(kwargs)

    _model_id = getattr(model, "model_name", None) or getattr(model, "model", None) or "unknown"
    log.info(
        "[DeepAgent] 创建 Agent: model=%s, tools=%d, subagents=%d",
        _model_id,
        len(tools),
        len(subagents),
    )

    return _create(**agent_kwargs)
