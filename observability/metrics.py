import yaml

from config import PROJECT_ROOT


class CostTracker:
    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = str(PROJECT_ROOT / "config.yaml")
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            self.rates = cfg.get("model_router", {}).get("rates", {})
        except Exception:
            self.rates = {}
        self.llm_calls = 0
        self.total_tokens = 0
        self.estimated_usd = 0.0

    def record_call(self, model: str, input_tokens: int, output_tokens: int):
        self.llm_calls += 1
        self.total_tokens += input_tokens + output_tokens
        rate = self.rates.get(model, {"input": 1.0, "output": 3.0})
        self.estimated_usd += (
            input_tokens * rate["input"] + output_tokens * rate["output"]
        ) / 1_000_000

    def to_dict(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "total_tokens": self.total_tokens,
            "estimated_usd": self.estimated_usd,
        }
