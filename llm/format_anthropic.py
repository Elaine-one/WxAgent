import json
from typing import Any, Optional

from llm.base import BaseLLM, LLMResponse, MessageFormat, ToolCall


class AnthropicFormat(MessageFormat):

    def create_client(self, api_key: str, base_url: str) -> Any:
        import anthropic
        return anthropic.Anthropic(api_key=api_key, base_url=base_url)

    def call_api(self, client: Any, model: str, tool_schemas: list[dict],
                 messages: list[dict]) -> Any:
        system_text = ""
        anthropic_msgs = []
        for m in messages:
            role = m.get("role", "")
            if role == "system":
                system_text = m.get("content", "")
            elif role == "user":
                anthropic_msgs.append({"role": "user", "content": m.get("content", "")})
            elif role == "assistant":
                if "tool_calls" in m:
                    anthropic_msgs.append({
                        "role": "assistant",
                        "content": [
                            {"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                             "input": json.loads(tc["function"]["arguments"])}
                            for tc in m["tool_calls"]
                        ],
                    })
                else:
                    anthropic_msgs.append({"role": "assistant", "content": m.get("content", "")})
            elif role == "tool":
                anthropic_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", ""),
                        "content": m.get("content", ""),
                    }],
                })

        return client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_text if system_text else None,
            messages=anthropic_msgs,
            tools=tool_schemas or None,
        )

    def parse_response(self, raw: Any) -> LLMResponse:
        return LLMResponse(
            text=_extract_anthropic_text(raw),
            tool_calls=_parse_anthropic_tool_calls(raw),
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


def _parse_anthropic_tool_calls(response) -> list[ToolCall]:
    result = []
    for block in response.content:
        if getattr(block, "type", "") == "tool_use":
            result.append(ToolCall(
                id=block.id,
                name=block.name,
                args=dict(block.input) if block.input else {},
            ))
    return result


def _extract_anthropic_text(response) -> str:
    parts = []
    for block in response.content:
        if getattr(block, "type", "") == "text":
            parts.append(block.text)
    return "".join(parts)
