import fnmatch
from pathlib import Path

import yaml

from config import PROJECT_ROOT
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry


TOOL_META = ToolMeta(
    name="batch",
    type=ToolType.BUILTIN,
    description="批量操作工具集：批量重命名、文件整理",
    version="1.0.0",
    tags=["batch", "rename", "organize"],
)


def _load_organize_rules() -> dict:
    try:
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("file_organize", {}).get("rules", {})
    except Exception:
        return {}


def _batch_rename(directory: str, pattern: str, to: str,
                  state=None, user_id: str = "") -> ToolResult:
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return ToolResult(success=False, error=f"目录不存在: {directory}")

    matches = sorted(f for f in dir_path.iterdir()
                     if f.is_file() and fnmatch.fnmatch(f.name, pattern))
    if not matches:
        return ToolResult(success=True, content="没有匹配的文件")

    plan = []
    for i, f in enumerate(matches):
        new_name = to.replace("{n}", str(i + 1)).replace("{name}", f.stem).replace("{ext}", f.suffix[1:] if f.suffix else "")
        new_path = dir_path / new_name
        plan.append((str(f), str(new_path)))

    preview = "\n".join(f"  {a} → {b}" for a, b in plan[:30])
    return ToolResult(
        success=True,
        content=f"重命名计划（共 {len(plan)} 项）:\n{preview}",
        display=f"将重命名 {len(plan)} 个文件，确认执行？",
        requires_confirmation=True,
        confirmation_detail={"type": "batch_rename", "plan": plan},
    )


def _organize_files(directory: str, rule: str = "by_type",
                    state=None, user_id: str = "") -> ToolResult:
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return ToolResult(success=False, error=f"目录不存在: {directory}")

    rules = _load_organize_rules()
    mapping = rules.get(rule)

    if mapping is None:
        available = list(rules.keys())
        return ToolResult(success=False, error=f"未知规则: {rule}，可用: {available}")

    plan = []
    for f in dir_path.iterdir():
        if not f.is_file():
            continue
        if rule == "by_type":
            for category, exts in mapping.items():
                if f.suffix.lower() in exts:
                    dest = dir_path / category / f.name
                    plan.append((str(f), str(dest)))
                    break
        elif rule == "by_date":
            from datetime import datetime
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            sub = mtime.strftime(mapping.get("format", "%Y-%m"))
            dest = dir_path / sub / f.name
            plan.append((str(f), str(dest)))
        elif rule == "by_ext":
            dest = dir_path / f.suffix.lower().lstrip(".") / f.name
            plan.append((str(f), str(dest)))

    preview = "\n".join(f"  {a} → {b}" for a, b in plan[:30])
    return ToolResult(
        success=True,
        content=f"整理计划（共 {len(plan)} 项，规则: {rule}）:\n{preview}",
        display=f"整理计划: {len(plan)} 个文件 → 按 {rule} 分类，确认执行？",
        requires_confirmation=True,
        confirmation_detail={"type": "organize_files", "plan": plan, "rule": rule},
    )


ToolRegistry.register(
    ToolDef(
        name="batch_rename",
        description="批量重命名文件。pattern 为 glob 匹配模式，to 为重命名模板（{n}=序号,{name}=原名,{ext}=扩展名）。执行前需确认。",
        parameters={
            "directory": {"type": "string", "description": "目标目录路径"},
            "pattern": {"type": "string", "description": "glob 匹配模式，如 *.jpg"},
            "to": {"type": "string", "description": "重命名模板，如 photo_{n}.jpg"},
        },
        required=["directory", "pattern", "to"],
    ),
    _batch_rename,
)

ToolRegistry.register(
    ToolDef(
        name="organize_files",
        description="按规则整理文件到子目录。支持 by_type(按类型)/by_date(按日期)/by_ext(按扩展名)。规则由 config.yaml 定义。执行前需确认。",
        parameters={
            "directory": {"type": "string", "description": "目标目录路径"},
            "rule": {"type": "string", "description": "整理规则: by_type / by_date / by_ext"},
        },
        required=["directory"],
    ),
    _organize_files,
)
