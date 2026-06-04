import base64
import time

import config


def message_signature(msg) -> str:
    from channel.client import InboundMessage
    if not isinstance(msg, InboundMessage):
        return ""
    parts = [msg.text or "", msg.msg_type or ""]
    if msg.msg_type == "image":
        parts.append(msg.image_url[:50] if msg.image_url else "")
    return "|".join(parts)


def merge_messages(msgs: list) -> "InboundMessage":
    from channel.client import InboundMessage

    if len(msgs) == 1:
        return msgs[0]

    text_parts = []
    all_image_urls = []
    all_image_media_refs = []
    all_file_urls = []
    all_file_media_refs = []
    all_file_names = []
    all_file_sizes = []
    all_voice_urls = []
    all_voice_media_refs = []
    all_video_urls = []
    all_video_media_refs = []
    has_image = False
    has_file = False
    has_voice = False
    has_video = False
    last_msg = msgs[-1]

    for m in msgs:
        if not isinstance(m, InboundMessage):
            continue
        if m.msg_type == "image":
            has_image = True
            if m.image_url:
                all_image_urls.append(m.image_url)
            if m.image_media_ref:
                all_image_media_refs.append(m.image_media_ref)
            if m.text and m.text != "[图片消息]":
                text_parts.append(m.text)
        elif m.msg_type == "file":
            has_file = True
            if m.file_url:
                all_file_urls.append(m.file_url)
            if m.file_media_ref:
                all_file_media_refs.append(m.file_media_ref)
            if m.file_name:
                all_file_names.append(m.file_name)
            if m.file_size:
                all_file_sizes.append(m.file_size)
            if m.text:
                text_parts.append(m.text)
        elif m.msg_type == "voice":
            has_voice = True
            if m.voice_url:
                all_voice_urls.append(m.voice_url)
            if m.voice_media_ref:
                all_voice_media_refs.append(m.voice_media_ref)
            if m.text:
                text_parts.append(m.text)
        elif m.msg_type == "video":
            has_video = True
            if m.video_url:
                all_video_urls.append(m.video_url)
            if m.video_media_ref:
                all_video_media_refs.append(m.video_media_ref)
            if m.text:
                text_parts.append(m.text)
        else:
            if m.text:
                text_parts.append(m.text)

    merged_text = "\n".join(text_parts) if text_parts else ""

    if has_image:
        if not merged_text or merged_text == "[图片消息]":
            merged_text = "[图片消息]"
    elif has_file:
        if not merged_text:
            merged_text = "[文件消息]"
    elif has_voice:
        if not merged_text:
            merged_text = "[语音消息]"
    elif has_video:
        if not merged_text:
            merged_text = "[视频消息]"

    if has_image:
        msg_type = "image"
    elif has_file:
        msg_type = "file"
    elif has_voice:
        msg_type = "voice"
    elif has_video:
        msg_type = "video"
    else:
        msg_type = "text"

    print(f"  📦 合并 {len(msgs)} 条消息 (type={msg_type})")

    return InboundMessage(
        seq=last_msg.seq,
        msg_id=last_msg.msg_id,
        from_user_id=last_msg.from_user_id,
        session_id=last_msg.session_id,
        context_token=last_msg.context_token,
        text=merged_text,
        create_time_ms=last_msg.create_time_ms,
        msg_type=msg_type,
        image_url=all_image_urls[0] if all_image_urls else "",
        image_media_ref=all_image_media_refs[0] if all_image_media_refs else {},
        file_url=all_file_urls[0] if all_file_urls else "",
        file_media_ref=all_file_media_refs[0] if all_file_media_refs else {},
        file_name=all_file_names[0] if all_file_names else "",
        file_size=all_file_sizes[0] if all_file_sizes else 0,
        voice_url=all_voice_urls[0] if all_voice_urls else "",
        voice_media_ref=all_voice_media_refs[0] if all_voice_media_refs else {},
        video_url=all_video_urls[0] if all_video_urls else "",
        video_media_ref=all_video_media_refs[0] if all_video_media_refs else {},
        # 保留完整列表供多语音场景使用
        _all_voice_urls=all_voice_urls,
        _all_voice_media_refs=all_voice_media_refs,
    )


def extract_recent_image_context(conv: list, lookback: int = 6) -> str:
    parts = []
    for msg in conv[-lookback:]:
        content = msg.get("content", "")
        if isinstance(content, str) and "[图片内容：" in content:
            start = content.find("[图片内容：")
            depth = 0
            end = start
            for i in range(start + 6, min(len(content), start + 5000)):
                if content[i] == '[':
                    depth += 1
                elif content[i] == ']':
                    if depth == 0:
                        end = i + 1
                        break
                    depth -= 1
            if end > start:
                desc = content[start:end]
                if desc not in parts:
                    parts.append(desc)
    return "\n".join(parts) if parts else ""


def save_recent_images(b64_images: list, user_id: str) -> list[str]:
    saved = []
    img_dir = config.WORKSPACE_DIR / "downloads" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for i, b64 in enumerate(b64_images):
        try:
            data_uri = b64
            if data_uri.startswith("data:"):
                header, b64data = data_uri.split(",", 1)
                ext = "png" if "png" in header else "jpg"
            else:
                b64data = data_uri
                ext = "jpg"
            img_bytes = base64.b64decode(b64data)
            ts = int(time.time())
            fname = f"img_{ts}_{i}.{ext}"
            fpath = img_dir / fname
            fpath.write_bytes(img_bytes)
            saved.append(str(fpath))
            print(f"  💾 图片已保存: {fpath}")
        except Exception as e:
            print(f"  ⚠ 图片保存失败: {e}")
    return saved


def find_recent_image_files(max_age: int = 300) -> list[str]:
    img_dir = config.WORKSPACE_DIR / "downloads" / "images"
    if not img_dir.exists():
        return []
    now = time.time()
    files = []
    for f in sorted(img_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
            if now - f.stat().st_mtime < max_age:
                files.append(str(f))
            if len(files) >= 5:
                break
    return files
