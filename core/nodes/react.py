import json
import logging
import re

import config as cfg
from channel.client import download_image_as_base64, download_media_list
from channel.message import extract_recent_image_context, find_recent_image_files, save_recent_images
from core.deps import Deps, get_deps
from core.state import AgentState
from llm.streaming import split_for_wechat
from observability.metrics import record_llm_call
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.react")


def _msg_to_dict(msg) -> dict:
    if isinstance(msg, dict):
        return msg
    content = getattr(msg, "content", "") or ""
    role = getattr(msg, "type", None) or getattr(msg, "role", "")
    msg_id = getattr(msg, "id", None)
    if role == "system":
        d = {"role": "system", "content": content}
    elif role == "human":
        d = {"role": "user", "content": content}
    elif role == "ai":
        d = {"role": "assistant", "content": content}
        tcs = getattr(msg, "tool_calls", None)
        if tcs:
            openai_tcs = []
            for tc in tcs:
                if isinstance(tc, dict):
                    if tc.get("type") == "tool_call":
                        openai_tcs.append({
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                            },
                        })
                    else:
                        openai_tcs.append(tc)
                else:
                    openai_tcs.append({
                        "id": getattr(tc, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(tc, "name", ""),
                            "arguments": json.dumps(getattr(tc, "args", {}), ensure_ascii=False),
                        },
                    })
            d["tool_calls"] = openai_tcs
    elif role == "tool":
        d = {"role": "tool", "content": content, "tool_call_id": getattr(msg, "tool_call_id", "")}
    else:
        d = {"role": str(role), "content": content}
    if msg_id:
        d["id"] = msg_id
    return d


