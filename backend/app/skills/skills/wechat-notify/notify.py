"""
企业微信通知 Skill — 实际执行脚本
通过 Webhook 发送消息到企业微信群
"""
import asyncio
import os

import httpx


async def send_wechat_notification(
    content: str,
    webhook_url: str | None = None,
    msg_type: str = "markdown",
) -> dict:
    """
    发送企业微信机器人消息。

    参数:
        content: 消息内容
        webhook_url: Webhook 地址，不传则读取环境变量 WECHAT_WEBHOOK_URL
        msg_type: 消息类型，text 或 markdown，默认 markdown

    返回:
        {"status": "success", "message": "...", "msg_id": "..."}
        或 {"status": "error", "message": "..."}
    """
    webhook_url = webhook_url or os.getenv("WECHAT_WEBHOOK_URL")
    if not webhook_url:
        return {
            "status": "error",
            "message": "webhook_url 未配置，请设置环境变量 WECHAT_WEBHOOK_URL 或传入参数",
        }

    # markdown 消息长度限制处理
    max_len = 4096
    if msg_type == "markdown" and len(content) > max_len:
        content = content[: max_len - 8] + "...(已截断)"

    payload: dict = {
        "msgtype": msg_type,
    }
    if msg_type == "text":
        payload["text"] = {"content": content}
    else:
        payload["markdown"] = {"content": content}

    # 最多重试 2 次
    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("errcode") == 0:
                    return {
                        "status": "success",
                        "message": f"消息已发送 (重试 {attempt} 次)",
                        "msg_id": data.get("msgid", ""),
                    }
                else:
                    last_error = f"企业微信返回错误: {data.get('errmsg', 'unknown')}"
        except Exception as exc:
            last_error = str(exc)

        if attempt < 2:
            await asyncio.sleep(1)

    return {"status": "error", "message": f"发送失败 (已重试 2 次): {last_error}"}
