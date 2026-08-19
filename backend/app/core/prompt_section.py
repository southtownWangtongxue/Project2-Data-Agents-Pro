"""
Prompt Section —— 系统提示词分层组装（Phase 2）

借鉴 DeepSeek Harness 的 system-prompt 包设计，将单一字符串系统提示词
重构为可插拔、可排序、可遮蔽的分层结构：

- PromptSection：结构化提示词段落（name / order / text / complete / scope）
- order 排序约定：-100=harness 身份、0=部署角色/persona、100-199=工具使用指引
- 作用域遮蔽：作用域同名段落遮蔽全局段落
- complete 段落：整体替换整个提示词
- {{var}} 变量插值：assemble 阶段插值

与 dsh 的对应关系（见 docs/reference/deepseek-harness-integration-analysis.md）：
  - PromptSection {name, order, text, complete} ≈ 同名 dataclass
  - system-prompt/assemble waterfall ≈ PromptAssembler.assemble()
  - variable(name, provider) + renderPrompt ≈ {{var}} 插值
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 变量插值语法：{{ var_name }}
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def prompt_section_enabled() -> bool:
    """读取 feature flag：是否启用分层提示词组装（默认关闭，保持旧行为）。"""
    return get_settings().PROMPT_SECTION_ENABLED


@dataclass
class PromptSection:
    """结构化提示词段落。

    属性:
        name: 段落名（用于作用域遮蔽去重）
        order: 排序权重，约定 -100=harness 身份、0=角色/persona、100-199=工具指引
        text: 段落文本（支持 {{var}} 占位符）
        complete: 若为 True，则该段落整体替换整个提示词
        scope: 作用域标识（None 表示全局段落），同名段落的 scope 段遮蔽全局段
    """
    name: str
    order: int
    text: str
    complete: bool = False
    scope: str | None = None


def _interpolate(text: str, variables: dict[str, str] | None) -> str:
    """对文本中的 {{var}} 占位符做变量插值。

    未在 variables 中提供的变量保留原样（不静默置空），便于审计。
    """
    if not variables:
        return text

    def repl(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        logger.warning("[prompt-section] 未提供变量 %s，保留占位符", key)
        return match.group(0)

    return _VAR_RE.sub(repl, text)


class PromptAssembler:
    """系统提示词组装器 —— 收集 PromptSection 并组装为最终提示词字符串。

    组装流程（对齐 dsh 的 assemble waterfall）：
      1. 过滤作用域（scope 匹配 + 全局段落）
      2. 同名遮蔽（scope 段遮蔽全局段）
      3. 按 order 升序排序（同 order 保持添加顺序）
      4. 若存在 complete 段落，则整体替换
      5. {{var}} 变量插值
    """

    def __init__(self) -> None:
        self._sections: list[PromptSection] = []

    def add(
        self,
        name: str,
        order: int,
        text: str,
        complete: bool = False,
        scope: str | None = None,
    ) -> "PromptAssembler":
        """添加一个段落（链式调用）。"""
        self._sections.append(
            PromptSection(name=name, order=order, text=text, complete=complete, scope=scope)
        )
        return self

    def add_section(self, section: PromptSection) -> "PromptAssembler":
        """添加一个 PromptSection 实例。"""
        self._sections.append(section)
        return self

    def _resolve_scope(self, scope: str | None) -> list[PromptSection]:
        """按作用域过滤 + 同名遮蔽。

        规则：
        - 保留 scope 为 None（全局）或等于目标 scope 的段落；
        - 若同名段落同时存在全局段与 scope 段，则 scope 段遮蔽全局段。
        """
        by_name: dict[str, PromptSection] = {}
        for section in self._sections:
            if section.scope is not None and section.scope != scope:
                continue  # 非目标作用域，跳过
            existing = by_name.get(section.name)
            if existing is None:
                by_name[section.name] = section
            else:
                # 遮蔽规则：scope 段遮蔽全局段；同为全局/同 scope 时后添加者遮蔽
                existing_is_scoped = existing.scope is not None
                new_is_scoped = section.scope is not None
                if new_is_scoped or not existing_is_scoped:
                    by_name[section.name] = section
        return list(by_name.values())

    def assemble(self, scope: str | None = None, variables: dict[str, str] | None = None) -> str:
        """组装为最终提示词字符串。"""
        resolved = self._resolve_scope(scope)

        # complete 段落整体替换
        complete_sections = [s for s in resolved if s.complete]
        if complete_sections:
            # 多个 complete 段落时取 order 最大的（最后添加的优先）
            chosen = max(complete_sections, key=lambda s: s.order)
            return _interpolate(chosen.text, variables)

        # 按 order 排序（稳定排序保持同 order 的添加顺序）
        ordered = sorted(resolved, key=lambda s: s.order)
        return "\n\n".join(_interpolate(s.text, variables) for s in ordered)
