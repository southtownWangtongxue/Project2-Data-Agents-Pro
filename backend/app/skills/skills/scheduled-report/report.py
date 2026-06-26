"""
定时报表 Skill — 实际执行脚本
管理定时报表任务：创建、列表、启停
"""
from typing import Any


async def create_scheduled_report(
    name: str,
    sql: str,
    cron: str,
    channel: str = "wechat",
    recipients: list[str] | None = None,
) -> dict:
    """
    创建定时报表任务。

    参数:
        name: 任务名称
        sql: 要执行的 SQL 语句
        cron: cron 表达式
        channel: 推送渠道 (wechat / email)
        recipients: 推送目标列表

    返回:
        任务创建结果
    """
    # TODO: 持久化到数据库，对接 APScheduler / schedule 库
    # 当前为占位实现，后续迭代中完成数据库持久化和调度引擎集成
    return {
        "status": "success",
        "message": f"定时报表任务 '{name}' 已创建",
        "task": {
            "name": name,
            "sql": sql,
            "cron": cron,
            "channel": channel,
            "recipients": recipients or [],
            "enabled": True,
        },
        "note": "定时报表调度引擎将在后续迭代中集成 APScheduler",
    }


async def list_scheduled_reports() -> dict:
    """列出所有定时报表任务"""
    # TODO: 从数据库查询
    return {
        "status": "success",
        "tasks": [],
        "note": "定时报表调度引擎将在后续迭代中集成",
    }


async def toggle_report(task_name: str, enabled: bool) -> dict:
    """启停指定定时报表任务"""
    return {
        "status": "success",
        "message": f"任务 '{task_name}' 已{'启用' if enabled else '停用'}",
        "task": {"name": task_name, "enabled": enabled},
    }
