import json
import logging
from typing import Optional

import httpx

from channel.client import (
    DEFAULT_LONGPOLL_TIMEOUT_MS, ITEM_TYPE_TEXT, ITEM_TYPE_VOICE,
    ITEM_TYPE_IMAGE, ITEM_TYPE_FILE, CDN_BASE_URL,
    InboundMessage, SESSION_EXPIRED_ERRCODE, SessionExpired,
    _build_base_info, _build_headers,
)

logger = logging.getLogger(__name__)


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
        msg = _parse_message(raw, state)
        if msg is None:
            continue
        if msg.context_token:
            state.context_tokens[msg.from_user_id] = msg.context_token
        msgs.append(msg)

    return msgs


def _parse_message(raw: dict, state=None) -> Optional[InboundMessage]:
    item_list = raw.get("item_list", [])
    text_parts = []
    has_image = False
    has_voice = False
    image_url = ""
    msg_type = "text"

    for item in item_list:
        item_type = item.get("type")
        if item_type == ITEM_TYPE_TEXT:
            t = item.get("text_item", {}).get("text", "")
            if t:
                text_parts.append(t)
        elif item_type == ITEM_TYPE_VOICE:
            has_voice = True
            msg_type = "voice"
            vt = item.get("voice_item", {}).get("text", "")
            if vt:
                text_parts.append(vt)
        elif item_type == ITEM_TYPE_IMAGE:
            has_image = True
            msg_type = "image"
            img_item = item.get("image_item", {})
            cdn_url = img_item.get("cdn_url", "")
            if cdn_url:
                image_url = cdn_url
            else:
                media = img_item.get("media", {})
                eqp = ""
                if media and media.get("encrypt_query_param"):
                    eqp = media["encrypt_query_param"]
                elif img_item.get("encrypt_query_param"):
                    eqp = img_item["encrypt_query_param"]
                if eqp:
                    image_url = f"{CDN_BASE_URL}/download?encrypted_query_param={eqp}"
                    logger.debug("image_url_from_eqp: %s", image_url[:120])
                elif state and hasattr(state, 'cdn_base_url'):
                    img_key = img_item.get("aes_key", "") or img_item.get("md5", "")
                    if img_key:
                        image_url = f"{state.cdn_base_url}/{img_key}"
            if not image_url:
                logger.warning(
                    "image_item_no_url: keys=%s",
                    list(img_item.keys()),
                )

    if not text_parts and not has_image:
        return None

    text = "".join(text_parts)

    if has_image:
        prefix = f"[图片消息] {text}" if text else "[图片消息]"
        if image_url:
            text = f"{prefix}\n[image_url:{image_url}]"
        else:
            text = prefix + "\n[图片URL缺失，无法识别图片内容]"

    image_media_ref = {}
    if has_image:
        img_item = next(
            (it.get("image_item", {}) for it in item_list if it.get("type") == ITEM_TYPE_IMAGE),
            {},
        )
        media = img_item.get("media", {})
        if media:
            image_media_ref = media
        else:
            if img_item.get("encrypt_query_param"):
                image_media_ref = {
                    "encrypt_query_param": img_item.get("encrypt_query_param", ""),
                    "aes_key": img_item.get("aes_key", ""),
                }

    if has_image:
        logger.info(
            "image_parsed: url=%s media_ref=%s",
            "有" if image_url else "无",
            "有" if image_media_ref else "无",
        )

    return InboundMessage(
        seq=raw.get("seq", 0),
        msg_id=raw.get("message_id", 0),
        from_user_id=raw.get("from_user_id", ""),
        session_id=raw.get("session_id", ""),
        context_token=raw.get("context_token", ""),
        text=text,
        create_time_ms=raw.get("create_time_ms", 0),
        msg_type=msg_type,
        image_url=image_url,
        image_media_ref=image_media_ref,
    )
