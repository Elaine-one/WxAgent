import logging

logger = logging.getLogger(__name__)


def resolve_fact_conflict(user_id: str, new_key: str, new_value: str,
                          existing_facts: list[dict],
                          strategy: str = "overwrite") -> tuple[bool, str]:
    for f in existing_facts:
        if f.get("key") == new_key and f.get("value") != new_value:
            if strategy == "overwrite":
                return True, f"已更新：{f['value']} → {new_value}"
            elif strategy == "keep_both":
                return True, f"已保留新旧两条记录"
            elif strategy == "ask_user":
                return False, f"冲突：旧值={f['value']}，新值={new_value}，请确认"
    return True, ""
