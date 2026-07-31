"""
定时任务 API — NL2Cron + APScheduler 管理
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.api.v1.auth import get_current_user
from app.utils.log_utils import log

router = APIRouter(prefix="/schedule", tags=["schedule"])

# 简单的内存任务存储（后续可迁移到 MySQL）
_tasks: list[dict] = []


class ScheduleTask(BaseModel):
    id: str = ""
    name: str
    prompt: str
    cron: str = ""  # 空则由 LLM 生成
    mode: str = "task"
    enabled: bool = True


@router.get("/list")
async def list_tasks(user=Depends(get_current_user)):
    user_tasks = [t for t in _tasks if t.get("user") == user["user_name"]]
    return {"tasks": user_tasks}


@router.post("/create")
async def create_task(task: ScheduleTask, user=Depends(get_current_user)):
    import uuid
    task_id = task.id or str(uuid.uuid4())[:8]

    # NL2Cron: 如果未提供 cron，用 LLM 生成
    cron = task.cron
    if not cron:
        try:
            from app.core.llm import get_llm, get_model_name
            from app.core.config import settings
            client = get_llm()
            resp = await client.chat.completions.create(
                model=get_model_name(),
                messages=[{
                    "role": "system",
                    "content": "将自然语言时间描述转为标准 cron 表达式（5 段）。只输出 cron 表达式，不要其他内容。示例：每天早上9点 → 0 9 * * *"
                }, {
                    "role": "user", "content": task.prompt
                }],
                temperature=0.0, max_tokens=50,
            )
            cron = resp.choices[0].message.content.strip()
            if len(cron.split()) != 5:
                cron = "0 9 * * *"  # 兜底
        except Exception:
            cron = "0 9 * * *"

    entry = {
        "id": task_id, "name": task.name, "prompt": task.prompt,
        "cron": cron, "mode": task.mode, "enabled": task.enabled,
        "user": user["user_name"],
    }
    _tasks.append(entry)
    log.info(f"[Schedule] 创建定时任务: {task.name}, cron={cron}")

    # 尝试注册到 APScheduler
    try:
        scheduler = _get_scheduler()
        scheduler.add_job(
            _execute_task, "cron",
            id=task_id,
            minute=cron.split()[0], hour=cron.split()[1],
            day=cron.split()[2], month=cron.split()[3], day_of_week=cron.split()[4],
            args=[entry],
            replace_existing=True,
        )
        log.info(f"[Schedule] APScheduler 已注册: {task_id}")
    except ImportError:
        log.info("[Schedule] APScheduler 未安装，定时任务仅记录不执行")

    return {"ok": True, "id": task_id, "cron": cron}


@router.delete("/{task_id}")
async def delete_task(task_id: str, user=Depends(get_current_user)):
    global _tasks
    _tasks = [t for t in _tasks if not (t.get("id") == task_id and t.get("user") == user["user_name"])]
    return {"ok": True}


@router.put("/{task_id}/toggle")
async def toggle_task(task_id: str, body: dict, user=Depends(get_current_user)):
    for t in _tasks:
        if t.get("id") == task_id and t.get("user") == user["user_name"]:
            t["enabled"] = body.get("enabled", not t["enabled"])
            return {"ok": True}
    raise HTTPException(404)


# ── APScheduler ──

_scheduler = None


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        _scheduler = BackgroundScheduler()
        _scheduler.start()
    return _scheduler


async def _execute_task(task: dict):
    """定时任务执行器：通过 chat API 触发 Agent 执行"""
    log.info(f"[Schedule] 执行定时任务: {task['name']}")
