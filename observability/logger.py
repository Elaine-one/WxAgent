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
        # 捕获异常堆栈（logger.exception() 的 exc_info）
        if record.exc_info and record.exc_info[1]:
            base["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            base["exception"] = record.exc_text
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
_initialized = False


def get_logger() -> logging.Logger:
    """初始化日志系统，返回 wxagent logger。

    FileHandler 挂载在 root logger 上，确保项目内所有 logger
    （无论是否使用 wxagent.* 命名）都能写入 agent.jsonl。
    第三方库的日志级别设为 WARNING 以抑制噪音。
    """
    global _logger, _initialized
    if _initialized:
        return _logger or logging.getLogger("wxagent")

    log_dir = config.DATA_DIR / "debug"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.jsonl"

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())

    # 挂载到 root logger — 捕获所有 logger 的输出，不依赖命名约定
    root = logging.getLogger()
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)

    # 抑制第三方库的噪音
    for lib in ("httpx", "httpcore", "urllib3", "openai", "anthropic",
                "asyncio", "charset_normalizer", "h2", "hpack", "hyperframe",
                "jieba", "PIL", "matplotlib", "numba"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    _logger = logging.getLogger("wxagent")
    _initialized = True
    return _logger
