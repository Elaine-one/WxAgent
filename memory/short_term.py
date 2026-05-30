class ShortTermMemory:
    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages

    def maybe_compress(self, messages: list[dict], model) -> list[dict]:
        if len(messages) <= self.max_messages:
            return messages
        system = messages[0] if messages[0]["role"] == "system" else None
        recent = messages[-(self.max_messages - 1):]
        middle = messages[1:-(self.max_messages - 1)] if system else messages[:-self.max_messages]

        summary_prompt = "请用200字以内总结以下对话的关键信息：\n" + "\n".join(
            f"[{m['role']}]: {str(m.get('content', ''))[:200]}" for m in middle
        )
        summary = model.chat([{"role": "user", "content": summary_prompt}]).text

        result = [{"role": "system", "content": f"{system['content']}\n\n[历史摘要]: {summary}"}] if system else []
        result.extend(recent)
        return result
