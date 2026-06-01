import hashlib
import logging

import httpx

from tasks.scheduler import create_scheduler
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TOOL_META = ToolMeta(
    name="monitor",
    type=ToolType.BUILTIN,
    description="监控工具集：定时任务、URL监控",
    version="1.0.0",
    tags=["monitor", "schedule", "timer"],
)

_scheduler = None


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = create_scheduler()
        if not _scheduler.running:
            _scheduler.start()
    return _scheduler


def _schedule_task(name: str, cron_expression: str, action_tool: str,
                   action_args: dict | None = None, state=None, user_id: str = "") -> ToolResult:
    if action_args is None:
        action_args = {}

    scheduler = _get_scheduler()
    job_id = f"{user_id}_{name}"
    scheduler.add_job(
        func=_execute_scheduled_action,
        trigger="cron",
        **_parse_cron(cron_expression),
        id=job_id,
        replace_existing=True,
        kwargs={"tool": action_tool, "args": action_args, "user_id": user_id},
    )
    return ToolResult(
        success=True,
        content=f"定时任务 '{name}' 已创建（{cron_expression}），将执行 {action_tool}",
        display=f"定时任务已设置: {cron_expression}",
    )


def _parse_cron(expression: str) -> dict:
    parts = expression.split()
    if len(parts) == 5:
        return {
            "minute": parts[0], "hour": parts[1],
            "day": parts[2], "month": parts[3], "day_of_week": parts[4],
        }
    return {"minute": "0", "hour": "9"}


def _execute_scheduled_action(tool: str, args: dict, user_id: str = ""):
    from tools.registry import ToolRegistry
    result = ToolRegistry.execute(tool, args, state=None, user_id=user_id)
    try:
        from channel.sender import send_message
        send_message(user_id, result.display or result.content[:500])
    except Exception as e:
        logger.warning("定时任务通知失败: %s", e)


def _monitor_url(url: str, interval_minutes: int = 360,
                 change_type: str = "content",
                 state=None, user_id: str = "") -> ToolResult:
    scheduler = _get_scheduler()
    job_id = f"monitor_{user_id}_{hashlib.md5(url.encode()).hexdigest()[:8]}"

    initial_hash = _fetch_url_hash(url)

    scheduler.add_job(
        func=_check_url_change,
        trigger="interval",
        minutes=interval_minutes,
        id=job_id,
        replace_existing=True,
        kwargs={
            "url": url, "user_id": user_id,
            "change_type": change_type,
            "baseline_hash": initial_hash,
        },
    )
    return ToolResult(
        success=True,
        content=f"已开始监控 {url}，每 {interval_minutes} 分钟检查一次。变化时通知你。",
        display=f"已开始监控，每 {interval_minutes}min 检查一次",
    )


def _fetch_url_hash(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        return hashlib.md5(resp.text.encode()).hexdigest()
    except Exception:
        return ""


def _check_url_change(url: str, user_id: str, change_type: str,
                      baseline_hash: str):
    current_hash = _fetch_url_hash(url)
    if current_hash and current_hash != baseline_hash:
        try:
            from channel.sender import send_message
            send_message(user_id, f"监控发现变化: {url}")
        except Exception as e:
            logger.warning("监控通知失败: %s", e)
        _monitor_url(url=url, user_id=user_id,
                     change_type=change_type, state=None)


ToolRegistry.register(
    ToolDef(
        name="schedule_task",
        description="创建通用定时任务。cron_expression 为标准5段cron表达式。到时自动执行指定工具并发送结果。",
        parameters={
            "name": {"type": "string", "description": "任务名称"},
            "cron_expression": {"type": "string", "description": "cron表达式，如 '0 9 * * *' 表示每天9点"},
            "action_tool": {"type": "string", "description": "到时执行的工具名"},
            "action_args": {"type": "object", "description": "工具参数"},
        },
        required=["name", "cron_expression", "action_tool"],
    ),
    _schedule_task,
)

ToolRegistry.register(
    ToolDef(
        name="monitor_url",
        description="监控 URL 变化。定时抓取，检测到变化时通知用户。",
        parameters={
            "url": {"type": "string", "description": "监控的 URL"},
            "interval_minutes": {"type": "integer", "description": "检查间隔(分钟)，默认360"},
            "change_type": {"type": "string", "description": "变化检测方式: content/status/hash"},
        },
        required=["url"],
    ),
    _monitor_url,
)
