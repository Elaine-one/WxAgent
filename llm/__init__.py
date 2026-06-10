from llm.base import BaseLLM, LLMResponse, MessageFormat, ToolCall
from llm.format_anthropic import AnthropicFormat
from llm.format_openai import OpenAIFormat
from llm.router import ModelRouter
from llm.universal import UniversalLLM
from tools.base import to_openai_schema, to_anthropic_schema


def create_llm(provider: str, api_key: str, base_url: str,
               model: str, tools: list = None) -> BaseLLM:
    if tools is None:
        tools = []
    if provider == "anthropic":
        fmt = AnthropicFormat()
        tool_schemas = to_anthropic_schema(tools)
    else:
        fmt = OpenAIFormat()
        tool_schemas = to_openai_schema(tools)

    return UniversalLLM(api_key, base_url, model, tool_schemas, fmt)
