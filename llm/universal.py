from typing import Optional, Generator

from llm.base import BaseLLM, LLMResponse, MessageFormat, ToolCall, StreamChunk


class UniversalLLM(BaseLLM):

    def __init__(self, api_key: str, base_url: str, model: str,
                 tool_schemas: list[dict], fmt: MessageFormat):
        self._fmt = fmt
        self._client = fmt.create_client(api_key, base_url)
        self.model = model
        self._tool_schemas = tool_schemas

    def update_tools(self, tool_schemas: list[dict]):
        """Update tool schemas dynamically (e.g. after MCP tools are loaded)."""
        self._tool_schemas = tool_schemas

    def chat(self, messages: list[dict]) -> LLMResponse:
        raw = self._fmt.call_api(self._client, self.model, self._tool_schemas, messages)
        return self._fmt.parse_response(raw)

    def stream_chat(self, messages: list[dict]) -> Generator[StreamChunk, None, None]:
        """流式聊天。如果 format 支持 stream_call_api 则使用，否则降级为非流式。"""
        if hasattr(self._fmt, 'stream_call_api'):
            yield from self._fmt.stream_call_api(self._client, self.model, self._tool_schemas, messages)
        else:
            resp = self.chat(messages)
            yield StreamChunk(delta=resp.text, tool_calls=resp.tool_calls, is_final=True, extra_fields=resp.extra_fields)

    def wrap_tool_call(self, calls: list[ToolCall], extra_fields: Optional[dict] = None) -> dict:
        return self._fmt.wrap_tool_call(calls, extra_fields)

    def wrap_tool_result(self, call: ToolCall, content: str) -> dict:
        return self._fmt.wrap_tool_result(call, content)
