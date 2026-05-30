from typing import Callable

from tools.base import ToolDef, ToolResult


class ToolRegistry:
    _tools: dict[str, tuple[ToolDef, Callable]] = {}

    @classmethod
    def register(cls, tool: ToolDef, handler: Callable) -> None:
        cls._tools[tool.name] = (tool, handler)

    @classmethod
    def execute(cls, name: str, args: dict, state, user_id: str) -> ToolResult:
        if name not in cls._tools:
            return ToolResult(success=False, error=f"未知工具: {name}")
        tool_def, handler = cls._tools[name]
        try:
            output = handler(**args, state=state, user_id=user_id)
            if isinstance(output, ToolResult):
                return output
            return ToolResult(success=True, content=str(output))
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    @classmethod
    def get_all_defs(cls) -> list[ToolDef]:
        return [td for td, _ in cls._tools.values()]

    @classmethod
    def clear(cls) -> None:
        cls._tools.clear()
