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
from app.skills.loader import SkillLoader
from app.skills.registry import skill_registry
from app.utils.log_utils import log


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

    # 提取所有可用的执行器作为工具
    tools = []
    for skill in skill_registry.list_all(enabled_only=True):
        executor = skill_registry.get_executor(skill["name"])
        if executor is not None:
            tools.append(executor)

    # 拼接所有 SKILL.md 指令
    instructions = loader.build_instructions_text()

    log.info(
        "[DeepAgent] Skills 工具加载完成: %d 个工具, %d 个 Skill",
        len(tools),
        skill_registry.count,
    )
    return tools, instructions


def _build_model_string() -> str:
    """将配置中的模型名转换为 DeepAgent 所需的 provider:model 格式。"""
    model = settings.LLM_MODEL_NAME
    # 如果已经是 provider:model 格式，直接返回
    if ":" in model:
        return model
    # 否则按 OpenAI 格式
    return f"openai:{model}"


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

    model = _build_model_string()
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

    log.info(
        "[DeepAgent] 创建 Agent: model=%s, tools=%d, subagents=%d",
        model,
        len(tools),
        len(subagents),
    )

    return _create(**agent_kwargs)
