"""
外部 API 调用 Skill — 实际执行脚本
通用 HTTP 客户端，支持 GET/POST/PUT/DELETE
"""
import os
import time
from urllib.parse import urlparse

import httpx

from app.utils.log_utils import log


async def call_external_api(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: dict | None = None,
    timeout: int = 30,
) -> dict:
    """
    调用外部 HTTP API。

    参数:
        url: 目标 URL
        method: HTTP 方法
        headers: 自定义请求头
        body: JSON 请求体
        timeout: 超时秒数

    返回:
        包含状态码、响应体和耗时的字典
    """
    # URL 白名单检查
    allowed_urls = os.getenv("ALLOWED_EXTERNAL_URLS", "")
    if allowed_urls:
        allowed_list = [u.strip() for u in allowed_urls.split(",") if u.strip()]
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not any(hostname.endswith(a) or hostname == a for a in allowed_list):
            return {
                "status": "error",
                "message": f"URL {hostname} 不在白名单中 (ALLOWED_EXTERNAL_URLS)",
            }

    headers = headers or {}
    # 移除敏感头用于日志
    safe_headers = {k: "***" if k.lower() in ("authorization", "x-api-key") else v
                    for k, v in headers.items()}

    start_time = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            if method.upper() == "GET":
                resp = await client.get(url, headers=headers)
            elif method.upper() == "POST":
                resp = await client.post(url, json=body, headers=headers)
            elif method.upper() == "PUT":
                resp = await client.put(url, json=body, headers=headers)
            elif method.upper() == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                return {"status": "error", "message": f"不支持的 HTTP 方法: {method}"}

            elapsed = round(time.monotonic() - start_time, 3)

            log.info(
                "[ExternalAPI] %s %s → %s (%ss)",
                method.upper(), url, resp.status_code, elapsed,
            )

            # 大响应体截断
            body_text = resp.text
            max_bytes = 500 * 1024
            if len(body_text) > max_bytes:
                body_text = body_text[:max_bytes] + f"...(已截断，原始大小 {len(resp.text)} 字节)"

            return {
                "status": "success",
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": body_text,
                "elapsed_seconds": elapsed,
            }
    except httpx.TimeoutException:
        log.error(f"[ExternalAPI] 请求超时: {method.upper()} {url} ({timeout}s)")
        return {"status": "error", "message": f"请求超时 (>{timeout}s): {url}"}
    except Exception as exc:
        log.error(f"[ExternalAPI] 请求异常: {method.upper()} {url} - {exc}")
        return {"status": "error", "message": f"请求失败: {str(exc)}"}
