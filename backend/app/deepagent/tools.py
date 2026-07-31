"""
DeepAgent 固定工具集。

包含不通过 Skill 机制动态加载、直接注册到 DeepAgent 的固定工具，
如百度联网搜索。
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from app.utils.log_utils import log


# ── 百度联网搜索 ──────────────────────────────────────────────

_BAIDU_SEARCH_URL = os.getenv(
    "BAIDU_WEB_SEARCH_URL",
    "https://qianfan.baidubce.com/v2/ai_search/web_search",
)
_BAIDU_API_KEY = os.getenv("BAIDU_API_KEY", "")


def _do_baidu_search(keyword: str) -> str:
    """同步执行百度搜索（在线程池中运行）。"""
    json_data = {
        "messages": [{"content": keyword, "role": "user"}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": 3}],
    }
    response = httpx.post(
        _BAIDU_SEARCH_URL,
        json=json_data,
        headers={
            "Authorization": f"Bearer {_BAIDU_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()
    references = data.get("references")
    if references:
        return "\n\n".join(ref.get("content", "") for ref in references)
    return "没有搜索到任何结果"


async def web_search_tool(keyword: str) -> str:
    """百度联网搜索工具——获取实时公开信息。

    使用百度搜索 API 检索互联网上的公开网页信息，适合需要最新数据的问题：
    天气预报、新闻、股价、最新资讯等。

    Args:
        keyword: 搜索关键词（建议用自然语言短语，如"长沙今天天气"）

    Returns:
        str: 搜索结果摘要文本
    """
    log.info("[WebSearch] 百度搜索: %s", keyword[:100])
    try:
        return await asyncio.to_thread(_do_baidu_search, keyword)
    except httpx.HTTPStatusError as exc:
        log.warning("[WebSearch] HTTP %d: %s", exc.response.status_code, exc)
        return f"搜索请求失败（HTTP {exc.response.status_code}），请稍后重试。"
    except Exception as exc:
        log.warning("[WebSearch] 搜索异常: %s", exc)
        return f"搜索服务暂时不可用: {exc}"


# ── 固定工具注册 ──────────────────────────────────────────────

_FIXED_TOOLS: list[Any] = []


def get_fixed_tools() -> list[Any]:
    """返回 DeepAgent 固定工具列表（可追加）。"""
    # 延迟注册，确保只在模块导入后执行一次
    if not _FIXED_TOOLS:
        _FIXED_TOOLS.append(web_search_tool)
        log.info("[DeepAgent] 固定工具注册: web_search_tool (百度)")
    return _FIXED_TOOLS
