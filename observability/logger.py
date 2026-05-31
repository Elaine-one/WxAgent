import json
import logging
from datetime import datetime
from pathlib import Path

import config


class JsonFormatter(logging.Formatter):
    def format(self, record):
        base = {
            "ts": datetime.now().isoformat(),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
            "user_id": getattr(record, "user_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
        }
        for key in ("round", "tool", "tools", "tool_args", "success", "conv_len",
                     "is_resuming", "user_input", "text_len", "text_preview",
                     "result_len", "result_preview", "desc_len", "saved",
                     "files", "task_complete", "response_len", "error",
                     "rounds", "uid", "confirm_type", "command"):
            val = getattr(record, key, None)
            if val is not None:
                base[key] = val
        return json.dumps(base, ensure_ascii=False)


_logger = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger("wxagent")
        _logger.propagate = False
        if not _logger.handlers:
            log_dir = config.DATA_DIR / "debug"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "agent.jsonl"

            file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
            file_handler.setFormatter(JsonFormatter())
            _logger.addHandler(file_handler)
            _logger.setLevel(logging.INFO)
    return _logger
