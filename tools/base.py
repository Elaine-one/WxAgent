from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ToolType(Enum):
    BUILTIN = "builtin"
    SKILL = "skill"
    MCP = "mcp"
    SYSTEM_MODE = "mode"
    THIRD_PARTY = "external"


@dataclass
class ToolMeta:
    name: str
    type: ToolType
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    enabled: bool = True
    priority: int = 100
    config_schema: dict | None = None
    source_path: str = ""
    triggers: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    always_load: bool = False  # Tool Search 模式下始终全量暴露给 LLM


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    success: bool
    content: str = ""
    error: str | None = None
    requires_confirmation: bool = False
    confirmation_detail: dict | None = None
    display: str = ""
    artifact_path: str | None = None


def to_openai_schema(tools: list[ToolDef]) -> list[dict]:
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
