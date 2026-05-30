"""
CDN 文件上传到微信 — 基于 openclaw-weixin v2.4.4 协议

三步流程：getUploadUrl → AES 加密上传到 CDN → sendmessage 发送媒体引用
"""
import base64
import hashlib
import json
import os
import secrets
from urllib.parse import urlparse, parse_qs

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import ilink
from ilink import SessionState

# ---------------------------------------------------------------------------
# AES-128-ECB 加密（用于 CDN 文件上传）
# ---------------------------------------------------------------------------
def _aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密，带 PKCS7 填充"""
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    # PKCS7 手动填充
    block_size = 16
    pad_len = block_size - (len(data) % block_size)
    padded = data + bytes([pad_len] * pad_len)
    return encryptor.update(padded) + encryptor.finalize()


def _aes_ecb_padded_size(plaintext_len: int) -> int:
    """计算 AES-128-ECB 加密后的长度（含 PKCS7 填充）"""
    block_size = 16
    return plaintext_len + (block_size - (plaintext_len % block_size))


# ---------------------------------------------------------------------------
# 文件类型识别
# ---------------------------------------------------------------------------
_type_names = {
    ilink.UPLOAD_TYPE_IMAGE: "图片",
    ilink.UPLOAD_TYPE_VIDEO: "视频",
    ilink.UPLOAD_TYPE_FILE: "文件",
    ilink.UPLOAD_TYPE_VOICE: "语音",
}


def _guess_media_type(file_path: str) -> int:
    """根据文件扩展名猜测媒体类型"""
    ext = os.path.splitext(file_path)[1].lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"}
    audio_exts = {".mp3", ".wav", ".aac", ".ogg", ".m4a", ".silk", ".amr"}

    if ext in image_exts:
        return ilink.UPLOAD_TYPE_IMAGE
    if ext in video_exts:
        return ilink.UPLOAD_TYPE_VIDEO
    if ext in audio_exts:
        return ilink.UPLOAD_TYPE_VOICE
    return ilink.UPLOAD_TYPE_FILE


# ---------------------------------------------------------------------------
# CDN 上传三步流程
# ---------------------------------------------------------------------------
def _get_upload_url(state: SessionState, to_user: str, file_path: str,
                    media_type: int) -> dict:
    """向微信服务器申请 CDN 预签名上传 URL 和加密参数"""
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
        "base_info": ilink._build_base_info(),
    })
    h = ilink._build_headers(token=state.token)
    resp = httpx.post(url, content=body, headers=h, timeout=ilink.DEFAULT_API_TIMEOUT_S)
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
    """将文件 AES 加密后上传到 CDN，返回下载凭证

    CDN 响应头 x-encrypted-param 中包含 downloadParam，用于后续 sendmessage 的
    encrypt_query_param 字段。
    """
    ciphertext = _aes_ecb_encrypt(upload_info["plaintext"], upload_info["aeskey"])

    # 构造 CDN 上传 URL：优先用 upload_param，否则解析 upload_full_url
    upload_param = upload_info["upload_param"]
    filekey = upload_info["filekey"]
    if upload_param:
        upload_url = f"{ilink.CDN_BASE_URL}/upload?encrypted_query_param={upload_param}&filekey={filekey}"
    elif upload_info["upload_full_url"]:
        parsed = urlparse(upload_info["upload_full_url"])
        qs = parse_qs(parsed.query)
        eqp = qs.get("encrypted_query_param", [None])[0]
        fk = qs.get("filekey", [None])[0]
        if eqp and fk:
            upload_url = f"{ilink.CDN_BASE_URL}/upload?encrypted_query_param={eqp}&filekey={fk}"
        else:
            upload_url = upload_info["upload_full_url"]
    else:
        raise RuntimeError("CDN 上传缺少 upload_param 和 upload_full_url")

    upload_timeout = max(ilink.DEFAULT_UPLOAD_TIMEOUT_S, len(ciphertext) // (100 * 1024) + 15)
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

    # 下载凭证在响应头 x-encrypted-param 中（不是 body）
    download_param = resp.headers.get("x-encrypted-param") or resp.headers.get("X-Encrypted-Param") or ""
    if not download_param:
        download_param = resp.text.strip()
    print(f"  ☁ CDN 上传完成, download_param 长度={len(download_param)}", flush=True)
    return download_param


def _send_media_item(state: SessionState, to_user: str, item: dict,
                     text: str = "") -> str:
    """发送单条媒体消息项，可附带文本"""
    ctx_token = state.context_tokens.get(to_user, "")
    items = []
    if text:
        items.append({"type": ilink.ITEM_TYPE_TEXT, "text_item": {"text": text}})
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
            "base_info": ilink._build_base_info(),
        })
        h = ilink._build_headers(token=state.token)
        url = f"{state.base_url}/ilink/bot/sendmessage"
        resp = httpx.post(url, content=body, headers=h, timeout=ilink.DEFAULT_API_TIMEOUT_S)
        resp.raise_for_status()
        if resp.text.strip():
            try:
                data = resp.json()
                ret = data.get("ret", 0)
                if ret and ret != 0:
                    raise RuntimeError(f"sendmessage 返回错误: ret={ret} errmsg={data.get('errmsg', '')}")
            except (json.JSONDecodeError, ValueError):
                pass  # 非 JSON 响应，忽略

    return last_client_id


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------
def send_file_message(state: SessionState, to_user: str, file_path: str,
                      text: str = "") -> str:
    """向微信用户发送文件/图片（自动识别类型并走 CDN 加密上传）

    流程：
    1. 获取 CDN 上传 URL（getUploadUrl）
    2. AES-128-ECB 加密文件内容，POST 到 CDN
    3. 从 CDN 响应头提取 x-encrypted-param 作为下载凭证
    4. 构造 sendmessage 请求，发送媒体引用（不是文件本体）
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    media_type = _guess_media_type(file_path)
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    print(f"  📤 上传{_type_names.get(media_type, '未知')}: {file_name} ({file_size:,} bytes)", flush=True)

    # 步骤 1：获取 CDN 上传 URL
    info = _get_upload_url(state, to_user, file_path, media_type)

    # 步骤 2：加密并上传到 CDN
    download_param = _upload_to_cdn(info)

    # 步骤 3：构造消息体并发送
    # aes_key 编码方式（与 npm 源码保持一致）：将 16 字节 key 转为 hex 字符串，
    # 再对 hex 字符串做 base64 编码，即 base64(aeskey_hex_string)
    aeskey_hex = info["aeskey"].hex()
    aeskey_b64 = base64.b64encode(aeskey_hex.encode()).decode()
    media_ref = {
        "encrypt_query_param": download_param,
        "aes_key": aeskey_b64,
        "encrypt_type": 1,
    }

    if media_type == ilink.UPLOAD_TYPE_IMAGE:
        item = {
            "type": ilink.ITEM_TYPE_IMAGE,
            "image_item": {
                "media": media_ref,
                "mid_size": info["filesize"],  # 加密后的文件大小
            },
        }
    elif media_type == ilink.UPLOAD_TYPE_VIDEO:
        item = {
            "type": ilink.ITEM_TYPE_VIDEO,
            "video_item": {
                "media": media_ref,
                "video_size": info["filesize"],
            },
        }
    else:
        item = {
            "type": ilink.ITEM_TYPE_FILE,
            "file_item": {
                "media": media_ref,
                "file_name": file_name,
                "len": str(file_size),
            },
        }

    msg_id = _send_media_item(state, to_user, item, text)
    print(f"  ✅ 发送完成: msg_id={msg_id}", flush=True)
    return msg_id
