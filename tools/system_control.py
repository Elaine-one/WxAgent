import logging
import subprocess

import yaml

from config import PROJECT_ROOT
from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _load_system_config() -> dict:
    try:
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("system_control", {})
    except Exception:
        return {}


def _list_processes(sort_by: str = "cpu", top_n: int = 5,
                    state=None, user_id: str = "") -> ToolResult:
    allowed_sort = {"cpu", "workingset", "name", "id"}
    sort_by = sort_by.lower() if sort_by.lower() in allowed_sort else "cpu"
    try:
        script = (
            f'Get-Process | Sort-Object -Property {sort_by} -Descending '
            f'| Select-Object -First {top_n} '
            f'| Format-Table Name,Id,CPU,WorkingSet -AutoSize'
        )
        r = subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True, text=True, timeout=10,
        )
        return ToolResult(
            success=True, content=r.stdout,
            display=f"Top {top_n} 进程（按 {sort_by}）",
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _check_port(port: int, state=None, user_id: str = "") -> ToolResult:
    try:
        r = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=10,
        )
        lines = [l for l in r.stdout.splitlines() if f":{port}" in l]
        if not lines:
            return ToolResult(success=True, content=f"端口 {port} 未被占用")
        return ToolResult(success=True, content=f"端口 {port} 占用:\n" + "\n".join(lines))
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _system_action(action: str, state=None, user_id: str = "") -> ToolResult:
    cfg = _load_system_config()
    actions = cfg.get("actions", {})
    act = actions.get(action)
    if not act:
        available = list(actions.keys())
        return ToolResult(success=False, error=f"未知操作: {action}，可用: {available}")

    risk = act.get("risk", "dangerous")
    if risk == "dangerous":
        return ToolResult(
            success=False,
            error=f"确认执行 {action}（{act.get('description', action)}）？",
            requires_confirmation=True,
            confirmation_detail={
                "type": "system_action",
                "action": action,
                "command": act["command"],
            },
        )

    return _execute_system_command(act)


def _execute_system_command(act: dict) -> ToolResult:
    cmd = act["command"]
    shell_type = act.get("shell", "cmd")
    try:
        if shell_type == "powershell":
            r = subprocess.run(
                ["powershell", "-Command", cmd],
                capture_output=True, text=True, timeout=10,
            )
        else:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=10,
            )
        return ToolResult(
            success=r.returncode == 0,
            content=act.get("description", cmd),
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _open_app(app_name: str, state=None, user_id: str = "") -> ToolResult:
    cfg = _load_system_config()
    whitelist = cfg.get("app_whitelist", {})
    cmd = whitelist.get(app_name.lower())
    if not cmd:
        available = list(whitelist.keys())
        return ToolResult(
            success=False,
            error=f"应用不在白名单中: {app_name}。可用: {available}",
        )
    try:
        subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return ToolResult(success=True, content=f"已启动: {app_name}")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _kill_process(pid: int, state=None, user_id: str = "") -> ToolResult:
    return ToolResult(
        success=False,
        error=f"确认终止进程 PID:{pid}？",
        requires_confirmation=True,
        confirmation_detail={"type": "kill_process", "pid": pid},
    )


ToolRegistry.register(
    ToolDef(
        name="list_processes",
        description="列出运行中的进程，按 cpu/workingset/name/id 排序。",
        parameters={
            "sort_by": {"type": "string", "description": "排序字段: cpu/workingset/name/id"},
            "top_n": {"type": "integer", "description": "返回数量，默认5"},
        },
    ),
    _list_processes,
)

ToolRegistry.register(
    ToolDef(
        name="check_port",
        description="检查指定端口是否被占用及占用进程。",
        parameters={"port": {"type": "integer", "description": "端口号"}},
        required=["port"],
    ),
    _check_port,
)

ToolRegistry.register(
    ToolDef(
        name="system_action",
        description="执行系统操作（sleep/lock/volume_up/volume_down/mute等）。操作定义在 config.yaml。危险操作需确认。",
        parameters={"action": {"type": "string", "description": "操作名称"}},
        required=["action"],
    ),
    _system_action,
)

ToolRegistry.register(
    ToolDef(
        name="open_app",
        description="打开应用程序。仅允许 config.yaml 白名单中的应用。",
        parameters={"app_name": {"type": "string", "description": "应用名称"}},
        required=["app_name"],
    ),
    _open_app,
)

ToolRegistry.register(
    ToolDef(
        name="kill_process",
        description="终止指定进程。需要用户确认。",
        parameters={"pid": {"type": "integer", "description": "进程 ID"}},
        required=["pid"],
    ),
    _kill_process,
)
