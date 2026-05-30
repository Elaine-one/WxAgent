import json
import logging

from memory.short_term import ShortTermMemory

try:
    from memory.long_term import LongTermMemory
except ImportError:
    LongTermMemory = None

try:
    from memory.retriever import MemoryRetriever
except ImportError:
    MemoryRetriever = None

logger = logging.getLogger(__name__)

PREFERENCE_EXTRACT_PROMPT = """从以下用户消息中提取偏好信息。如果用户表达了明确的偏好，返回 JSON：
{{"preference_key": "...", "preference_value": "...", "confidence": 0.0~1.0}}

偏好可以是任何类型：回复风格、常用目录、文件命名习惯、语言偏好等。
如果没有明显偏好，返回空 JSON {{}}。

用户消息: {message}
助手回复: {response}"""


class MemoryManager:
    def __init__(self):
        self.short_term = ShortTermMemory()
        if LongTermMemory is not None:
            self.long_term = LongTermMemory()
        else:
            self.long_term = None
        if MemoryRetriever is not None:
            self.retriever = MemoryRetriever()
        else:
            self.retriever = None

    def store_fact(self, user_id: str, key: str, value: str):
        if self.long_term:
            try:
                from memory.conflict import resolve_fact_conflict
                existing = self.long_term.retrieve_facts(user_id, key, top_k=3)
                ok, msg = resolve_fact_conflict(user_id, key, value, existing, strategy="overwrite")
                if not ok:
                    logger.info("fact_conflict", extra={"user_id": user_id, "key": key, "msg": msg})
            except Exception:
                pass
            self.long_term.store_fact(user_id, key, value)

    def retrieve_facts(self, user_id: str, query: str, top_k: int = 5) -> list[dict]:
        if self.long_term:
            return self.long_term.retrieve_facts(user_id, query, top_k)
        return []

    def store_preference(self, user_id: str, key: str, value: str):
        if self.long_term:
            self.long_term.store_preference(user_id, key, value)

    def get_preference(self, user_id: str, key: str) -> str | None:
        if self.long_term:
            return self.long_term.get_preference(user_id, key)
        return None

    def get_all_preferences(self, user_id: str) -> dict[str, str]:
        if self.long_term:
            return self.long_term.get_all_preferences(user_id)
        return {}

    def store_conversation(self, user_id: str, messages: list[dict],
                           max_messages: int = 20):
        if self.long_term:
            self.long_term.store_conversation(user_id, messages, max_messages)

    def search_conversations(self, user_id: str, query: str,
                             top_k: int = 5) -> list[dict]:
        if self.long_term:
            return self.long_term.search_conversations(user_id, query, top_k)
        return []

    def search(self, query: str, scope: list[str] | None = None,
               top_k: int = 10, user_id: str | None = None) -> list[dict]:
        if self.retriever:
            return self.retriever.search(query, scope, top_k, user_id)
        return []

    def build_context_prompt(self, user_id: str, user_input: str) -> str:
        hints = []
        try:
            all_prefs = self.get_all_preferences(user_id)
            if all_prefs:
                for key, value in all_prefs.items():
                    hints.append(f"用户偏好 - {key}: {value}")
        except Exception:
            pass

        if user_input and self.retriever:
            try:
                relevant = self.retriever.search(
                    query=user_input, user_id=user_id, top_k=3,
                )
                if relevant and relevant[0]["score"] > 0.5:
                    hints.append(f"相关记忆: {relevant[0]['content'][:100]}")
            except Exception:
                pass

        return "\n".join(hints)

    def maybe_compress(self, messages: list[dict], model) -> list[dict]:
        return self.short_term.maybe_compress(messages, model)

    def learn_from_interaction(self, user_id: str, message: str,
                               response: str, metadata: dict | None = None):
        if not self.long_term:
            return
        try:
            from llm import create_llm
            from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL

            llm = create_llm(LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, "deepseek-chat")
            prompt = PREFERENCE_EXTRACT_PROMPT.format(message=message, response=response)
            resp = llm.chat([{"role": "user", "content": prompt}])

            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            result = json.loads(text)

            if result and result.get("preference_key") and result.get("confidence", 0) >= 0.6:
                self.long_term.store_preference(
                    user_id, result["preference_key"], result["preference_value"],
                )
        except Exception:
            pass
