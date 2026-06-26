import base64
import hashlib
import json
import os
import secrets
from urllib.parse import urlparse, parse_qs

import httpx  # CDN 上传用独立连接

from network.async_client import post_sync
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from channel.client import (
    CDN_BASE_URL, DEFAULT_API_TIMEOUT_S, DEFAULT_UPLOAD_TIMEOUT_S,
    UPLOAD_TYPE_FILE, UPLOAD_TYPE_IMAGE, UPLOAD_TYPE_VIDEO, UPLOAD_TYPE_VOICE,
    ITEM_TYPE_FILE, ITEM_TYPE_IMAGE, ITEM_TYPE_TEXT, ITEM_TYPE_VIDEO,
    SessionState, _build_base_info, _build_headers,
)

_type_names = {
    UPLOAD_TYPE_IMAGE: "图片",
    UPLOAD_TYPE_VIDEO: "视频",
    UPLOAD_TYPE_FILE: "文件",
    UPLOAD_TYPE_VOICE: "语音",
}


def _aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    block_size = 16
    pad_len = block_size - (len(data) % block_size)
    padded = data + bytes([pad_len] * pad_len)
    return encryptor.update(padded) + encryptor.finalize()


def _aes_ecb_padded_size(plaintext_len: int) -> int:
    block_size = 16
    return plaintext_len + (block_size - (plaintext_len % block_size))


def _guess_media_type(file_path: str) -> int:
    ext = os.path.splitext(file_path)[1].lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"}
    audio_exts = {".mp3", ".wav", ".aac", ".ogg", ".m4a", ".silk", ".amr"}

    if ext in image_exts:
        return UPLOAD_TYPE_IMAGE
    if ext in video_exts:
        return UPLOAD_TYPE_VIDEO
    if ext in audio_exts:
        return UPLOAD_TYPE_VOICE
    return UPLOAD_TYPE_FILE


def _get_upload_url(state: SessionState, to_user: str, file_path: str,
                    media_type: int) -> dict:
    with open(file_path, "rb") as f:
        plaintext = f.read()

    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    filesize = _aes_ecb_padded_size(rawsize)
    filekey = secrets.token_hex(16)
    aeskey = secrets.token_bytes(16)

    url = f"{state.base_url}/ilink/bot/getuploadurl"
    body = json.dumps({
        "filekey": filekey,
        "media_type": media_type,
        "to_user_id": to_user,
        "rawsize": rawsize,
        "rawfilemd5": rawfilemd5,
        "filesize": filesize,
        "no_need_thumb": True,
        "aeskey": aeskey.hex(),
        "base_info": _build_base_info(),
    })
    h = _build_headers(token=state.token)
    resp = post_sync(url, content=body, headers=h, timeout=DEFAULT_API_TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()

    upload_full_url = (data.get("upload_full_url") or "").strip()
    upload_param = (data.get("upload_param") or "").strip()

    if not upload_full_url and not upload_param:
        raise RuntimeError(f"getUploadUrl 未返回上传地址: {json.dumps(data, ensure_ascii=False)[:300]}")

    return {
        "plaintext": plaintext,
        "aeskey": aeskey,
        "filekey": filekey,
        "rawsize": rawsize,
        "filesize": filesize,
        "upload_full_url": upload_full_url,
        "upload_param": upload_param,
    }


def _upload_to_cdn(upload_info: dict) -> str:
    ciphertext = _aes_ecb_encrypt(upload_info["plaintext"], upload_info["aeskey"])

    upload_param = upload_info["upload_param"]
    filekey = upload_info["filekey"]
    if upload_param:
        upload_url = f"{CDN_BASE_URL}/upload?encrypted_query_param={upload_param}&filekey={filekey}"
    elif upload_info["upload_full_url"]:
        parsed = urlparse(upload_info["upload_full_url"])
        qs = parse_qs(parsed.query)
        eqp = qs.get("encrypted_query_param", [None])[0]
        fk = qs.get("filekey", [None])[0]
        if eqp and fk:
            upload_url = f"{CDN_BASE_URL}/upload?encrypted_query_param={eqp}&filekey={fk}"
        else:
            upload_url = upload_info["upload_full_url"]
    else:
        raise RuntimeError("CDN 上传缺少 upload_param 和 upload_full_url")

    upload_timeout = max(DEFAULT_UPLOAD_TIMEOUT_S, len(ciphertext) // (100 * 1024) + 15)
    print(f"  📦 密文大小: {len(ciphertext):,} bytes, 上传中...", flush=True)

    resp = httpx.post(
        upload_url,
        content=ciphertext,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(ciphertext)),
        },
        timeout=upload_timeout,
    )
    resp.raise_for_status()

    download_param = resp.headers.get("x-encrypted-param") or resp.headers.get("X-Encrypted-Param") or ""
    if not download_param:
        download_param = resp.text.strip()
    print(f"  ☁ CDN 上传完成, download_param 长度={len(download_param)}", flush=True)
    return download_param


def _send_media_item(state: SessionState, to_user: str, item: dict,
                     text: str = "") -> str:
    ctx_token = state.context_tokens.get(to_user, "")
    items = []
    if text:
        items.append({"type": ITEM_TYPE_TEXT, "text_item": {"text": text}})
    items.append(item)

    last_client_id = ""
    for it in items:
        last_client_id = f"bot-{secrets.token_hex(8)}"
        body = json.dumps({
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user,
                "client_id": last_client_id,
                "message_type": 2,
                "message_state": 2,
                "item_list": [it],
                "context_token": ctx_token,
            },
            "base_info": _build_base_info(),
        })
        h = _build_headers(token=state.token)
        url = f"{state.base_url}/ilink/bot/sendmessage"
        resp = post_sync(url, content=body, headers=h, timeout=DEFAULT_API_TIMEOUT_S)
        resp.raise_for_status()
        if resp.text.strip():
            try:
                data = resp.json()
                ret = data.get("ret", 0)
                if ret and ret != 0:
                    raise RuntimeError(f"sendmessage 返回错误: ret={ret} errmsg={data.get('errmsg', '')}")
            except (json.JSONDecodeError, ValueError):
                pass

    return last_client_id


def send_file_message(state: SessionState, to_user: str, file_path: str,
                      text: str = "") -> str:
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    media_type = _guess_media_type(file_path)
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    print(f"  📤 上传{_type_names.get(media_type, '未知')}: {file_name} ({file_size:,} bytes)", flush=True)

    info = _get_upload_url(state, to_user, file_path, media_type)
    download_param = _upload_to_cdn(info)

    aeskey_hex = info["aeskey"].hex()
    aeskey_b64 = base64.b64encode(aeskey_hex.encode()).decode()
    media_ref = {
        "encrypt_query_param": download_param,
        "aes_key": aeskey_b64,
        "encrypt_type": 1,
    }

    if media_type == UPLOAD_TYPE_IMAGE:
        item = {
            "type": ITEM_TYPE_IMAGE,
            "image_item": {
                "media": media_ref,
                "mid_size": info["filesize"],
            },
        }
    elif media_type == UPLOAD_TYPE_VIDEO:
        item = {
            "type": ITEM_TYPE_VIDEO,
            "video_item": {
                "media": media_ref,
                "video_size": info["filesize"],
            },
        }
    else:
        item = {
            "type": ITEM_TYPE_FILE,
            "file_item": {
                "media": media_ref,
                "file_name": file_name,
                "len": str(file_size),
            },
        }

    msg_id = _send_media_item(state, to_user, item, text)
    print(f"  ✅ 发送完成: msg_id={msg_id}", flush=True)
    return msg_id
