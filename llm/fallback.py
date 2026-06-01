import config
from llm.base import BaseLLM


class LLMFallback:

    def __init__(self, primary: BaseLLM, fallback: BaseLLM, timeout: float = None):
        self.primary = primary
        self.fallback = fallback
        self.timeout = timeout if timeout is not None else config.ADV_LLM_FALLBACK_TIMEOUT
        self._fallback_count = 0

    def chat(self, messages, **kwargs):
        try:
            return self.primary.chat(messages, **kwargs)
        except Exception as e:
            self._fallback_count += 1
            import logging
            logging.getLogger(__name__).warning(f"主模型失败，切换备用: {e}")
            return self.fallback.chat(messages, **kwargs)

    @property
    def stats(self) -> dict:
        return {"fallback_count": self._fallback_count}

    def wrap_tool_call(self, calls, extra_fields=None):
        try:
            return self.primary.wrap_tool_call(calls, extra_fields)
        except Exception:
            return self.fallback.wrap_tool_call(calls, extra_fields)

    def wrap_tool_result(self, call, content):
        try:
            return self.primary.wrap_tool_result(call, content)
        except Exception:
            return self.fallback.wrap_tool_result(call, content)
