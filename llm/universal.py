from typing import Optional

from llm.base import BaseLLM, LLMResponse, MessageFormat, ToolCall


class UniversalLLM(BaseLLM):

    def __init__(self, api_key: str, base_url: str, model: str,
                 tool_schemas: list[dict], fmt: MessageFormat):
        self._fmt = fmt
        self._client = fmt.create_client(api_key, base_url)
        self.model = model
        self._tool_schemas = tool_schemas

    def chat(self, messages: list[dict]) -> LLMResponse:
        raw = self._fmt.call_api(self._client, self.model, self._tool_schemas, messages)
        return self._fmt.parse_response(raw)

    def wrap_tool_call(self, calls: list[ToolCall], extra_fields: Optional[dict] = None) -> dict:
        return self._fmt.wrap_tool_call(calls, extra_fields)

    def wrap_tool_result(self, call: ToolCall, content: str) -> dict:
        return self._fmt.wrap_tool_result(call, content)
