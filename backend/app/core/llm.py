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
import json
from openai import AsyncOpenAI
from langchain.chat_models import init_chat_model
from app.core.config import settings


# ── reasoning_content 兼容补丁(2026-10-18)────────────────────────
# 背景:Qwen/DeepSeek 等的流式增量把思考内容放在非标准字段
# `delta.reasoning_content`;langchain-openai 1.x 明确「不提取」
# (chat_models/base.py 注释:reasoning_content are **not** extracted),
# 导致 harness 的 messages 流永远拿不到思考内容、前端无实时思考。
# 做法:包装其模块级 `_convert_delta_to_message_chunk`,把该字段补回
# additional_kwargs(流式)与 _convert_dict_to_message(非流式,尽力),
# sse_bridge 已有 additional_kwargs["reasoning_content"] 的读取逻辑。
def _patch_reasoning_content() -> None:
    try:
        from langchain_openai.chat_models import base as _oa_base
    except Exception:  # noqa: BLE001 —— 包结构变化时静默跳过,不影响主流程
        return

    origin_delta = getattr(_oa_base, "_convert_delta_to_message_chunk", None)
    if origin_delta is not None and not getattr(origin_delta, "_reasoning_patched", False):

        def _delta_with_reasoning(_dict, default_class):  # noqa: ANN001
            chunk = origin_delta(_dict, default_class)
            try:
                rc = _dict.get("reasoning_content") if hasattr(_dict, "get") else None
                if rc:
                    chunk.additional_kwargs["reasoning_content"] = rc
            except Exception:  # noqa: BLE001 —— 补丁绝不阻断流式
                pass
            return chunk

        _delta_with_reasoning._reasoning_patched = True  # type: ignore[attr-defined]
        _oa_base._convert_delta_to_message_chunk = _delta_with_reasoning

    origin_msg = getattr(_oa_base, "_convert_dict_to_message", None)
    if origin_msg is not None and not getattr(origin_msg, "_reasoning_patched", False):

        def _message_with_reasoning(_dict):  # noqa: ANN001
            msg = origin_msg(_dict)
            try:
                rc = _dict.get("reasoning_content") if hasattr(_dict, "get") else None
                if rc:
                    msg.additional_kwargs["reasoning_content"] = rc
            except Exception:  # noqa: BLE001
                pass
            return msg

        _message_with_reasoning._reasoning_patched = True  # type: ignore[attr-defined]
        _oa_base._convert_dict_to_message = _message_with_reasoning


_patch_reasoning_content()


# ── 当前 LLM provider 上下文（按请求/任务隔离）──
_current_provider: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "current_llm_provider", default=None
)

# ── 思考模式上下文（按请求隔离；默认 True 保持既有行为）──
# 前端「思考模式」开关经 chat_completions 入口设置；模型构建处读取并尽力
# 注入 enable_thinking=False（仅对声明支持思考的 provider / Qwen 家族模型，
# 避免不支持的网关 400）。关闭时后端同时停止推送思考展示。
_thinking_enabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "llm_thinking_enabled", default=True
)


def set_thinking_mode(enabled: bool) -> None:
    """设置当前请求是否开启模型思考（在聊天流开始时调用，与 set_provider 同款）。"""
    _thinking_enabled.set(bool(enabled))


def get_thinking_mode() -> bool:
    """当前请求的思考模式开关；默认 True（未设置时保持模型既有行为）。"""
    return _thinking_enabled.get()


def _thinking_capable(provider: dict | None) -> bool:
    """provider/模型是否可经 enable_thinking 控制思考。

    判定：provider 显式声明 thinking_mode / capabilities.thinking，
    或模型名为 Qwen 家族（DashScope OpenAI 兼容模式文档参数）。
    其余（GLM/OpenRouter 等）不注入，避免未知参数导致网关 400。
    """
    if provider:
        if provider.get("thinking_mode"):
            return True
        caps = provider.get("capabilities") or {}
        if isinstance(caps, dict) and caps.get("thinking"):
            return True
    model = (get_model_name(provider) or "").lower()
    return "qwen" in model


def thinking_model_kwargs(provider: dict | None = None) -> dict:
    """按当前思考开关 + provider 配置解析模型注入参数。

    - 思考强度(provider.params.reasoning_effort 非空时注入 reasoning_effort)
      来源:配置中心 / 模型选择器的「思考强度」(2026-10-18)
    - 开关打开：不干预 enable_thinking（模型默认行为）
    - 开关关闭且模型可控制：enable_thinking=False
    - 开关关闭但模型不可控制：不注入（退化为仅前端隐藏思考展示）
    """
    provider = provider or _current_provider.get()
    # ⚠️ 必须走 extra_body 而非 model_kwargs:
    # openai SDK 的 AsyncCompletions.create() 不接受 enable_thinking 这类
    # 非标准关键字,放 model_kwargs 会抛「unexpected keyword argument」;
    # extra_body 才是透传到请求 JSON 顶层(DashScope 兼容模式认这个)。
    extra: dict = {}

    # 思考强度:管理员/用户在界面显式设置过才下发(避免不支持该参数的网关 400)
    effort = ((provider or {}).get("params") or {}).get("reasoning_effort") or ""
    if effort:
        extra["reasoning_effort"] = effort

    if not get_thinking_mode() and _thinking_capable(provider):
        extra["enable_thinking"] = False

    return {"extra_body": extra} if extra else {}


