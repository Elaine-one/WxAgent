import base64
import json
import secrets
from dataclasses import dataclass, field
from typing import Optional

import httpx

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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
    msg_type: str = "text"
    image_url: str = ""
    image_media_ref: dict = field(default_factory=dict)


@dataclass
class SessionState:
    token: str
    base_url: str
    cdn_base_url: str = CDN_BASE_URL
    get_updates_buf: str = ""
    context_tokens: dict[str, str] = field(default_factory=dict)


class SessionExpired(Exception):
    pass


def download_image_as_base64(url: str, session: SessionState | None = None,
                             media_ref: dict | None = None) -> str:
    try:
        if media_ref and media_ref.get("encrypt_query_param"):
            eqp = media_ref["encrypt_query_param"]
            download_url = f"{CDN_BASE_URL}/download?encrypted_query_param={eqp}"
            resp = httpx.get(download_url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            ciphertext = resp.content
            aes_key_b64 = media_ref.get("aes_key", "")
            if aes_key_b64:
                aes_key_hex = base64.b64decode(aes_key_b64).decode()
                aes_key_bytes = bytes.fromhex(aes_key_hex)
                cipher = Cipher(algorithms.AES(aes_key_bytes), modes.ECB())
                decryptor = cipher.decryptor()
                plaintext = decryptor.update(ciphertext) + decryptor.finalize()
                pad_len = plaintext[-1]
                if 0 < pad_len <= 16:
                    plaintext = plaintext[:-pad_len]
                b64 = base64.b64encode(plaintext).decode()
                return f"data:image/jpeg;base64,{b64}"
            else:
                b64 = base64.b64encode(ciphertext).decode()
                return f"data:image/jpeg;base64,{b64}"

        if not url:
            import logging
            logging.getLogger(__name__).warning(
                "图片下载跳过: url 为空且 media_ref 无 encrypt_query_param"
            )
            return ""

        headers = {}
        if session and "cdn.weixin" in url:
            headers = _build_headers(token=session.token)
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg")
        if "/" in content_type:
            mime = content_type.split(";")[0].strip()
        else:
            mime = "image/jpeg"
        b64 = base64.b64encode(resp.content).decode()
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "图片下载失败 url=%s session=%s media_ref=%s: %s",
            url[:120] if url else "(空)",
            "有" if session else "无",
            "有" if media_ref else "无",
            e,
        )
        return ""
