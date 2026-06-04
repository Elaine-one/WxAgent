import json
from typing import Any, Optional

import config
from llm.base import BaseLLM, LLMResponse, MessageFormat, ToolCall, StreamChunk


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

    def stream_call_api(self, client: Any, model: str, tool_schemas: list[dict],
                        messages: list[dict]):
        """流式调用 OpenAI API，逐块返回 StreamChunk。"""
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas or None,
            tool_choice="auto" if tool_schemas else None,
            max_tokens=config.ADV_MAX_TOKENS,
            stream=True,
        )
        # 累积工具调用
        pending_tool_calls: dict[int, dict] = {}
        for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue
            delta = choice.delta
            finish_reason = choice.finish_reason

            # 处理文本增量
            text_delta = getattr(delta, "content", None) or ""

            # 处理工具调用增量
            delta_tool_calls = getattr(delta, "tool_calls", None)
            if delta_tool_calls:
                for dtc in delta_tool_calls:
                    idx = dtc.index
                    if idx not in pending_tool_calls:
                        pending_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if dtc.id:
                        pending_tool_calls[idx]["id"] = dtc.id
                    if dtc.function:
                        if dtc.function.name:
                            pending_tool_calls[idx]["name"] += dtc.function.name
                        if dtc.function.arguments:
                            pending_tool_calls[idx]["arguments"] += dtc.function.arguments

            # 提取 usage
            extra = {}
            usage = getattr(chunk, "usage", None)
            if usage:
                extra["usage"] = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                }

            is_final = finish_reason is not None
            tool_calls_list = []
            if is_final and pending_tool_calls:
                for idx in sorted(pending_tool_calls):
                    tc_data = pending_tool_calls[idx]
                    try:
                        args = json.loads(tc_data["arguments"])
                    except (json.JSONDecodeError, AttributeError):
                        args = {}
                    tool_calls_list.append(ToolCall(
                        id=tc_data["id"], name=tc_data["name"], args=args
                    ))

            yield StreamChunk(
                delta=text_delta,
                tool_calls=tool_calls_list,
                is_final=is_final,
                extra_fields=extra,
            )

    def parse_response(self, raw: Any) -> LLMResponse:
        msg = raw.choices[0].message
        extra = {}
        for attr in ("reasoning_content",):
            val = getattr(msg, attr, None)
            if val:
                extra[attr] = val
        # 提取 token 用量
        usage = getattr(raw, "usage", None)
        if usage:
            extra["usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            }
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
