import json
from typing import Any, Optional

import config
from llm.base import BaseLLM, LLMResponse, MessageFormat, ToolCall


class OpenAIFormat(MessageFormat):

    def create_client(self, api_key: str, base_url: str) -> Any:
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url)

    def call_api(self, client: Any, model: str, tool_schemas: list[dict],
                 messages: list[dict]) -> Any:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas or None,
            tool_choice="auto" if tool_schemas else None,
            max_tokens=config.ADV_MAX_TOKENS,
        )

    def parse_response(self, raw: Any) -> LLMResponse:
        msg = raw.choices[0].message
        extra = {}
        for attr in ("reasoning_content",):
            val = getattr(msg, attr, None)
            if val:
                extra[attr] = val
        return LLMResponse(
            text=getattr(msg, "content", "") or "",
            tool_calls=_parse_openai_tool_calls(msg),
            extra_fields=extra,
        )

    def wrap_tool_call(self, calls: list[ToolCall], extra_fields: Optional[dict] = None) -> dict:
        msg: dict = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.args, ensure_ascii=False),
                    },
                }
                for tc in calls
            ],
        }
        if extra_fields:
            msg.update(extra_fields)
        return msg

    def wrap_tool_result(self, call: ToolCall, content: str) -> dict:
        return {"role": "tool", "tool_call_id": call.id, "content": content}


def _parse_openai_tool_calls(message) -> list[ToolCall]:
    raw = getattr(message, "tool_calls", None)
    if not raw:
        return []
    result = []
    for tc in raw:
        try:
            args = json.loads(tc.function.arguments)
        except (json.JSONDecodeError, AttributeError):
            args = {}
        result.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
    return result
