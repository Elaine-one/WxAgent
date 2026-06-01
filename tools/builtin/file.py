import os
import re

import config
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry


TOOL_META = ToolMeta(
    name="file",
    type=ToolType.BUILTIN,
    description="文件操作工具集：读取、写入、搜索、发送文件",
    version="1.0.0",
    tags=["file", "io", "filesystem"],
)


def _read_text(path: str, max_chars: int = None) -> str:
    if max_chars is None:
        max_chars = config.ADV_FILE_READ_MAX_CHARS
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_chars)


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _read_file(path: str, **kwargs) -> str:
    if not os.path.isfile(path):
        return f"错误：文件不存在 — {path}"
    try:
        size = os.path.getsize(path)
        if size > config.ADV_FILE_READ_MAX_CHARS:
            return f"文件过大（{_format_size(size)}），只读取前 5000 字符...\n" + _read_text(path, 5000)
        return _read_text(path)
    except UnicodeDecodeError:
        return f"这是二进制文件（{_format_size(size)}），无法直接读取文本内容。如需发送，请用 send_file。"


def _list_directory(path: str, **kwargs) -> str:
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


def _search_files(pattern: str, directory: str, **kwargs) -> str:
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


def _send_file(path: str, state=None, user_id: str = "", message: str = "") -> str:
    from channel.upload import send_file_message

    if not os.path.isfile(path):
        return f"错误：文件不存在 — {path}"
    file_name = os.path.basename(path)
    file_size = os.path.getsize(path)
    if file_size > config.ADV_FILE_SIZE_LIMIT_MB * 1024 * 1024:
        return f"文件过大（{_format_size(file_size)}），微信限制 50MB"
    try:
        send_file_message(state, user_id, path, text=message or "")
        return f"已成功发送文件: {file_name} ({_format_size(file_size)})"
    except Exception as e:
        err = str(e)
        if len(err) > 500:
            err = err[:500] + "...(错误消息已截断)"
        return f"发送失败: {err}"


def _write_file(path: str, content: str, state=None, user_id: str = "") -> ToolResult:
    from security.path_sandbox import PathSandbox
    try:
        safe_path = PathSandbox.validate_write(path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")
        return ToolResult(
            success=True,
            content=f"已写入: {safe_path}",
            display=f"已保存到 {safe_path.name}",
            artifact_path=str(safe_path),
        )
    except PermissionError as e:
        return ToolResult(
            success=False, error=str(e),
            requires_confirmation=True,
            confirmation_detail={"type": "write_outside_workspace", "path": path},
        )


ToolRegistry.register(
    ToolDef(
        name="read_file",
        description="读取本地文件内容。用于查看文档、代码、日志等文本文件。",
        parameters={
            "path": {"type": "string", "description": "文件的绝对路径，如 C:\\Users\\xxx\\Desktop\\report.txt"},
        },
        required=["path"],
    ),
    _read_file,
)

ToolRegistry.register(
    ToolDef(
        name="list_directory",
        description="列出目录中的文件和子目录。用于浏览文件夹内容。",
        parameters={
            "path": {"type": "string", "description": "目录的绝对路径，如 C:\\Users\\xxx\\Desktop"},
        },
        required=["path"],
    ),
    _list_directory,
)

ToolRegistry.register(
    ToolDef(
        name="search_files",
        description="按文件名搜索文件。支持通配符模糊匹配（如 *.pdf、report*）。",
        parameters={
            "pattern": {"type": "string", "description": "搜索模式，如 *.pdf 或 report*"},
            "directory": {"type": "string", "description": "搜索起始目录的绝对路径"},
        },
        required=["pattern", "directory"],
    ),
    _search_files,
)

ToolRegistry.register(
    ToolDef(
        name="send_file",
        description="向当前微信用户发送本地文件或图片。支持图片、文档、压缩包等。",
        parameters={
            "path": {"type": "string", "description": "要发送的文件的绝对路径"},
            "message": {"type": "string", "description": "附带文字说明（可选）"},
        },
        required=["path"],
    ),
    _send_file,
)

ToolRegistry.register(
    ToolDef(
        name="write_file",
        description="写入文件内容。所有写操作限制在 workspace 目录内。",
        parameters={
            "path": {"type": "string", "description": "文件路径，如 workspace/output/report.txt"},
            "content": {"type": "string", "description": "要写入的文件内容"},
        },
        required=["path", "content"],
    ),
    _write_file,
)
