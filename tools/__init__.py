import logging
from pathlib import Path

from tools.base import ToolDef, ToolResult, ToolMeta, ToolType, to_anthropic_schema, to_openai_schema
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.tools")


def _discover_and_load_tools():
    project_root = Path(__file__).parent.parent

    builtin_path = project_root / "tools" / "builtin"
    if builtin_path.exists():
        for py_file in builtin_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = py_file.stem
            try:
                __import__(f"tools.builtin.{module_name}")
            except Exception as e:
                logger.warning(f"Failed to load builtin tool {module_name}: {e}")

    skills_path = project_root / "tools" / "skills"
    if skills_path.exists():
        for skill_file in skills_path.glob("*"):
            if skill_file.suffix == ".py":
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(skill_file.stem, skill_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                except Exception as e:
                    logger.warning(f"Failed to load skill {skill_file.name}: {e}")
            elif skill_file.suffix == ".md":
                try:
                    metas = ToolRegistry._load_md_skill(skill_file)
                    logger.debug(f"Loaded md skill: {skill_file.name}, metas: {len(metas)}")
                except Exception as e:
                    logger.warning(f"Failed to load md skill {skill_file.name}: {e}")



_discover_and_load_tools()

ALL_TOOLS = ToolRegistry.get_all_defs()


def execute(name: str, args: dict, state, user_id: str) -> str:
    result = ToolRegistry.execute(name, args, state, user_id)
    if result.success:
        return result.content
    return f"错误：{result.error}" if result.error else "未知错误"


def get_tool_stats() -> dict:
    return ToolRegistry.get_stats()


def list_tools(type: str = None, enabled: bool = None) -> list[dict]:
    tool_type = ToolType(type) if type else None
    metas = ToolRegistry.get_all_metas(type=tool_type, enabled=enabled)
    return [
        {
            "name": m.name,
            "type": m.type.value,
            "description": m.description,
            "enabled": m.enabled,
            "version": m.version,
            "tags": m.tags,
        }
        for m in metas
    ]


def reload_tools() -> dict:
    ToolRegistry.reload()
    global ALL_TOOLS
    ALL_TOOLS = ToolRegistry.get_all_defs()
    return get_tool_stats()
