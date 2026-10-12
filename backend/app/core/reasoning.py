"""
reasoning.py —— 思考增量提取(全 Agent 复用)

不同提供方的推理字段命名不统一,统一在此兼容:
- Qwen / DashScope(openai 兼容模式):``delta.additional_kwargs["reasoning_content"]``
  或 ``delta.reasoning_content`` 属性
- OpenRouter / Nemotron 等:``delta.reasoning``(openai SDK 以 extra 字段暴露)
- LangChain AIMessageChunk:``chunk.additional_kwargs`` 中的同名字段

非思考模型返回空串,调用方据此静默跳过——不做假流式。
"""


def extract_reasoning(chunk) -> str:
    """从流式 chunk 中提取推理增量文本(无则返回空串)。"""
    # LangChain chunk:直接看 additional_kwargs
    add_kwargs = getattr(chunk, "additional_kwargs", None) or {}
    reasoning = add_kwargs.get("reasoning_content") or add_kwargs.get("reasoning") or ""
    if reasoning:
        return str(reasoning)

    choices = getattr(chunk, "choices", None)
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return ""

    # Qwen/DashScope:属性形式
    reasoning = getattr(delta, "reasoning_content", "") or ""
    if reasoning:
        return str(reasoning)

    # OpenRouter:SDK extra 字段(detail/为空时兜底 model_extra)
    reasoning = getattr(delta, "reasoning", "") or ""
    if reasoning:
        return str(reasoning)

    model_extra = getattr(delta, "model_extra", None) or {}
    reasoning = model_extra.get("reasoning") or model_extra.get("reasoning_content") or ""
    return str(reasoning) if reasoning else ""