"""
LLM 抽象层 — 统一 OpenAI 和 Anthropic 接口，处理 tool calling 格式差异

用法：
    llm = create_llm(provider, api_key, base_url, model, tools)

    # 多轮对话
    response = llm.chat(messages)           # messages 为统一格式的 list[dict]
    if response.tool_calls:
        ...  # 执行工具，构造 tool_result 消息
    else:
        print(response.text)

消息格式（与具体厂商无关的统一格式）：
    {"role": "system", "content": "..."}
    {"role": "user", "content": "..."}
    {"role": "assistant", "content": "..."}              # 纯文本回复
    {"role": "assistant", "tool_calls": [...]}           # 工具调用
    {"role": "tool", "tool_call_id": "...", "content": "..."}  # 工具结果
"""
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from tools import ToolDef, to_openai_schema, to_anthropic_schema


@dataclass
class ToolCall:
    """统一的工具调用表示"""
    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """统一的 LLM 响应"""
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    extra_fields: dict[str, Any] = field(default_factory=dict)  # 厂商特有字段，需原样回传


class BaseLLM:
    """LLM 抽象基类"""

    def chat(self, messages: list[dict]) -> LLMResponse:
        raise NotImplementedError

    def wrap_tool_call(self, calls: list[ToolCall], extra_fields: Optional[dict] = None) -> dict:
        """将工具调用列表转为 assistant 消息"""
        raise NotImplementedError

    def wrap_tool_result(self, call: ToolCall, content: str) -> dict:
        """将工具执行结果转为 tool/user 消息"""
        raise NotImplementedError


class OpenAILLM(BaseLLM):
    """OpenAI 兼容接口（DeepSeek、Qwen、OpenAI 等）"""

    def __init__(self, api_key: str, base_url: str, model: str, tools: list[ToolDef]):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self._tool_schemas = to_openai_schema(tools)

    def chat(self, messages: list[dict]) -> LLMResponse:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._tool_schemas or None,
            tool_choice="auto" if self._tool_schemas else None,
            max_tokens=2048,
        )
        msg = resp.choices[0].message
        # 捕获厂商特有字段（如 DeepSeek 的 reasoning_content），多轮对话需原样回传
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


class AnthropicLLM(BaseLLM):
    """Anthropic 原生接口"""

    def __init__(self, api_key: str, base_url: str, model: str, tools: list[ToolDef]):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        self.model = model
        self._tool_schemas = to_anthropic_schema(tools)

    def chat(self, messages: list[dict]) -> LLMResponse:
        # Anthropic 的 system prompt 通过 system 参数传入，不在 messages 里
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

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_text if system_text else None,
            messages=anthropic_msgs,
            tools=self._tool_schemas or None,
        )
        return LLMResponse(
            text=_extract_anthropic_text(resp),
            tool_calls=_parse_anthropic_tool_calls(resp),
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


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_llm(provider: str, api_key: str, base_url: str,
               model: str, tools: list[ToolDef]) -> BaseLLM:
    if provider == "anthropic":
        return AnthropicLLM(api_key, base_url, model, tools)
    return OpenAILLM(api_key, base_url, model, tools)


# ---------------------------------------------------------------------------
# 响应解析（内部）
# ---------------------------------------------------------------------------

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
