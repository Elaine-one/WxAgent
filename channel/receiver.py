import json
import logging
from typing import Optional

import httpx  # ReadTimeout

from network.async_client import post_sync

from channel.client import (
    DEFAULT_LONGPOLL_TIMEOUT_MS, ITEM_TYPE_TEXT, ITEM_TYPE_VOICE,
    ITEM_TYPE_IMAGE, ITEM_TYPE_FILE, ITEM_TYPE_VIDEO, CDN_BASE_URL,
    InboundMessage, SESSION_EXPIRED_ERRCODE, SessionExpired,
    _build_base_info, _build_headers,
)

logger = logging.getLogger(__name__)


def _extract_media(item: dict, key: str) -> tuple[str, dict]:
    sub = item.get(key, {})
    media = sub.get("media", {})
    if media and media.get("encrypt_query_param"):
        return f"{CDN_BASE_URL}/download?encrypted_query_param={media['encrypt_query_param']}", media
    eqp = sub.get("encrypt_query_param", "")
    if eqp:
        ref = {"encrypt_query_param": eqp, "aes_key": sub.get("aes_key", "")}
        return f"{CDN_BASE_URL}/download?encrypted_query_param={eqp}", ref
    cdn_url = sub.get("cdn_url", "")
    return cdn_url, {}


def get_updates(state, timeout_ms: int = DEFAULT_LONGPOLL_TIMEOUT_MS) -> list[InboundMessage]:
    url = f"{state.base_url}/ilink/bot/getupdates"
    body = json.dumps({
        "get_updates_buf": state.get_updates_buf,
        "base_info": _build_base_info(),
    })
    h = _build_headers(token=state.token)

    try:
        resp = post_sync(url, content=body, headers=h, timeout=(timeout_ms / 1000) + 5)
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
    has_image = has_voice = has_file = has_video = False
    image_url = file_url = voice_url = video_url = ""
    image_media_ref = file_media_ref = voice_media_ref = video_media_ref = {}
    file_name = ""
    file_size = 0
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
            voice_item = item.get("voice_item", {})
            vt = voice_item.get("text", "")
            if vt:
                text_parts.append(vt)
            voice_url, voice_media_ref = _extract_media(item, "voice_item")
        elif item_type == ITEM_TYPE_IMAGE:
            has_image = True
            msg_type = "image"
            image_url, image_media_ref = _extract_media(item, "image_item")
            if not image_url:
                logger.warning("image_item_no_url: keys=%s", list(item.get("image_item", {}).keys()))
        elif item_type == ITEM_TYPE_FILE:
            has_file = True
            msg_type = "file"
            file_item = item.get("file_item", {})
            file_name = file_item.get("file_name", "未知文件")
            file_size = int(file_item.get("len", 0) or 0)
            file_url, file_media_ref = _extract_media(item, "file_item")
            logger.info("file_parsed: name=%s size=%s url=%s media_ref=%s",
                        file_name, file_size, "有" if file_url else "无", "有" if file_media_ref else "无")
        elif item_type == ITEM_TYPE_VIDEO:
            has_video = True
            msg_type = "video"
            video_url, video_media_ref = _extract_media(item, "video_item")
            logger.info("video_parsed: url=%s media_ref=%s", "有" if video_url else "无", "有" if video_media_ref else "无")

    if not text_parts and not has_image and not has_file and not has_video and not has_voice:
        return None

    text = "".join(text_parts)

    if has_image:
        prefix = f"[图片消息] {text}" if text else "[图片消息]"
        text = f"{prefix}\n[image_url:{image_url}]" if image_url else prefix + "\n[图片URL缺失，无法识别图片内容]"
        logger.info("image_parsed: url=%s media_ref=%s", "有" if image_url else "无", "有" if image_media_ref else "无")
    elif has_file:
        size_str = f" ({file_size:,} bytes)" if file_size else ""
        text = f"[文件消息] {file_name}{size_str}\n{text}" if text else f"[文件消息] {file_name}{size_str}"
        if file_url:
            text += f"\n[file_url:{file_url}]"
    elif has_video:
        text = f"[视频消息] {text}" if text else "[视频消息]"
        if video_url:
            text += f"\n[video_url:{video_url}]"
    elif has_voice:
        text = f"[语音消息] {text}" if text else "[语音消息]"
        if voice_url:
            text += f"\n[voice_url:{voice_url}]"

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
        file_url=file_url,
        file_media_ref=file_media_ref,
        file_name=file_name,
        file_size=file_size,
        voice_url=voice_url,
        voice_media_ref=voice_media_ref,
        video_url=video_url,
        video_media_ref=video_media_ref,
    )
