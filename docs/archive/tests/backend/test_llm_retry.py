"""LLM 瞬时错误分类与重试策略(TDD)。

背景:OpenRouter 免费档模型(nvidia/...:free)在容量紧张时返回间歇性
403 AllocationQuota.FreeTierOnly / 429 rate_limit_exceeded / 5xx。
实测同一请求 8 次中失败 1 次——属瞬时可用性问题而非配置错误,
必须重试(与 WorkBuddy 表现一致),否则每次都要用户重发。

策略:
- classify_llm_error: 区分「瞬时可重试」与「确定性失败」
- next_retry_delay: 指数退避 + 上限
- is_retryable_exception: 供调用层直接使用
"""
from app.core.llm_retry import (
    MAX_RETRIES,
    classify_llm_error,
    is_retryable_exception,
    next_retry_delay,
)


def test_free_tier_quota_error_is_retryable():
    """OpenRouter 免费档间歇性拒绝:瞬时,应重试。"""
    err = Exception(
        "Error code: 403 - {'error': {'code': 'AllocationQuota.FreeTierOnly',"
        " 'message': 'Free quota exhausted... disable the use free tier only mode'}}"
    )
    assert classify_llm_error(err) == "retryable"


def test_rate_limit_is_retryable():
    err = Exception("Error code: 429 - rate limit exceeded")
    assert classify_llm_error(err) == "retryable"


def test_server_error_is_retryable():
    err = Exception("Error code: 502 - Bad Gateway")
    assert classify_llm_error(err) == "retryable"


def test_auth_error_is_permanent():
    """401/403 无 key、非法 key:确定性失败,重试无意义。"""
    err = Exception("Error code: 401 - {'error': {'message': 'No auth credentials found'}}")
    assert classify_llm_error(err) == "permanent"


def test_bad_request_is_permanent():
    err = Exception("Error code: 400 - invalid request")
    assert classify_llm_error(err) == "permanent"


def test_unknown_error_defaults_to_permanent():
    """未知错误不盲目重试(避免放大真实缺陷)。"""
    assert classify_llm_error(Exception("boom")) == "permanent"


def test_backoff_grows_and_caps():
    d1 = next_retry_delay(1)
    d2 = next_retry_delay(2)
    d3 = next_retry_delay(3)
    assert d1 < d2 < d3, "退避应递增"
    assert next_retry_delay(10) <= 8.0, "退避应有上限,避免久等"


def test_is_retryable_exception_matches_classification():
    transient = Exception("Error code: 503 - service unavailable")
    assert is_retryable_exception(transient) is True
    assert is_retryable_exception(Exception("Error code: 404 - not found")) is False


def test_max_retries_is_bounded():
    assert 1 <= MAX_RETRIES <= 5