from memory.short_term import ShortTermMemory

try:
    from memory.long_term import LongTermMemory
except ImportError:
    LongTermMemory = None


class MemoryManager:
    def __init__(self):
        self.short_term = ShortTermMemory()
        if LongTermMemory is not None:
            self.long_term = LongTermMemory()
        else:
            self.long_term = None

    def store_fact(self, user_id: str, key: str, value: str):
        if self.long_term:
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

    def maybe_compress(self, messages: list[dict], model) -> list[dict]:
        return self.short_term.maybe_compress(messages, model)
