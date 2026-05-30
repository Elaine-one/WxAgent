import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    extra_fields: dict[str, Any] = field(default_factory=dict)


class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> LLMResponse: ...

    @abstractmethod
    def wrap_tool_call(self, calls: list[ToolCall], extra_fields: Optional[dict] = None) -> dict: ...

    @abstractmethod
    def wrap_tool_result(self, call: ToolCall, content: str) -> dict: ...


class MessageFormat(ABC):
    @abstractmethod
    def create_client(self, api_key: str, base_url: str) -> Any: ...

    @abstractmethod
    def call_api(self, client: Any, model: str, tool_schemas: list[dict],
                 messages: list[dict]) -> Any: ...

    @abstractmethod
    def parse_response(self, raw: Any) -> LLMResponse: ...

    @abstractmethod
    def wrap_tool_call(self, calls: list[ToolCall], extra_fields: Optional[dict] = None) -> dict: ...

    @abstractmethod
    def wrap_tool_result(self, call: ToolCall, content: str) -> dict: ...
