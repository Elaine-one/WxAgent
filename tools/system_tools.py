import locale
import os
import subprocess
import sys

from tools.base import ToolDef
from tools.registry import ToolRegistry


def _sys_encoding() -> str:
    if sys.platform == "win32":
        try:
            return locale.getdefaultlocale()[1] or "gbk"
        except Exception:
            pass
    return "utf-8"


def _run_shell(command: str, state=None, user_id: str = "") -> str:
    forbidden = ["rm -rf", "del /f", "format", "shutdown", "restart",
                 "DROP", "DELETE", "TRUNCATE", "> /dev/", "mkfs"]
    cmd_lower = command.lower()
    for kw in forbidden:
        if kw.lower() in cmd_lower:
            return f"已拒绝执行危险命令（匹配关键词: {kw}）。仅支持只读操作。"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            encoding=_sys_encoding(), errors="replace",
            timeout=30, cwd=os.path.expanduser("~"),
        )
        out = result.stdout.strip() or result.stderr.strip()
        if len(out) > 3000:
            out = out[:3000] + "\n...(输出已截断)"
        return out or "命令执行完毕，无输出"
    except subprocess.TimeoutExpired:
        return "命令执行超时（30秒）"
    except Exception as e:
        return f"执行失败: {e}"


ToolRegistry.register(
    ToolDef(
        name="run_shell",
        description="执行系统命令并返回输出。用于获取系统信息、运行脚本等只读操作。"
                    "禁止执行删除、格式化等破坏性命令。",
        parameters={
            "command": {"type": "string", "description": "要执行的 shell 命令，如 systeminfo 或 dir C:\\"},
        },
        required=["command"],
    ),
    _run_shell,
)
