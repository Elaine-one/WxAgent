from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Generator


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


@dataclass
class StreamChunk:
    """流式响应的一个片段。"""
    delta: str = ""           # 增量文本
    tool_calls: list[ToolCall] = field(default_factory=list)  # 工具调用（仅最后一块有）
    is_final: bool = False    # 是否为最后一块
    extra_fields: dict[str, Any] = field(default_factory=dict)


class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> LLMResponse: ...

    def stream_chat(self, messages: list[dict]) -> Generator[StreamChunk, None, None]:
        """流式聊天，逐块返回。默认降级为非流式。"""
        resp = self.chat(messages)
        yield StreamChunk(delta=resp.text, tool_calls=resp.tool_calls, is_final=True, extra_fields=resp.extra_fields)

    @property
    def model_name(self) -> str:
        """获取模型 ID 字符串（统一接口，替代 hasattr 链式判断）。"""
        if hasattr(self, 'primary'):
            return getattr(self.primary, 'model', '')
        if hasattr(self, 'model'):
            return self.model
        return ''

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
