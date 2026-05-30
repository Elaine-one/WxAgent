import json
import logging
from datetime import datetime


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": datetime.now().isoformat(),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
            "user_id": getattr(record, "user_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
        }, ensure_ascii=False)


_logger = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger("wxagent")
        if not _logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            _logger.addHandler(handler)
            _logger.setLevel(logging.INFO)
    return _logger
