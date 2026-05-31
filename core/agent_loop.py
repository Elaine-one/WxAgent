import time

import config
import llm
import tools
from channel.client import InboundMessage, SessionState, download_image_as_base64, download_media_list
from channel.message import (
    extract_recent_image_context,
    find_recent_image_files,
    save_recent_images,
)


def agent_loop(model: llm.BaseLLM, user_id: str, msg,
               conversations: dict, state: SessionState, phase3_ctx: dict = None) -> str:
    user_text = msg.text if isinstance(msg, InboundMessage) else msg
    image_urls = []
    image_media_refs = []
    file_urls = []
    file_media_refs = []
    file_names = []
    voice_urls = []
    voice_media_refs = []
    video_urls = []
    video_media_refs = []

    if isinstance(msg, InboundMessage):
        if msg.msg_type == "image":
            if msg.image_url:
                image_urls = [msg.image_url]
            if msg.image_media_ref:
                image_media_refs = [msg.image_media_ref]
        elif msg.msg_type == "file":
            if msg.file_url:
                file_urls = [msg.file_url]
            if msg.file_media_ref:
                file_media_refs = [msg.file_media_ref]
            if msg.file_name:
                file_names = [msg.file_name]
        elif msg.msg_type == "voice":
            if msg.voice_url:
                voice_urls = [msg.voice_url]
            if msg.voice_media_ref:
                voice_media_refs = [msg.voice_media_ref]
        elif msg.msg_type == "video":
            if msg.video_url:
                video_urls = [msg.video_url]
            if msg.video_media_ref:
                video_media_refs = [msg.video_media_ref]

    conv = conversations.get(user_id, [])
    if not conv:
        system_prompt = config.SYSTEM_PROMPT
        if phase3_ctx and phase3_ctx.get("memory"):
            try:
                context = phase3_ctx["memory"].build_context_prompt(user_id, user_text)
                if context:
                    system_prompt = f"{system_prompt}\n\n[用户上下文]\n{context}"
            except Exception:
                pass
        conv = [{"role": "system", "content": system_prompt}]

    recent_image_context = extract_recent_image_context(conv)

    if file_urls or file_media_refs:
        sub_dir = str(config.WORKSPACE_DIR / "downloads" / "files")
        saved_file_paths = download_media_list(file_urls, file_media_refs, state, sub_dir, "file")
        for p in saved_file_paths:
            print(f"  📥 文件已下载: {p}")
        file_info = "\n".join(f"- {fn}" for fn in file_names) if file_names else "- 未知文件"
        enriched = f"{user_text}\n\n[用户发送了文件]\n{file_info}" if user_text else f"[用户发送了文件]\n{file_info}"
        if saved_file_paths:
            enriched += f"\n\n[文件已保存到:\n" + "\n".join(saved_file_paths) + "]"
        conv.append({"role": "user", "content": enriched})

    elif voice_urls or voice_media_refs:
        sub_dir = str(config.WORKSPACE_DIR / "downloads" / "voice")
        saved_voice_paths = download_media_list(voice_urls, voice_media_refs, state, sub_dir, "voice", ".silk")
        for p in saved_voice_paths:
            print(f"  🎤 语音已下载: {p}")
        voice_text = ""
        if user_text:
            voice_url_marker = "\n[voice_url:"
            cleaned = user_text.split(voice_url_marker)[0].strip() if voice_url_marker in user_text else user_text
            voice_text = cleaned
        if not voice_text or voice_text == "[语音消息]":
            if saved_voice_paths:
                try:
                    tr = tools.execute("transcribe_audio", {"file_path": saved_voice_paths[0]}, state, user_id)
                    if isinstance(tr, str) and tr:
                        voice_text = f"[语音消息] {tr}"
                        print(f"  🎤 语音转文字(Whisper): {tr[:80]}")
                except Exception:
                    pass
        if voice_text and voice_text != "[语音消息]":
            print(f"  🎤 语音转文字: {voice_text[:80]}")
        enriched = voice_text if voice_text and voice_text != "[语音消息]" else "[语音消息：转写失败]"
        conv.append({"role": "user", "content": enriched})

    elif video_urls or video_media_refs:
        sub_dir = str(config.WORKSPACE_DIR / "downloads" / "videos")
        saved_video_paths = download_media_list(video_urls, video_media_refs, state, sub_dir, "video", ".mp4")
        for p in saved_video_paths:
            print(f"  🎬 视频已下载: {p}")
        enriched = f"{user_text}\n\n[用户发送了视频]" if user_text else "[用户发送了视频]"
        if saved_video_paths:
            enriched += f"\n\n[视频文件路径: {', '.join(saved_video_paths)}]"
        conv.append({"role": "user", "content": enriched})

    elif image_urls or image_media_refs:
        b64_images = []
        if image_urls:
            for i, url in enumerate(image_urls):
                media_ref = image_media_refs[i] if i < len(image_media_refs) else None
                b64 = download_image_as_base64(url, state, media_ref)
                if b64:
                    b64_images.append(b64)
                else:
                    print(f"  ⚠ 图片下载失败 url={url[:100]}")
        elif image_media_refs:
            for media_ref in image_media_refs:
                b64 = download_image_as_base64("", state, media_ref)
                if b64:
                    b64_images.append(b64)
                else:
                    print("  ⚠ 图片下载失败: media_ref 无效")

        main_supports_vision = False
        vision_model = None
        if phase3_ctx and phase3_ctx.get("model_cache") and "vision" in phase3_ctx["model_cache"]:
            vision_model = phase3_ctx["model_cache"]["vision"]
            if vision_model is model:
                main_supports_vision = True
            print(f"  🖼 Vision 模型: {getattr(vision_model, 'model', '?')} | 主模型支持视觉: {main_supports_vision}")
        else:
            print("  ⚠ model_cache 中无 vision 模型，回退到主模型（可能不支持图片）")

        if main_supports_vision and b64_images:
            content_parts = [{"type": "text", "text": user_text or "请描述这张图片"}]
            for b64 in b64_images:
                content_parts.append({"type": "image_url", "image_url": {"url": b64}})
            conv.append({"role": "user", "content": content_parts})
            save_recent_images(b64_images, user_id)
        elif b64_images:
            vision_prompt_parts = [{"type": "text", "text": "请详细描述这张图片的所有内容，包括文字、物体、场景、颜色、布局等，越详细越好。"}]
            for b64 in b64_images:
                vision_prompt_parts.append({"type": "image_url", "image_url": {"url": b64}})
            vision_conv = [{"role": "user", "content": vision_prompt_parts}]
            try:
                vision_resp = vision_model.chat(vision_conv)
                image_desc = vision_resp.text
                print(f"  🖼 Vision 模型已识别图片 ({len(image_desc)} chars)")
            except Exception as e:
                print(f"  ✗ Vision 模型调用失败: {e}")
                image_desc = f"[图片识别失败: {e}]"
            enriched_text = user_text or "请描述这张图片"
            if image_desc:
                enriched_text = f"{enriched_text}\n\n[图片内容：{image_desc}]"
            saved_paths = save_recent_images(b64_images, user_id)
            if saved_paths:
                enriched_text += f"\n\n[图片已保存到: {', '.join(saved_paths)}]"
            conv.append({"role": "user", "content": enriched_text})
        else:
            conv.append({"role": "user", "content": f"[图片下载失败]\n{user_text}"})
    else:
        if recent_image_context:
            recent_image_files = find_recent_image_files()
            enhanced = f"{user_text}\n\n[系统提示：用户之前发送了图片，图片内容如下，请基于此内容操作]\n{recent_image_context}"
            if recent_image_files:
                enhanced += f"\n\n[图片文件路径: {', '.join(recent_image_files)}]"
            conv.append({"role": "user", "content": enhanced})
        else:
            conv.append({"role": "user", "content": user_text})

    for _round in range(config.MAX_TOOL_ROUNDS):
        resp = model.chat(conv)

        if not resp.tool_calls:
            msg_dict = {"role": "assistant", "content": resp.text}
            msg_dict.update(resp.extra_fields)
            conv.append(msg_dict)
            trim_history(conv, config.MAX_HISTORY)
            conversations[user_id] = conv
            return resp.text

        print(f"  🔧 调用 {len(resp.tool_calls)} 个工具: {[tc.name for tc in resp.tool_calls]}")
        conv.append(model.wrap_tool_call(resp.tool_calls, resp.extra_fields))

        for tc in resp.tool_calls:
            result = tools.execute(tc.name, tc.args, state, user_id)
            if len(result) > 4000:
                result = result[:4000] + "\n...(结果已截断)"
            conv.append(model.wrap_tool_result(tc, result))
            print(f"  ✓ {tc.name} → {len(result)} chars")

    conv.append({"role": "user", "content": "请基于以上工具调用结果给出最终回复。"})
    final = model.chat(conv)
    final_msg = {"role": "assistant", "content": final.text}
    final_msg.update(final.extra_fields)
    conv.append(final_msg)
    trim_history(conv, config.MAX_HISTORY)
    conversations[user_id] = conv
    return final.text


def trim_history(conv: list, max_n: int) -> None:
    if len(conv) <= max_n + 1:
        return
    system = conv[0] if conv[0]["role"] == "system" else None
    recent = conv[-max_n:]
    while recent and recent[0]["role"] == "tool":
        recent.pop(0)
    conv.clear()
    if system:
        conv.append(system)
    conv.extend(recent)


def do_login() -> SessionState:
    import channel

    print("正在获取登录二维码...")
    qrcode_url, qrcode = channel.start_qr_login()
    try:
        import qrcode as qrlib
        qr = qrlib.QRCode()
        qr.add_data(qrcode_url)
        qr.print_ascii(invert=True)
    except ImportError:
        pass
    print(f"\n用手机微信扫描上方二维码，或访问：\n{qrcode_url}\n")
    print("等待扫码...", end="", flush=True)
    result = channel.wait_for_login(qrcode)
    state = SessionState(token=result.bot_token, base_url=result.base_url)
    state.context_tokens[result.user_id] = ""
    channel.save_session(state, str(config.SESSION_FILE))
    return state


def interruptible_sleep(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end and config.running:
        time.sleep(0.1)
