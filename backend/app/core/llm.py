"""
LLM 客户端模块 —— 提供 OpenAI 兼容的 LLM 调用接口
使用 openai SDK 兼容 Qwen/GLM 等模型（通过自定义 base_url）

V2.1: 支持「上下文 provider」动态路由
- 对话请求可在入口处通过 set_provider() 设置当前 provider
- 所有 agent 调用 get_llm() 时自动使用上下文中的 provider 的
  api_key / api_base / model，实现「界面切换模型 → 实际 API 路由一致」
- 未设置 provider 时回退到全局 settings（兼容定时任务等非对话场景）
"""
import contextvars
from openai import AsyncOpenAI
from langchain.chat_models import init_chat_model
from app.core.config import settings


# ── 当前 LLM provider 上下文（按请求/任务隔离）──
_current_provider: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "current_llm_provider", default=None
)


def set_provider(provider: dict | None) -> None:
    """设置当前请求的 LLM provider（在聊天流开始时调用）"""
    _current_provider.set(provider)


def get_current_provider() -> dict | None:
    """获取当前上下文中的 provider（调试/透传用）"""
    return _current_provider.get()


def get_model_name(provider: dict | None = None) -> str:
    """当前生效的 model 名。

    优先级：显式传入的 provider > 上下文 provider > 全局 settings。
    这样 agent 在显式传入 provider（前端模型列表）时绝不会回退到 .env 的 settings。
    """
    p = provider or _current_provider.get()
    if p and p.get("model"):
        return p["model"]
    return settings.LLM_MODEL_NAME


def describe_route() -> str:
    """
    返回当前实际 LLM 路由摘要，用于日志/排障。

    显示：provider id（界面所选）、实际发往 API 的 model、
    base_url、api_key 前缀。可快速判断「界面模型 → 实际调用」是否一致，
    以及是否因 provider id 匹配不到而静默回退到全局默认模型。
    """
    p = _current_provider.get()
    model = get_model_name()
    key, base = _resolve_key_and_base(p)
    pid = (p or {}).get("id")
    masked = f"{key[:6]}…" if key else "none"
    return f"provider_id={pid!r}, model={model!r}, base_url={base!r}, api_key={masked}"


def _resolve_key_and_base(provider: dict | None = None) -> tuple[str, str]:
    """解析 API Key 和 Base URL：优先使用 provider 配置，否则回退 settings"""
    key = settings.LLM_API_KEY
    base = settings.LLM_BASE_URL
    if provider:
        from app.core.config_manager import get_config_manager
        mgr = get_config_manager()
        key = mgr.resolve_api_key(provider) or key
        base = provider.get("api_base") or base
    return key, base


def get_llm(provider: dict | None = None) -> AsyncOpenAI:
    """
    获取配置好的 AsyncOpenAI 客户端实例。

    自动从全局配置中读取 API Key、Base URL 等参数，
    每次调用创建新实例以保证线程安全。

    provider: 可选，显式传入；不传则使用上下文 provider（set_provider）。
    """
    provider = provider or _current_provider.get()
    key, base = _resolve_key_and_base(provider)
    return AsyncOpenAI(api_key=key, base_url=base)


def get_langchain_llm(provider: dict | None = None):
    """
    获取配置好的 LangChain chat model 实例。

    provider: 可选，显式传入；不传则使用上下文 provider（set_provider）。
    """
    provider = provider or _current_provider.get()
    key, base = _resolve_key_and_base(provider)
    return init_chat_model(
        model=get_model_name(),
        model_provider='openai',
        temperature=1.0,
        api_key=key,
        base_url=base,
    )
