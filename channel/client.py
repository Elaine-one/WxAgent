import base64
import json
import secrets
from dataclasses import dataclass, field
from typing import Optional

import httpx

FIXED_AUTH_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
BOT_TYPE = "3"
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_LONGPOLL_TIMEOUT_MS = 35_000
DEFAULT_API_TIMEOUT_S = 15
DEFAULT_UPLOAD_TIMEOUT_S = 60
SESSION_EXPIRED_ERRCODE = -14

UPLOAD_TYPE_IMAGE = 1
UPLOAD_TYPE_VIDEO = 2
UPLOAD_TYPE_FILE = 3
UPLOAD_TYPE_VOICE = 4

ITEM_TYPE_TEXT = 1
ITEM_TYPE_IMAGE = 2
ITEM_TYPE_VOICE = 3
ITEM_TYPE_FILE = 4
ITEM_TYPE_VIDEO = 5


def _build_client_version() -> int:
    return 0x0001000B


def _random_wechat_uin() -> str:
    u32 = secrets.randbits(32)
    return base64.b64encode(str(u32).encode()).decode()


def _build_base_info() -> dict:
    return {
        "channel_version": "2.4.4",
        "bot_agent": "OpenClaw",
    }


def _build_headers(token: Optional[str] = None) -> dict:
    h = {
        "Content-Type": "application/json",
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(_build_client_version()),
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


@dataclass
class LoginResult:
    bot_token: str
    bot_id: str
    base_url: str
    user_id: str


@dataclass
class InboundMessage:
    seq: int
    from_user_id: str
    session_id: str
    context_token: str
    text: str
    msg_id: int = 0
    create_time_ms: int = 0


@dataclass
class SessionState:
    token: str
    base_url: str
    cdn_base_url: str = CDN_BASE_URL
    get_updates_buf: str = ""
    context_tokens: dict[str, str] = field(default_factory=dict)


class SessionExpired(Exception):
    pass
