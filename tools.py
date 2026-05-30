"""
工具注册与执行 — 新增工具只需在这里添加 ToolDef + execute 分支
"""
import locale
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import ilink
import ilink_upload
from ilink import SessionState


def _sys_encoding() -> str:
    """获取系统默认编码（Windows 中文系统为 gbk）"""
    if sys.platform == "win32":
        try:
            return locale.getdefaultlocale()[1] or "gbk"
        except Exception:
            pass
    return "utf-8"


# ---------------------------------------------------------------------------
# 工具注册表 — 单一定义，自动转换为 OpenAI / Anthropic 格式
# ---------------------------------------------------------------------------

@dataclass
class ToolDef:
    """工具定义 — 新增工具只需加一个 ToolDef + execute_tool 加一个分支"""
    name: str
    description: str
    parameters: dict[str, Any]       # JSON Schema properties
    required: list[str] = field(default_factory=list)


# 所有可用工具的注册表
ALL_TOOLS: list[ToolDef] = [
    ToolDef(
        name="read_file",
        description="读取本地文件内容。用于查看文档、代码、日志等文本文件。",
        parameters={
            "path": {"type": "string", "description": "文件的绝对路径，如 C:\\Users\\xxx\\Desktop\\report.txt"},
        },
        required=["path"],
    ),
    ToolDef(
        name="list_directory",
        description="列出目录中的文件和子目录。用于浏览文件夹内容。",
        parameters={
            "path": {"type": "string", "description": "目录的绝对路径，如 C:\\Users\\xxx\\Desktop"},
        },
        required=["path"],
    ),
    ToolDef(
        name="search_files",
        description="按文件名搜索文件。支持通配符模糊匹配（如 *.pdf、report*）。",
        parameters={
            "pattern": {"type": "string", "description": "搜索模式，如 *.pdf 或 report*"},
            "directory": {"type": "string", "description": "搜索起始目录的绝对路径"},
        },
        required=["pattern", "directory"],
    ),
    ToolDef(
        name="send_file",
        description="向当前微信用户发送本地文件或图片。支持图片、文档、压缩包等。",
        parameters={
            "path": {"type": "string", "description": "要发送的文件的绝对路径"},
            "message": {"type": "string", "description": "附带文字说明（可选）"},
        },
        required=["path"],
    ),
    ToolDef(
        name="run_shell",
        description="执行系统命令并返回输出。用于获取系统信息、运行脚本等只读操作。"
                    "禁止执行删除、格式化等破坏性命令。",
        parameters={
            "command": {"type": "string", "description": "要执行的 shell 命令，如 systeminfo 或 dir C:\\"},
        },
        required=["command"],
    ),
]


def to_openai_schema(tools: list[ToolDef]) -> list[dict]:
    """转换为 OpenAI function calling 格式"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": t.parameters,
                    "required": t.required,
                },
            },
        }
        for t in tools
    ]


def to_anthropic_schema(tools: list[ToolDef]) -> list[dict]:
    """转换为 Anthropic tool use 格式"""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": {
                "type": "object",
                "properties": t.parameters,
                "required": t.required,
            },
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# 工具执行
# ---------------------------------------------------------------------------

# 工具执行上下文，由调用方注入
ToolContext = dict[str, Any]  # 可扩展，目前包含 state, to_user


def execute(name: str, args: dict[str, Any], state: SessionState, to_user: str) -> str:
    """执行工具调用，返回结果字符串"""

    if name == "read_file":
        return _read_file(args.get("path", ""))

    elif name == "list_directory":
        return _list_directory(args.get("path", ""))

    elif name == "search_files":
        return _search_files(
            args.get("pattern", "*"),
            args.get("directory", os.path.expanduser("~")),
        )

    elif name == "send_file":
        return _send_file(state, to_user, args.get("path", ""), args.get("message", ""))

    elif name == "run_shell":
        return _run_shell(args.get("command", ""))

    return f"未知工具: {name}"


# ---- 工具实现 ----

def _read_file(path: str) -> str:
    if not os.path.isfile(path):
        return f"错误：文件不存在 — {path}"
    try:
        size = os.path.getsize(path)
        if size > 100_000:
            return f"文件过大（{_format_size(size)}），只读取前 5000 字符...\n" + _read_text(path, 5000)
        return _read_text(path)
    except UnicodeDecodeError:
        return f"这是二进制文件（{_format_size(size)}），无法直接读取文本内容。如需发送，请用 send_file。"


def _list_directory(path: str) -> str:
    if not os.path.isdir(path):
        return f"错误：目录不存在 — {path}"
    try:
        items = os.listdir(path)
    except PermissionError:
        return f"错误：没有权限访问 {path}"
    if not items:
        return f"目录为空：{path}"
    lines = [f"📁 {path} ({len(items)} 项):"]
    for item in sorted(items):
        full = os.path.join(path, item)
        tag = "📁" if os.path.isdir(full) else "📄"
        size_str = ""
        if not os.path.isdir(full):
            size_str = f" ({_format_size(os.path.getsize(full))})"
        lines.append(f"  {tag} {item}{size_str}")
    return "\n".join(lines)


def _search_files(pattern: str, directory: str) -> str:
    if not os.path.isdir(directory):
        return f"错误：目录不存在 — {directory}"
    results = []
    try:
        regex = re.compile(pattern.replace("*", ".*").replace("?", "."), re.IGNORECASE)
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if regex.search(f):
                    results.append(os.path.join(root, f))
            if len(results) >= 50:
                break
    except PermissionError:
        pass
    if not results:
        return f"在 {directory} 中未找到匹配 '{pattern}' 的文件"
    return f"找到 {len(results)} 个匹配文件:\n" + "\n".join(results[:30])


def _send_file(state: SessionState, to_user: str, path: str, message: str) -> str:
    if not os.path.isfile(path):
        return f"错误：文件不存在 — {path}"
    file_name = os.path.basename(path)
    file_size = os.path.getsize(path)
    if file_size > 50 * 1024 * 1024:
        return f"文件过大（{_format_size(file_size)}），微信限制 50MB"
    try:
        ilink_upload.send_file_message(state, to_user, path, text=message or "")
        return f"已成功发送文件: {file_name} ({_format_size(file_size)})"
    except Exception as e:
        err = str(e)
        import traceback
        traceback.print_exc()
        if len(err) > 500:
            err = err[:500] + "...(错误消息已截断)"
        return f"发送失败: {err}"


def _run_shell(command: str) -> str:
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


# ---- 辅助函数 ----

def _read_text(path: str, max_chars: int = 100_000) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_chars)


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
