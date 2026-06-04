import json
from pathlib import Path

from fastapi import APIRouter, Query

import config as cfg

router = APIRouter(prefix="/api", tags=["status"])

KEY_MSG_TYPES = {
    "agent_loop_start", "agent_loop_llm_call", "agent_loop_tool_calls",
    "agent_loop_tool_detail", "agent_loop_tool_result", "agent_loop_final_response",
    "agent_loop_done", "agent_loop_max_rounds",
    "react_start", "react_llm_call", "react_tool_calls",
    "react_tool_detail", "react_tool_result", "react_final_response",
    "react_done", "react_needs_confirm", "react_confirm_limit",
    "new_invocation", "interrupt_resume", "send_response", "send_confirm",
    "classify_result", "messages_compressed",
    "qrcode_generated", "qrcode_scanned", "login_confirmed", "qrcode_expired",
    "dangerous_command_confirmed", "cloud_consent_confirmed",
    "pip_install_confirmed", "skill_action_confirmed",
}


def _get_log_file() -> Path:
    return cfg.DATA_DIR / "debug" / "agent.jsonl"


@router.get("/stats")
def get_stats():
    try:
        from observability.metrics import get_stats as _get_stats
        return _get_stats()
    except Exception:
        return {
            "llm_calls": 0,
            "total_tokens": 0,
            "estimated_usd": 0.0,
        }


@router.get("/sessions")
def get_sessions():
    session_file = cfg.PROJECT_ROOT / "session.json"
    if not session_file.exists():
        return {"active": False, "info": {}}
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        info = {
            "has_token": bool(data.get("token")),
            "base_url": data.get("base_url", ""),
            "context_tokens_count": len(data.get("context_tokens", {})),
        }
        return {"active": True, "info": info}
    except Exception as e:
        return {"active": False, "info": {}, "error": str(e)}


@router.get("/logs")
def get_logs(
    lines: int = Query(default=200, ge=1, le=2000),
    key_only: bool = Query(default=True, description="仅返回关键日志类型"),
):
    log_file = _get_log_file()
    if not log_file.exists():
        return {"entries": [], "total": 0}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        selected = all_lines[-lines * 3:] if key_only else all_lines[-lines:]
        entries = []
        for line in selected:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                entry = {"raw": line}

            if key_only:
                msg = entry.get("msg", "")
                level = entry.get("level", "")
                if msg not in KEY_MSG_TYPES and level not in ("ERROR", "error", "WARNING", "warning"):
                    continue

            entries.append(entry)

        entries = entries[-lines:]
        return {"entries": entries, "total": len(entries)}
    except Exception as e:
        return {"entries": [], "total": 0, "error": str(e)}
