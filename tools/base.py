from dataclasses import dataclass, field
from typing import Any, Callable


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
