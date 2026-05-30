import hashlib
import logging
from datetime import datetime
from pathlib import Path

from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _scan_large_files(directory: str, min_size_mb: int = 100,
                      days_unused: int = 30, max_results: int = 50,
                      state=None, user_id: str = "") -> ToolResult:
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return ToolResult(success=False, error=f"目录不存在: {directory}")

    now = datetime.now().timestamp()
    large_files = []

    for fp in dir_path.rglob("*"):
        if not fp.is_file():
            continue
        try:
            stat = fp.stat()
            size_mb = stat.st_size / (1024 * 1024)
            age_days = (now - stat.st_atime) / 86400
            if size_mb >= min_size_mb and age_days >= days_unused:
                large_files.append({
                    "path": str(fp), "size_mb": round(size_mb, 1),
                    "days_unused": round(age_days),
                })
        except (OSError, PermissionError):
            continue

    large_files.sort(key=lambda x: x["size_mb"], reverse=True)
    results = large_files[:max_results]
    total = sum(f["size_mb"] for f in results)
    lines = [
        f"{i+1}. {f['path']} ({f['size_mb']}MB, {f['days_unused']}天未用)"
        for i, f in enumerate(results)
    ]

    return ToolResult(
        success=True,
        content=f"发现 {len(large_files)} 个大文件（>{min_size_mb}MB 且 {days_unused}天未访问），共 {total:.0f}MB\n"
                + "\n".join(lines),
        display=f"发现 {len(large_files)} 个大文件，共 {total:.0f}MB",
    )


def _find_duplicates(directory: str, max_file_size_mb: int = 100,
                     max_results: int = 20,
                     state=None, user_id: str = "") -> ToolResult:
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return ToolResult(success=False, error=f"目录不存在: {directory}")

    max_bytes = max_file_size_mb * 1024 * 1024
    hash_map: dict[str, list[str]] = {}

    for fp in dir_path.rglob("*"):
        if not fp.is_file():
            continue
        try:
            if fp.stat().st_size > max_bytes:
                continue
            h = hashlib.md5(fp.read_bytes()).hexdigest()
            hash_map.setdefault(h, []).append(str(fp))
        except (OSError, PermissionError):
            continue

    dups = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    lines = []
    for h, paths in list(dups.items())[:max_results]:
        lines.append(f"重复组 ({len(paths)} 份, {paths[0]})")
        for p in paths[1:]:
            lines.append(f"  └─ {p}")

    return ToolResult(
        success=True,
        content="\n".join(lines) if lines else "未发现重复文件",
        display=f"发现 {len(dups)} 组重复文件" if dups else "未发现重复文件",
    )


def _disk_usage(directory: str, top_n: int = 10,
                 state=None, user_id: str = "") -> ToolResult:
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return ToolResult(success=False, error=f"目录不存在: {directory}")

    usage: dict[str, float] = {}
    for fp in dir_path.rglob("*"):
        if fp.is_file():
            try:
                parent = str(fp.relative_to(dir_path).parts[0]) if fp.relative_to(dir_path).parts else "_root"
                usage[parent] = usage.get(parent, 0) + fp.stat().st_size / (1024 * 1024)
            except (OSError, PermissionError):
                continue

    sorted_usage = sorted(usage.items(), key=lambda x: x[1], reverse=True)[:top_n]
    lines = [f"{name}: {size:.1f}MB" for name, size in sorted_usage]
    total = sum(usage.values())

    return ToolResult(
        success=True,
        content=f"目录 {directory} 总占用 {total:.1f}MB\n" + "\n".join(lines),
        display=f"空间统计: 共 {total:.1f}MB，Top {top_n} 目录已列出",
    )


ToolRegistry.register(
    ToolDef(
        name="scan_large_files",
        description="扫描目录下的大文件，按大小和未访问天数筛选。",
        parameters={
            "directory": {"type": "string", "description": "扫描目录"},
            "min_size_mb": {"type": "integer", "description": "最小文件大小(MB)，默认100"},
            "days_unused": {"type": "integer", "description": "未访问天数阈值，默认30"},
            "max_results": {"type": "integer", "description": "最大返回数量，默认50"},
        },
        required=["directory"],
    ),
    _scan_large_files,
)

ToolRegistry.register(
    ToolDef(
        name="find_duplicates",
        description="基于内容Hash检测重复文件。",
        parameters={
            "directory": {"type": "string", "description": "扫描目录"},
            "max_file_size_mb": {"type": "integer", "description": "跳过超过此大小的文件(MB)，默认100"},
            "max_results": {"type": "integer", "description": "最大返回重复组数，默认20"},
        },
        required=["directory"],
    ),
    _find_duplicates,
)

ToolRegistry.register(
    ToolDef(
        name="disk_usage",
        description="统计目录下各子目录的空间占用。",
        parameters={
            "directory": {"type": "string", "description": "统计目录"},
            "top_n": {"type": "integer", "description": "返回占用最大的N个子目录，默认10"},
        },
        required=["directory"],
    ),
    _disk_usage,
)
