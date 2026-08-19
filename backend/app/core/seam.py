"""
Seam —— 能力接缝（Phase 3）

借鉴 DeepSeek Harness 的 capability seams 三角色设计：
  - Service Definition：声明一个可替换服务（seam），如 dsh 的 ctx.llm / ctx.storage / ctx.shell
  - Provider：该服务的多种实现，并列注册，运行时选一个后端
  - Consumer：通过 seam 获取当前选中后端，不关心具体实现

服务分类（对齐 dsh 的 core/seam/bundle）：
  - core：主干，不可替换
  - seam：可替换，组合时选后端（本阶段主要实现此类）
  - bundle：组合多个服务的复合能力

与 dsh 的对应关系（见 docs/reference/deepseek-harness-integration-analysis.md）：
  - Service Definition/Provider/Consumer 三角色 ≈ define()/register()/resolve()
  - 组合时选后端 ≈ select()
  - 可注入 replay 后端（测试）≈ register() 一个 fake provider 后 select()

本阶段落地两个 seam：
  - search：联网搜索后端（baidu_search 等）
  - storage：数据库存储后端（mysql / postgresql）

说明：LLM 客户端未落地为 seam——本项目 get_llm() 返回 AsyncOpenAI、
get_langchain_llm() 返回 LangChain model，二者类型不同、由不同调用方使用，
无统一 LLM 接口可抽象；且 provider 路由（api_key/base_url/model）由
contextvars 的 set_provider() 按请求切换，属「配置层路由」而非「实现层替换」，
与 seam 的「单例后端选择」语义冲突。留待后续引入统一 LLM 接口后再抽象。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def seam_enabled() -> bool:
    """读取 feature flag：是否启用能力接缝（默认关闭，保持旧行为）。"""
    return get_settings().SEAM_ENABLED


@dataclass
class ServiceDefinition:
    """服务定义（seam 声明）。"""
    key: str
    description: str = ""
    default: str | None = None  # 默认 provider 名
    kind: str = "seam"  # core / seam / bundle


@dataclass
class Provider:
    """服务的一个实现（provider）。工厂懒加载。

    cache=True：实例缓存（适合有状态后端，如 storage 引擎）；
    cache=False：每次 resolve 都调工厂返回新实例（适合随上下文变化的客户端，如 LLM）。
    """
    service: str
    name: str
    factory: Callable[[], Any]
    description: str = ""
    cache: bool = True
    _instance: Any = field(default=None, init=False, repr=False)


class SeamRegistry:
    """能力接缝注册表。

    管理所有服务的 provider 集合与当前选中后端，供 consumer 统一解析。
    线程安全要求不高（注册发生在启动期，选择/解析发生在运行期读多写少）。
    """

    def __init__(self) -> None:
        self._services: dict[str, ServiceDefinition] = {}
        self._providers: dict[str, dict[str, Provider]] = {}
        self._selected: dict[str, str] = {}

    # ── 服务定义 ──
    def define(
        self,
        key: str,
        description: str = "",
        default: str | None = None,
        kind: str = "seam",
    ) -> "SeamRegistry":
        """声明一个可替换服务。"""
        self._services[key] = ServiceDefinition(
            key=key, description=description, default=default, kind=kind
        )
        return self

    # ── Provider 注册 ──
    def register(
        self,
        service: str,
        name: str,
        factory: Callable[[], Any],
        description: str = "",
        cache: bool = True,
    ) -> "SeamRegistry":
        """注册服务的一个实现（provider）。

        cache：True 实例缓存（有状态后端）；False 每次 resolve 新建（随上下文变化的客户端）。
        """
        if service not in self._services:
            self.define(service)
        self._providers.setdefault(service, {})[name] = Provider(
            service=service, name=name, factory=factory, description=description, cache=cache
        )
        # 选中后端：default 已注册则优先选中 default（覆盖此前的自动选择）；
        # 否则若尚未选中，选中首个注册者。显式 select() 后不会再被 register 覆盖
        # （本项目 register 均发生在启动期，select 发生在运行期，无冲突）。
        default = self._services[service].default
        if default and default in self._providers[service]:
            self._selected[service] = default
        elif service not in self._selected:
            self._selected[service] = name
        return self

    def provider(self, service: str, name: str, description: str = ""):
        """装饰器形式注册 provider，返回原函数（不影响函数本身语义）。"""

        def decorator(factory: Callable[[], Any]):
            self.register(service, name, factory, description)
            return factory

        return decorator

    # ── 选择后端 ──
    def select(self, service: str, name: str) -> bool:
        """切换服务的当前后端。返回是否成功。"""
        if service in self._providers and name in self._providers[service]:
            old = self._selected.get(service)
            self._selected[service] = name
            # 切换后使旧实例失效，下次 resolve 重建
            if old and old in self._providers[service]:
                self._providers[service][old]._instance = None
            logger.info("[seam] %s: %s -> %s", service, old, name)
            return True
        logger.warning("[seam] 切换失败：服务 %s 无 provider %s", service, name)
        return False

    # ── Consumer 获取 ──
    def get(self, service: str) -> Provider | None:
        """返回服务当前选中的 provider（不实例化）。"""
        name = self._selected.get(service)
        if name is None:
            return None
        return self._providers.get(service, {}).get(name)

    def resolve(self, service: str) -> Any:
        """返回服务当前选中后端的实例。

        cache=True 的后端懒加载并缓存；cache=False 的后端每次返回新实例。
        """
        provider = self.get(service)
        if provider is None:
            raise KeyError(f"服务 {service!r} 未注册 provider 或未选中后端")
        if not provider.cache:
            return provider.factory()
        if provider._instance is None:
            provider._instance = provider.factory()
            logger.info("[seam] resolve %s/%s", service, provider.name)
        return provider._instance

    # ── 查询 ──
    def providers(self, service: str) -> list[str]:
        """列出服务的所有 provider 名。"""
        return list(self._providers.get(service, {}).keys())

    def selected(self, service: str) -> str | None:
        """返回服务当前选中后端名。"""
        return self._selected.get(service)


# 全局单例
_seam_registry: SeamRegistry | None = None


def get_seam() -> SeamRegistry:
    """返回全局能力接缝注册表单例。"""
    global _seam_registry
    if _seam_registry is None:
        _seam_registry = SeamRegistry()
    return _seam_registry
