"""LLM 调用成本追踪器。

使用 JSON 文件持久化，Agent 主进程写入，Web API 进程读取，
解决跨进程内存隔离问题。
"""

import json
import threading
from pathlib import Path

from config import PROJECT_ROOT

_STATS_FILE = PROJECT_ROOT / "workspace" / "data" / "cost_stats.json"
_save_lock = threading.Lock()


def _read_stats() -> dict:
    """从文件读取统计数据。"""
    try:
        if _STATS_FILE.exists():
            with open(_STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"llm_calls": 0, "total_tokens": 0, "estimated_usd": 0.0, "models": {}}


def _write_stats(data: dict):
    """写入统计数据到文件。"""
    _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_stats() -> dict:
    """获取当前统计数据（Web API 进程调用此函数）。"""
    return _read_stats()


def record_llm_call(model_name: str, input_tokens: int, output_tokens: int,
                    state: dict | None = None) -> None:
    """记录一次 LLM 调用（Agent 主进程调用此函数）。

    同时更新持久化文件和内存 state（如果提供）。
    """
    import yaml

    # 读取费率
    rates = {}
    try:
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            rates = yaml.safe_load(f).get("model_router", {}).get("rates", {})
    except Exception:
        pass

    rate = rates.get(model_name, {"input": 1.0, "output": 3.0})
    cost_usd = (input_tokens * rate.get("input", 1.0) + output_tokens * rate.get("output", 3.0)) / 1_000_000

    with _save_lock:
        data = _read_stats()
        data["llm_calls"] = data.get("llm_calls", 0) + 1
        data["total_tokens"] = data.get("total_tokens", 0) + input_tokens + output_tokens
        data["estimated_usd"] = round(data.get("estimated_usd", 0.0) + cost_usd, 6)
        # 按模型统计
        models = data.get("models", {})
        m = models.get(model_name, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0})
        m["calls"] += 1
        m["input_tokens"] += input_tokens
        m["output_tokens"] += output_tokens
        m["cost"] = round(m.get("cost", 0.0) + cost_usd, 6)
        models[model_name] = m
        data["models"] = models
        _write_stats(data)

    # 同步更新内存 state
    if state is not None:
        state["cost"] = {
            "llm_calls": data["llm_calls"],
            "total_tokens": data["total_tokens"],
            "estimated_usd": data["estimated_usd"],
        }