# ── legacy 路径的用量回调 ─────────────────────────────────────
# legacy 图的 LLM 调用发生在各 agent 内部，graph 流里看不到 usage；
# 模型实例挂上本回调后，on_llm_end 把 token_usage 回灌到请求级计量器
# （usage_metrics.set_request_usage_meter 注册；harness/deepagent 不注册，
# 其 usage 从 astream 的 usage_metadata 直读，回调对其 no-op，避免双计）。
class _RequestUsageCallback:
    """LangChain 回调：on_llm_end → 请求级 UsageMeter.observe_usage。"""

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: ANN001,ANN003
        from app.core.usage_metrics import get_request_usage_meter

        meter = get_request_usage_meter()
        if meter is None:
            return
        llm_output = getattr(response, "llm_output", None) or {}
        usage = llm_output.get("token_usage") if isinstance(llm_output, dict) else None
        if not isinstance(usage, dict):
            return
        details = usage.get("prompt_token_details")
        cached = 0
        if isinstance(details, dict):
            cached = int(details.get("cached_tokens") or 0)
        meter.observe_usage(
            usage.get("prompt_tokens") or 0,
            usage.get("completion_tokens") or 0,
            cached,
        )


_usage_callback = _RequestUsageCallback()


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
    """解析 API Key 和 Base URL。

    优先使用 provider 配置(按其 key_mode/dotenv 解析);provider 缺失时才回退
    全局 settings。**provider 存在但 key 解析不到时返回空 key**——不用其它厂商的
    key 兜底,避免把错误 key 发往目标 API(401 Missing Authentication header)。
    """
    key = settings.LLM_API_KEY
    base = settings.LLM_BASE_URL
    if provider:
        from app.core.config_manager import get_config_manager
        mgr = get_config_manager()
        resolved = mgr.resolve_api_key(provider)
        key = resolved or ""
        base = provider.get("api_base") or base
    return key, base


# ── 客户端实例缓存 ────────────────────────────────────────────
# AsyncOpenAI 内部持有 httpx.AsyncClient，官方设计即跨请求复用（协程安全）；
# 缓存命中可免去每次 LLM 调用重付 TCP+TLS 握手。
# 注意：contextvars provider 路由逻辑（set_provider/_current_provider）不受影响，
# 缓存 key 仅决定实例复用，路由仍按每次调用的上下文 provider 解析。
_openai_clients: dict[tuple[str, str], AsyncOpenAI] = {}
_langchain_models: dict[tuple[str, str, str], object] = {}


def get_llm(provider: dict | None = None) -> AsyncOpenAI:
    """
    获取配置好的 AsyncOpenAI 客户端实例（按 api_key + base_url 缓存复用）。

    自动从全局配置中读取 API Key、Base URL 等参数；
    相同 (api_key, base_url) 的请求复用同一实例，避免重复 TLS 握手。

    provider: 可选，显式传入；不传则使用上下文 provider（set_provider）。
    """
    provider = provider or _current_provider.get()
    key, base = _resolve_key_and_base(provider)
    cache_key = (key, base)
    client = _openai_clients.get(cache_key)
    if client is None:
        client = AsyncOpenAI(api_key=key, base_url=base)
        _openai_clients[cache_key] = client
    return client


def get_langchain_llm(provider: dict | None = None):
    """
    获取配置好的 LangChain chat model 实例（按 model + api_key + base_url + 思考参数缓存复用）。

    provider: 可选，显式传入；不传则使用上下文 provider（set_provider）。
    """
    provider = provider or _current_provider.get()
    key, base = _resolve_key_and_base(provider)
    model_name = get_model_name()
    # 思考开关参与缓存 key：开关状态不同必须复用不同实例（model_kwargs 构建期固化）
    thinking_kwargs = thinking_model_kwargs(provider)
    cache_key = (model_name, key, base, json.dumps(thinking_kwargs, sort_keys=True))
    cached = _langchain_models.get(cache_key)
    if cached is None:
        cached = init_chat_model(
            model=model_name,
            model_provider='openai',
            temperature=1.0,
            api_key=key,
            base_url=base,
            # usage 统计：让末块带 usage_metadata（读数条 Token 用量弹窗数据源）
            stream_usage=True,
            # legacy 路径用量回灌（on_llm_end → 请求级计量器）
            callbacks=[_usage_callback],
            **thinking_kwargs,
        )
        _langchain_models[cache_key] = cached
    return cached