def _fix_orphaned_tool_calls(conv: list) -> list:
    i = 0
    while i < len(conv):
        msg = conv[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_call_ids = set()
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id", "")
                if tc_id:
                    tool_call_ids.add(tc_id)

            j = i + 1
            found_ids = set()
            while j < len(conv) and conv[j].get("role") == "tool":
                tc_id = conv[j].get("tool_call_id", "")
                if tc_id:
                    found_ids.add(tc_id)
                j += 1

            missing = tool_call_ids - found_ids
            for mid in missing:
                conv.insert(j, {"role": "tool", "content": "操作已取消或未完成", "tool_call_id": mid})
                j += 1
                logger.info("fix_orphaned_tool_call", extra={"tool_call_id": mid})

            i = j
        else:
            i += 1
    return conv


def _inject_skill_tools(model, candidate_skill_names: list[str]):
    """将候选 Skill 动态注入模型工具列表，返回 restore 函数。

    在 LLM 调用前注入，确保 LLM 可见候选 skill；调用后恢复，避免跨用户污染。
    """
    candidate_skill_names = candidate_skill_names or []
    if not candidate_skill_names:
        return lambda: None

    skill_defs = []
    for name in candidate_skill_names:
        td, _ = ToolRegistry._tools.get(f"skill_{name}", (None, None))
        if td:
            skill_defs.append(td)

    if not skill_defs:
        return lambda: None

    from llm.fallback import LLMFallback
    if isinstance(model, LLMFallback):
        unwrapped = [model.primary, model.fallback]
    else:
        unwrapped = [model]

    from tools.base import to_openai_schema, to_anthropic_schema
    from llm.format_anthropic import AnthropicFormat

    original_schemas = []
    for m in unwrapped:
        original_schemas.append(m._tool_schemas)
        if isinstance(m._fmt, AnthropicFormat):
            skill_schemas = to_anthropic_schema(skill_defs)
        else:
            skill_schemas = to_openai_schema(skill_defs)
        m.update_tools(m._tool_schemas + skill_schemas)

    logger.info("skill_injected", extra={"skills": candidate_skill_names, "added": len(skill_defs)})

    def restore():
        for m, orig in zip(unwrapped, original_schemas):
            m.update_tools(orig)

    return restore


async def react_node(state: AgentState, config) -> AgentState:
    deps = get_deps(config)
    model = deps.model
    real_session = deps.real_session(config)
    memory = deps.memory
    model_cache = deps.model_cache
    _uid = state.get("user_id", "-")
    _log = lambda **kw: {**kw, "user_id": _uid}
    conv = [_msg_to_dict(m) for m in state.get("messages", [])]
    conv = _fix_orphaned_tool_calls(conv)

    if not conv or conv[0].get("role") != "system":
        conv = [{"role": "system", "content": cfg.get_system_prompt()}]

    is_resuming = state.get("pending_confirmation") == {} and _has_pending_tool_calls(conv)

    if not is_resuming:
        user_input = state.get("user_input", "")
        has_image = bool(state.get("image_urls")) or bool(state.get("image_media_refs"))
        has_file = bool(state.get("file_urls")) or bool(state.get("file_media_refs"))
        has_voice = bool(state.get("voice_urls")) or bool(state.get("voice_media_refs"))
        has_video = bool(state.get("video_urls")) or bool(state.get("video_media_refs"))

        if memory:
            try:
                context = state.get("memory_context", "")
                if not context:
                    context = memory.build_context_prompt(state.get("user_id", ""), user_input)
                if context and conv[0].get("role") == "system":
                    existing = conv[0].get("content", "")
                    if "[用户上下文]" in existing:
                        base = existing.split("[用户上下文]")[0].rstrip()
                        conv[0] = {"role": "system", "content": f"{base}\n\n[用户上下文]\n{context}"}
                    else:
                        conv[0] = {"role": "system", "content": f"{existing}\n\n[用户上下文]\n{context}"}
            except Exception:
                pass

        if has_file:
            file_urls = state.get("file_urls", [])
            file_media_refs = state.get("file_media_refs", [])
            file_names = state.get("file_names", [])
            file_sizes = state.get("file_sizes", [])
            sub_dir = str(cfg.WORKSPACE_DIR / "downloads" / "files")
            saved_file_paths = download_media_list(file_urls, file_media_refs, real_session, sub_dir, "file")
            for p in saved_file_paths:
                print(f"  📥 文件已下载: {p}")
            state["saved_file_paths"] = saved_file_paths

            file_info_parts = []
            for i, fname in enumerate(file_names):
                fsize = file_sizes[i] if i < len(file_sizes) else 0
                size_str = f" ({fsize:,} bytes)" if fsize else ""
                file_info_parts.append(f"- {fname}{size_str}")
            file_info = "\n".join(file_info_parts)

            enriched = f"{user_input}\n\n[用户发送了文件]\n{file_info}" if user_input else f"[用户发送了文件]\n{file_info}"
            if saved_file_paths:
                enriched += f"\n\n[文件已保存到:\n" + "\n".join(saved_file_paths) + "]"
            else:
                enriched += "\n\n[文件下载失败，请告知用户手动发送文件内容]"
            conv.append({"role": "user", "content": enriched})
            logger.info("react_file_ok", extra=_log(files=len(saved_file_paths)))

        elif has_voice:
            voice_urls = state.get("voice_urls", [])
            voice_media_refs = state.get("voice_media_refs", [])

            # 从 user_input 中提取转写文本（逐行过滤 voice_url 标记行）
            voice_text = ""
            if user_input:
                lines = user_input.split("\n")
                text_lines = [l for l in lines if not l.startswith("[voice_url:")]
                voice_text = "\n".join(text_lines).strip()

            # 只有当微信未提供转写文本时，才进行本地转写（降级方案）
            if not voice_text or voice_text == "[语音消息]":
                sub_dir = str(cfg.WORKSPACE_DIR / "downloads" / "voice")
                saved_voice_paths = download_media_list(voice_urls, voice_media_refs, real_session, sub_dir, "voice", ".silk")
                for p in saved_voice_paths:
                    print(f"  🎤 语音已下载: {p}")
                if saved_voice_paths:
                    try:
                        transcription_result = await ToolRegistry.aexecute("transcribe_audio", {"file_path": saved_voice_paths[0]}, real_session, state.get("user_id", ""))
                        if transcription_result.success and transcription_result.content:
                            voice_text = f"[语音消息] {transcription_result.content}"
                            state["voice_transcription"] = transcription_result.content
                            print(f"  🎤 语音转文字(Whisper): {transcription_result.content[:80]}")
                    except Exception:
                        pass
            else:
                # 微信已提供转写文本，无需本地转写
                print(f"  🎤 语音转文字: {voice_text[:80]}")

            enriched = voice_text if voice_text and voice_text != "[语音消息]" else "[语音消息：转写失败]"
            conv.append({"role": "user", "content": enriched})
            logger.info("react_voice_ok", extra=_log(has_text=bool(voice_text), urls=len(voice_urls)))

        elif has_video:
            video_urls = state.get("video_urls", [])
            video_media_refs = state.get("video_media_refs", [])
            sub_dir = str(cfg.WORKSPACE_DIR / "downloads" / "videos")
            saved_video_paths = download_media_list(video_urls, video_media_refs, real_session, sub_dir, "video", ".mp4")
            for p in saved_video_paths:
                print(f"  🎬 视频已下载: {p}")

            enriched = f"{user_input}\n\n[用户发送了视频]" if user_input else "[用户发送了视频]"
            if saved_video_paths:
                enriched += f"\n\n[视频文件路径: {', '.join(saved_video_paths)}]"
            else:
                enriched += "\n\n[视频下载失败]"
            conv.append({"role": "user", "content": enriched})
            logger.info("react_video_ok", extra=_log(files=len(saved_video_paths)))

        elif has_image:
            if state.get("image_description"):
                enriched = f"{user_input}\n\n[图片内容：{state['image_description']}]" if user_input else f"请描述这张图片\n\n[图片内容：{state['image_description']}]"
                saved_paths = state.get("saved_image_paths", [])
                if saved_paths:
                    enriched += f"\n\n[图片文件路径: {', '.join(saved_paths)}]"
                conv.append({"role": "user", "content": enriched})
            else:
                from channel.client import download_image_as_base64
                image_urls = state.get("image_urls", [])
                media_refs = state.get("image_media_refs", [])
                vision_model = model_cache.get("vision") if model_cache else None

                b64_images = []
                for i, url in enumerate(image_urls):
                    media_ref = media_refs[i] if i < len(media_refs) else None
                    b64 = download_image_as_base64(url, real_session, media_ref)
                    if b64:
                        b64_images.append(b64)
                for media_ref in media_refs[len(image_urls):]:
                    b64 = download_image_as_base64("", real_session, media_ref)
                    if b64:
                        b64_images.append(b64)

                if b64_images and vision_model and vision_model is not model:
                    try:
                        vision_parts = [{"type": "text", "text": "请详细描述这张图片的所有内容，包括文字、物体、场景、颜色、布局等。"}]
                        for b64 in b64_images:
                            vision_parts.append({"type": "image_url", "image_url": {"url": b64}})
                        vision_resp = vision_model.chat([{"role": "user", "content": vision_parts}])
                        image_desc = vision_resp.text
                        enriched = f"{user_input}\n\n[图片内容：{image_desc}]" if user_input else f"请描述这张图片\n\n[图片内容：{image_desc}]"
                        saved_paths = save_recent_images(b64_images, state.get("user_id", ""))
                        if saved_paths:
                            enriched += f"\n\n[图片已保存到: {', '.join(saved_paths)}]"
                        conv.append({"role": "user", "content": enriched})
                        state["image_description"] = image_desc
                        logger.info("react_image_ok", extra=_log(desc_len=len(image_desc), saved=len(saved_paths) if saved_paths else 0))
                    except Exception as e:
                        conv.append({"role": "user", "content": f"[图片识别失败: {e}]\n{user_input}"})
                        logger.warning("react_image_fail", extra=_log(error=str(e)))
                elif b64_images and vision_model is model:
                    content_parts = [{"type": "text", "text": user_input or "请描述这张图片"}]
                    for b64 in b64_images:
                        content_parts.append({"type": "image_url", "image_url": {"url": b64}})
                    saved_paths = save_recent_images(b64_images, state.get("user_id", ""))
                    conv.append({"role": "user", "content": content_parts})
                    if saved_paths:
                        conv.append({"role": "user", "content": f"[图片已保存到: {', '.join(saved_paths)}]"})
                else:
                    conv.append({"role": "user", "content": f"[图片下载失败]\n{user_input}"})
        else:
            recent_image_context = extract_recent_image_context(conv)
            if recent_image_context:
                recent_image_files = find_recent_image_files()
                enhanced = f"{user_input}\n\n[系统提示：用户之前发送了图片，图片内容如下，请基于此内容操作]\n{recent_image_context}"
                if recent_image_files:
                    enhanced += f"\n\n[图片文件路径: {', '.join(recent_image_files)}]"
                conv.append({"role": "user", "content": enhanced})
                logger.info("react_image_context_restored", extra=_log(files=len(recent_image_files) if recent_image_files else 0))
            else:
                conv.append({"role": "user", "content": user_input})
    else:
        logger.info("react_resuming", extra=_log(conv_len=len(conv)))
        user_input = state.get("user_input", "")

    # 候选 Skill 注入：只把 trigger 命中的 skill 注册给本次 LLM 调用
    candidate_skill_names = state.get("candidate_skill_names", [])
    restore_tools = _inject_skill_tools(model, candidate_skill_names)
    if candidate_skill_names:
        skill_hint_parts = ["匹配到以下技能："]
        for name in candidate_skill_names:
            td, _ = ToolRegistry._tools.get(f"skill_{name}", (None, None))
            if td:
                skill_hint_parts.append(f"- {name}: {td.description}")
        skill_hint_parts.append("如果用户希望执行该技能，请调用对应的 skill_ 工具。")
        conv.append({"role": "system", "content": "\n".join(skill_hint_parts)})
        logger.info("react_skill_hint", extra=_log(skills=candidate_skill_names))

    logger.info("react_start", extra=_log(conv_len=len(conv), is_resuming=is_resuming, user_input=state.get("user_input", "")[:80]))

    for _round in range(cfg.MAX_TOOL_ROUNDS):
        logger.info("react_llm_call", extra=_log(round=_round, conv_len=len(conv)))

        # 使用流式调用，边收边判断是否有工具调用
        full_text = ""
        all_tool_calls = []
        extra_fields = {}
        stream_callback = deps.stream_callback
        # 流式发送缓冲区：累积文本，遇到自然断句就发送
        _sent_chars = 0  # 已发送的字符数
        _buffer = ""

        for chunk in model.stream_chat(conv):
            if chunk.delta:
                full_text += chunk.delta
                # 如果没有工具调用且设置了流式回调，尝试边收边发
                if stream_callback and not all_tool_calls:
                    _buffer += chunk.delta
                    # 检查是否达到自然断句点
                    _should_send = False
                    if len(_buffer) >= cfg.ADV_MAX_CHARS:
                        _should_send = True
                    elif len(_buffer) > 60:  # 至少累积 60 字符再检查断句
                        # 段落完成（\n\n）→ 发送，这是一条消息的自然边界
                        if _buffer.endswith("\n\n"):
                            _should_send = True
                        # 句末标点 + 缓冲区较长 → 发送
                        elif len(_buffer) > cfg.ADV_MAX_CHARS * 0.5 and _buffer.rstrip()[-1:] in "。！？；：":
                            _should_send = True
                    if _should_send:
                        try:
                            stream_callback(_buffer)
                            _sent_chars += len(_buffer)
                            _buffer = ""
                        except Exception:
                            pass
            if chunk.tool_calls:
                all_tool_calls = chunk.tool_calls
            if chunk.extra_fields:
                extra_fields.update(chunk.extra_fields)
            if chunk.is_final:
                break

        # 发送缓冲区中剩余的文本
        if stream_callback and not all_tool_calls and _buffer:
            try:
                stream_callback(_buffer)
            except Exception:
                pass

        input_tokens = extra_fields.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = extra_fields.get("usage", {}).get("completion_tokens", 0)
        record_llm_call(model.model_name, input_tokens, output_tokens, state)

        if all_tool_calls:
            tool_names = [tc.name for tc in all_tool_calls]
            print(f"  🔧 调用 {len(tool_names)} 个工具: {tool_names}")
            logger.info("react_tool_calls", extra=_log(round=_round, tools=tool_names))
            for tc in all_tool_calls:
                tc_meta = ToolRegistry.get_meta(tc.name)
                tc_type = tc_meta.type if tc_meta else ""
                logger.info("react_tool_detail", extra=_log(round=_round, tool=tc.name, tool_args=str(tc.args)[:200], tool_type=tc_type))
        else:
            print(f"  → 已回复 ({len(full_text)} chars)")
            logger.info("react_final_response", extra=_log(round=_round, text_len=len(full_text), text_preview=full_text[:200]))

        if not all_tool_calls:
            msg_dict = {"role": "assistant", "content": full_text}
            msg_dict.update(extra_fields)
            conv.append(msg_dict)
            state["final_response"] = full_text
            state["task_complete"] = True
            state["messages"] = _trim(conv, cfg.MAX_HISTORY)
            break

        tool_call_msg = model.wrap_tool_call(all_tool_calls, extra_fields)
        tool_call_msg.setdefault("content", "")
        conv.append(tool_call_msg)

        for tc in all_tool_calls:
            result = await ToolRegistry.aexecute(tc.name, tc.args, real_session, state.get("user_id", ""))

            # tool_call 桥接工具透传确认信息，补充真实工具名
            if result.requires_confirmation and tc.name == "tool_call":
                if not result.confirmation_detail:
                    result.confirmation_detail = {}
                result.confirmation_detail.setdefault("bridge_tool", "tool_call")
                result.confirmation_detail.setdefault("tool_name", tc.args.get("tool_name", ""))
                result.confirmation_detail.setdefault("tool_args", tc.args.get("arguments", {}))

            if result.requires_confirmation:
                confirm_rounds = state.get("confirm_rounds", 0) + 1
                state["confirm_rounds"] = confirm_rounds
                if confirm_rounds > 3:
                    conv.append(model.wrap_tool_result(tc, "确认次数已达上限，操作已自动取消"))
                    print(f"  ✗ {tc.name} → 确认次数超限，已取消")
                    logger.info("react_confirm_limit", extra=_log(tool=tc.name, confirm_rounds=confirm_rounds))
                    continue
                detail = result.confirmation_detail or {
                    "type": "confirm",
                    "detail": f"工具 {tc.name} 需要确认",
                    "tool_name": tc.name,
                    "tool_args": tc.args,
                }
                detail["tool_call_id"] = tc.id
                state["pending_confirmation"] = detail
                state["messages"] = _ensure_content(conv)
                logger.info("react_needs_confirm", extra=_log(tool=tc.name, tool_call_id=tc.id, tool_args=str(tc.args)[:200]))
                restore_tools()
                return state

            result_text = result.content if result.success else f"错误：{result.error or '未知错误'}"
            if len(result_text) > 4000:
                result_text = result_text[:4000] + "\n...(结果已截断)"
            conv.append(model.wrap_tool_result(tc, result_text))
            print(f"  ✓ {tc.name} → {len(result_text)} chars")
            logger.info("react_tool_result", extra=_log(tool=tc.name, success=result.success, result_len=len(result_text), result_preview=result_text[:200]))

    else:
        logger.info("react_max_rounds_reached", extra=_log(rounds=cfg.MAX_TOOL_ROUNDS))
        conv.append({"role": "user", "content": "请基于以上工具调用结果给出最终回复。"})
        final = model.chat(conv)
        msg_dict = {"role": "assistant", "content": final.text}
        msg_dict.update(final.extra_fields)
        conv.append(msg_dict)
        state["final_response"] = final.text
        state["task_complete"] = True
        state["messages"] = _trim(conv, cfg.MAX_HISTORY)

    if memory and state.get("final_response"):
        try:
            memory.store_conversation(
                state["user_id"],
                [{"role": "user", "content": user_input},
                 {"role": "assistant", "content": state["final_response"]}],
            )
            memory.learn_from_interaction(
                state["user_id"],
                user_input,
                state["final_response"],
            )
        except Exception:
            pass

    logger.info("react_done", extra=_log(task_complete=state.get("task_complete"), response_len=len(state.get("final_response", ""))))
    restore_tools()
    return state


def _has_pending_tool_calls(conv: list) -> bool:
    for msg in reversed(conv):
        role = msg.get("role", "")
        if role == "tool":
            return True
        if role == "assistant":
            if msg.get("tool_calls"):
                return True
            break
    return False


def _ensure_content(conv: list) -> list:
    for msg in conv:
        if isinstance(msg, dict):
            msg.setdefault("content", "")
    return conv


def _trim(conv: list, max_n: int) -> list:
    if len(conv) <= max_n + 1:
        return _ensure_content(conv)
    system = conv[0] if conv[0].get("role") == "system" else None
    recent = conv[-max_n:]
    while recent and recent[0].get("role") == "tool":
        recent.pop(0)
    result = []
    if system:
        result.append(system)
    result.extend(recent)
    return _ensure_content(result)
