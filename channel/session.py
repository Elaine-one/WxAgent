import json
import os

from channel.client import CDN_BASE_URL, SessionState


def save_session(state: SessionState, path: str = "session.json") -> None:
    with open(path, "w") as f:
        json.dump({
            "token": state.token,
            "base_url": state.base_url,
            "cdn_base_url": state.cdn_base_url,
            "get_updates_buf": state.get_updates_buf,
            "context_tokens": state.context_tokens,
        }, f, indent=2)
    os.chmod(path, 0o600)


def load_session(path: str = "session.json") -> SessionState | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    s = SessionState(
        token=data["token"],
        base_url=data["base_url"],
        cdn_base_url=data.get("cdn_base_url", CDN_BASE_URL),
        get_updates_buf=data.get("get_updates_buf", ""),
    )
    s.context_tokens = data.get("context_tokens", {})
    return s
