"""
Skill Registry — 注册中心

管理已加载的 Skills，提供查询、匹配、启用/禁用能力。
支持与 DeepAgent 的工具系统对接。
"""
from __future__ import annotations

from typing import Any, Callable

from app.utils.log_utils import log


class SkillRegistry:
    """Skill 注册中心，管理所有已发现的 Skill。"""

    def __init__(self):
        self._skills: dict[str, dict] = {}

    def register(self, skill_entry: dict) -> None:
        """注册一个 Skill。

        参数:
            skill_entry: SkillLoader.scan() 返回的单个 Skill 字典
        """
        name = skill_entry["name"]
        self._skills[name] = skill_entry
        log.debug("[SkillRegistry] 注册 Skill: %s", name)

    def register_all(self, skills: list[dict]) -> None:
        """批量注册 Skills。"""
        for skill in skills:
            self.register(skill)

    def get(self, name: str) -> dict | None:
        """按名称获取 Skill。"""
        return self._skills.get(name)

    def list_all(self, enabled_only: bool = True) -> list[dict]:
        """列出所有 Skill。

        参数:
            enabled_only: 仅返回已启用的

        返回:
            Skill 字典列表，每项含 name/description/enabled
        """
        result = []
        for skill in self._skills.values():
            if enabled_only and not skill.get("enabled", True):
                continue
            result.append({
                "name": skill["name"],
                "description": skill["description"],
                "enabled": skill.get("enabled", True),
            })
        return result

    def match_by_description(self, query: str) -> list[dict]:
        """
        根据用户查询匹配相关 Skill。

        当前使用简单的关键词匹配，后续可升级为 LLM 语义匹配。

        参数:
            query: 用户查询文本

        返回:
            匹配的 Skill 列表，按相关度排序
        """
        query_lower = query.lower()
        results = []

        for skill in self._skills.values():
            if not skill.get("enabled", True):
                continue

            desc = skill["description"].lower()
            name = skill["name"].lower()

            # 简单关键词得分
            score = 0
            keywords = [name.replace("-", " ")] + desc.split()
            for kw in keywords:
                if kw in query_lower:
                    score += 1

            if score > 0:
                results.append((score, skill))

        results.sort(key=lambda x: x[0], reverse=True)
        return [skill for _, skill in results]

    def get_tool_specs(self) -> list[dict]:
        """生成可供 LLM function calling 使用的工具规格列表。"""
        specs = []
        for skill in self._skills.values():
            if not skill.get("enabled", True):
                continue
            specs.append({
                "type": "function",
                "function": {
                    "name": skill["name"],
                    "description": skill["description"],
                },
            })
        return specs

    def get_executor(self, name: str) -> Callable | None:
        """获取 Skill 的执行函数。"""
        skill = self._skills.get(name)
        if skill is None:
            return None
        return skill.get("executor")

    def enable(self, name: str) -> bool:
        """启用指定 Skill。"""
        skill = self._skills.get(name)
        if skill is None:
            return False
        skill["enabled"] = True
        return True

    def disable(self, name: str) -> bool:
        """禁用指定 Skill。"""
        skill = self._skills.get(name)
        if skill is None:
            return False
        skill["enabled"] = False
        return True

    @property
    def count(self) -> int:
        return len(self._skills)


# 全局单例
skill_registry = SkillRegistry()


async def init_skills() -> SkillRegistry:
    """应用启动时初始化 Skills 系统。"""
    from app.skills.loader import SkillLoader

    loader = SkillLoader()
    skills = loader.scan()
    skill_registry.register_all(skills)

    log.info("[SkillRegistry] Skills 初始化完成，共 %d 个", skill_registry.count)
    return skill_registry
