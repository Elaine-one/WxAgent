from tools.base import ToolDef, ToolResult, to_anthropic_schema, to_openai_schema
from tools.registry import ToolRegistry

import tools.file_tools
import tools.system_tools

ALL_TOOLS = ToolRegistry.get_all_defs()


def execute(name: str, args: dict, state, user_id: str) -> str:
    result = ToolRegistry.execute(name, args, state, user_id)
    if result.success:
        return result.content
    return f"错误：{result.error}" if result.error else "未知错误"
