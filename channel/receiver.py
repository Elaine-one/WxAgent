import json
from typing import Optional

import httpx

from channel.client import (
    DEFAULT_LONGPOLL_TIMEOUT_MS, ITEM_TYPE_TEXT, ITEM_TYPE_VOICE,
    InboundMessage, SESSION_EXPIRED_ERRCODE, SessionExpired,
    _build_base_info, _build_headers,
)


def get_updates(state, timeout_ms: int = DEFAULT_LONGPOLL_TIMEOUT_MS) -> list[InboundMessage]:
    url = f"{state.base_url}/ilink/bot/getupdates"
    body = json.dumps({
        "get_updates_buf": state.get_updates_buf,
        "base_info": _build_base_info(),
    })
    h = _build_headers(token=state.token)

    try:
        resp = httpx.post(url, content=body, headers=h, timeout=(timeout_ms / 1000) + 5)
        resp.raise_for_status()
        data = resp.json()
    except httpx.ReadTimeout:
        return []

    errcode = data.get("errcode", 0)
    ret = data.get("ret", 0)
    if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
        raise SessionExpired("session 已过期，需要重新登录")

    if (ret != 0 and ret is not None) or (errcode != 0 and errcode is not None):
        raise RuntimeError(f"getUpdates 错误: ret={ret} errcode={errcode} errmsg={data.get('errmsg', '')}")

    new_buf = data.get("get_updates_buf", "")
    if new_buf:
        state.get_updates_buf = new_buf

    suggested_ms = data.get("longpolling_timeout_ms", 0)
    if suggested_ms > 0:
        state._next_poll_timeout = suggested_ms

    msgs: list[InboundMessage] = []
    for raw in data.get("msgs", []):
        msg = _parse_message(raw)
        if msg is None:
            continue
        if msg.context_token:
            state.context_tokens[msg.from_user_id] = msg.context_token
        msgs.append(msg)

    return msgs


def _parse_message(raw: dict) -> Optional[InboundMessage]:
    item_list = raw.get("item_list", [])
    text_parts = []
    for item in item_list:
        if item.get("type") == ITEM_TYPE_TEXT:
            t = item.get("text_item", {}).get("text", "")
            if t:
                text_parts.append(t)
        elif item.get("type") == ITEM_TYPE_VOICE:
            vt = item.get("voice_item", {}).get("text", "")
            if vt:
                text_parts.append(vt)

    if not text_parts:
        return None

    return InboundMessage(
        seq=raw.get("seq", 0),
        msg_id=raw.get("message_id", 0),
        from_user_id=raw.get("from_user_id", ""),
        session_id=raw.get("session_id", ""),
        context_token=raw.get("context_token", ""),
        text="".join(text_parts),
        create_time_ms=raw.get("create_time_ms", 0),
    )
