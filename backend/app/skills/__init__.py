"""
Skills 系统 — 包入口

遵循 Anthropic Agent Skills 规范:
- 每个 Skill 是一个独立文件夹，包含 SKILL.md 和可选脚本/资源
- SKILL.md 由 YAML frontmatter (name, description) + Markdown 指令正文组成
- 通过 loader.py 扫描发现，registry.py 管理注册与匹配
"""
from app.skills.loader import SkillLoader
from app.skills.registry import SkillRegistry

__all__ = ["SkillLoader", "SkillRegistry"]
