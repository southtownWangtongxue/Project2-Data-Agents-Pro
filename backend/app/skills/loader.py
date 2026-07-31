"""
Skill Loader — 扫描 skills/ 目录，解析 SKILL.md 文件

遵循 Anthropic Agent Skills 规范：
1. 扫描 skills/ 下每个子目录
2. 读取 SKILL.md 的 YAML frontmatter 提取 name / description
3. 读取正文 Markdown 作为指令内容
4. 可选：发现同目录下的 Python 脚本作为执行器
"""
import importlib.util
import os
import re
from pathlib import Path
from typing import Any

import yaml

from app.utils.log_utils import log

# Skill 目录相对于本文件的路径
_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 SKILL.md 的 YAML frontmatter 和正文。

    返回:
        (metadata_dict, body_markdown)
    """
    # 匹配 --- ... --- 包裹的 YAML 块
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}, content

    yaml_text = match.group(1)
    body = content[match.end():]

    try:
        metadata = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        log.warning(f"[SkillLoader] YAML 解析失败: {exc}")
        metadata = {}

    return metadata, body


def _import_script(script_path: Path, function_name: str) -> Any | None:
    """动态导入 Python 脚本中的指定函数。"""
    try:
        spec = importlib.util.spec_from_file_location(
            script_path.stem, str(script_path)
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, function_name, None)
    except Exception as exc:
        log.warning(f"[SkillLoader] 导入脚本失败 {script_path}: {exc}")
        return None


class SkillLoader:
    """扫描并加载 Anthropic 规范的 Skill 文件夹。"""

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or _SKILLS_DIR
        self._loaded: list[dict] = []

    # 执行器函数名映射：skill name → (script_path_relative, function_name)
    _EXECUTOR_MAP = {
        "wechat-notify": ("wechat-notify/notify.py", "send_wechat_notification"),
        "scheduled-report": ("scheduled-report/report.py", "create_scheduled_report"),
        "external-api": ("external-api/api_client.py", "call_external_api"),
        "summarizer": ("summarizer/summarize.py", "summarize_text"),
        "translator": ("translator/translate.py", "translate_text"),
    }

    def scan(self) -> list[dict]:
        """扫描 skills/ 目录，返回所有已加载的 Skill 字典列表。

        每个 Skill 字典结构:
            {
                "name": "wechat-notify",
                "description": "...",
                "instructions": "# 企业微信通知\n...",
                "folder": "/path/to/wechat-notify",
                "executor": <callable> | None,
                "enabled": True,
            }
        """
        self._loaded = []

        if not self.skills_dir.exists():
            log.warning(f"[SkillLoader] Skills 目录不存在: {self.skills_dir}")
            return self._loaded

        for entry in sorted(self.skills_dir.iterdir()):
            if not entry.is_dir():
                continue

            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                log.warning(f"[SkillLoader] 目录 {entry.name} 缺少 SKILL.md，跳过")
                continue

            try:
                raw = skill_md.read_text(encoding="utf-8")
            except Exception as exc:
                log.warning(f"[SkillLoader] 读取 {skill_md} 失败: {exc}")
                continue

            metadata, instructions = _parse_frontmatter(raw)

            name = metadata.get("name", entry.name)
            description = metadata.get("description", "")

            if not name:
                log.warning(f"[SkillLoader] {skill_md} 缺少 name 字段，跳过")
                continue

            # 查找执行器
            executor = None
            exec_info = self._EXECUTOR_MAP.get(name)
            if exec_info:
                script_rel, func_name = exec_info
                script_path = self.skills_dir / script_rel
                if script_path.exists():
                    executor = _import_script(script_path, func_name)

            skill_entry = {
                "name": name,
                "description": description,
                "instructions": instructions.strip(),
                "folder": str(entry),
                "executor": executor,
                "enabled": True,
            }

            self._loaded.append(skill_entry)
            log.info(f"[SkillLoader] 已加载 Skill: {name} ({description[:60]})")

        log.info(f"[SkillLoader] 扫描完成，共加载 {len(self._loaded)} 个 Skill")
        return self._loaded

    def get_loaded(self) -> list[dict]:
        """获取已加载的 Skill 列表（需先调用 scan()）。"""
        return self._loaded

    def build_instructions_text(self) -> str:
        """将所有 Skill 的指令拼接为单个文本，用于注入 system prompt。"""
        parts = []
        for skill in self._loaded:
            parts.append(f"## {skill['name']}\n{skill['instructions']}")
        return "\n\n".join(parts)
