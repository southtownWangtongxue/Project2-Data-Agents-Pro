"""LLM 瞬时错误分类与重试策略。

背景:OpenRouter 免费档模型(如 nvidia/...:free)在容量紧张时返回间歇性
403 AllocationQuota.FreeTierOnly / 429 / 5xx。实测同一请求 8 次失败 1 次
——属瞬时可用性问题,必须重试(与 WorkBuddy 的表现一致),否则用户每次
都要手动重发。

分类原则:
- retryable  免费档拒绝 / 限流 / 网关与服务端错误 → 退避后重试
- permanent  鉴权失败(401/403 无凭据)、请求不合法(400/404)、
             以及无法识别的错误 → 直接失败,不放大真实缺陷
"""
from __future__ import annotations

import re

MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 8.0

# 确定性:鉴权与请求错误——重试无意义(先判,避免 403 免费档拒绝被误判)
_PERMANENT_PATTERNS = (
    re.compile(r"\b401\b"),
    re.compile(r"invalid[_ ]api[_ ]key|incorrect api key|no auth credentials", re.I),
    re.compile(r"\b400\b"),
    re.compile(r"\b404\b"),
    re.compile(r"\b422\b"),
    re.compile(r"model not found", re.I),
)

# 瞬时:免费档配额拒绝(OpenRouter)/ 限流 / 服务端与网关错误
_RETRYABLE_PATTERNS = (
    re.compile(r"AllocationQuota\.FreeTierOnly", re.I),
    re.compile(r"Free quota exhausted", re.I),
    re.compile(r"rate[_ -]?limit", re.I),
    re.compile(r"\b429\b"),
    re.compile(r"\b50[0234]\b"),
    re.compile(r"overloaded", re.I),
    re.compile(r"service unavailable", re.I),
    re.compile(r"bad gateway", re.I),
    re.compile(r"timeout|timed out", re.I),
    re.compile(r"connection reset|connection error", re.I),
)


def classify_llm_error(exc: BaseException | str) -> str:
    """把错误分类为 "retryable" / "permanent"。"""
    text = str(exc)
    # 鉴权/请求类优先:403 既可能是免费档拒绝(retryable)也可能是无凭据
    # (permanent),先判永久模式可避免把真鉴权失败当瞬时错误重试。
    for pat in _PERMANENT_PATTERNS:
        if pat.search(text):
            return "permanent"
    for pat in _RETRYABLE_PATTERNS:
        if pat.search(text):
            return "retryable"
    return "permanent"


def is_retryable_exception(exc: BaseException) -> bool:
    """调用层直接使用的判定。"""
    return classify_llm_error(exc) == "retryable"


def next_retry_delay(attempt: int) -> float:
    """指数退避(attempt 从 1 起),上限 MAX_DELAY_SECONDS。"""
    delay = BASE_DELAY_SECONDS * (2 ** max(0, attempt - 1))
    return min(delay, MAX_DELAY_SECONDS)