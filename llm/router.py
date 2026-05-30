import yaml

from config import PROJECT_ROOT


class ModelRouter:
    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = str(PROJECT_ROOT / "config.yaml")
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)["model_router"]

    def detect_modality(self, messages: list[dict]) -> str:
        for msg in reversed(messages):
            content = msg.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "image":
                            return "vision"
                        if part.get("type") == "file":
                            return "file"
        return "text"

    def route(self, messages: list[dict], task_type: str = "") -> dict:
        if task_type and task_type in self.config.get("task_overrides", {}):
            return self.config["task_overrides"][task_type]
        modality = self.detect_modality(messages)
        if modality in self.config.get("routes", {}):
            return self.config["routes"][modality]
        default = self.config.get("default", {})
        if isinstance(default, str):
            return self.config["routes"].get("text", {"model": default})
        return default
