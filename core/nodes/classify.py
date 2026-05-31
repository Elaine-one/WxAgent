import json
import logging

from channel.client import download_image_as_base64
from channel.message import save_recent_images
from core.deps import Deps
from core.state import AgentState
from observability.metrics import record_llm_call

logger = logging.getLogger("wxagent.classify")

CLASSIFY_PROMPT = """判断用户消息的类型，回复 JSON:
{{"type": "meta"|"confirm"|"new_task"|"interrupt"}}
- meta: 元命令（/reset、/help、/status、/tasks、/usage）
- confirm: 对确认请求的回复（Y/N/是/否/确认/取消等）
- interrupt: 当前有任务在执行，用户想打断/纠正/放弃
- new_task: 其他一切新请求
当前是否有正在执行的任务: {has_active_task}
用户消息: {user_input}"""

VISION_PROMPT = "请详细描述这张图片的内容，包括文字、物体、场景等所有可见信息。"


def _get_deps(config: dict | None) -> Deps:
    if config:
        deps = config.get("configurable", {}).get("deps")
        if deps is not None:
            return deps
    raise RuntimeError("Deps not found in config")


def _build_multimodal_content(state, session=None):
    text = state.get("user_input", "")
    images = state.get("image_urls", [])
    media_refs = state.get("image_media_refs", [])
    if not images and not media_refs:
        return text, []

    content = [{"type": "text", "text": text or "请描述这张图片"}]
    b64_list = []

    if images:
        for i, url in enumerate(images):
            media_ref = media_refs[i] if i < len(media_refs) else None
            b64_uri = download_image_as_base64(url, session, media_ref)
            if b64_uri:
                content.append({"type": "image_url", "image_url": {"url": b64_uri}})
                b64_list.append(b64_uri)
            else:
                content.append({"type": "text", "text": f"[图片下载失败: {url[:80]}]"})
    elif media_refs:
        for media_ref in media_refs:
            b64_uri = download_image_as_base64("", session, media_ref)
            if b64_uri:
                content.append({"type": "image_url", "image_url": {"url": b64_uri}})
                b64_list.append(b64_uri)
            else:
                content.append({"type": "text", "text": "[图片下载失败: media_ref无效]"})

    return content, b64_list


def classify_node(state: AgentState, config) -> AgentState:
    deps = _get_deps(config)
    model = deps.model
    real_session = deps.real_session(config)
    memory = deps.memory
    model_cache = deps.model_cache

    has_image = bool(state.get("image_urls")) or bool(state.get("image_media_refs"))
    main_supports_vision = False
    vision_model = None

    if has_image and model_cache and "vision" in model_cache:
        vision_model = model_cache["vision"]
        if vision_model is model:
            main_supports_vision = True
            model = vision_model
        else:
            model = vision_model

    if has_image and not main_supports_vision and vision_model:
        try:
            content, b64_list = _build_multimodal_content(state, real_session)
            if isinstance(content, list):
                vision_messages = [{"role": "user", "content": content}]
                vision_resp = vision_model.chat(vision_messages)
                image_desc = vision_resp.text
                logger.info("image_analyzed", extra={"description_len": len(image_desc)})
                original_input = state.get("user_input", "")
                if original_input:
                    state["user_input"] = f"{original_input}\n\n[图片内容：{image_desc}]"
                else:
                    state["user_input"] = f"请描述这张图片\n\n[图片内容：{image_desc}]"
                state["image_description"] = image_desc
                if b64_list:
                    saved_paths = save_recent_images(b64_list, state.get("user_id", ""))
                    state["saved_image_paths"] = saved_paths
                    if saved_paths:
                        print(f"  💾 图片已保存: {', '.join(saved_paths)}")
        except Exception as e:
            state["image_description"] = f"[图片识别失败: {e}]"
            logger.warning("image_analysis_failed", extra={"error": str(e)[:200]})

    has_active = not state.get("task_complete", True)
    prompt = CLASSIFY_PROMPT.format(
        has_active_task=has_active,
        user_input=state["user_input"],
    )

    context = ""
    if memory:
        try:
            context = memory.build_context_prompt(state.get("user_id", ""), state["user_input"])
        except Exception:
            pass

    state["memory_context"] = context

    full_prompt = f"[用户上下文]\n{context}\n\n{prompt}" if context else prompt

    if has_image and main_supports_vision:
        content, b64_list = _build_multimodal_content(state, real_session)
        if b64_list:
            saved_paths = save_recent_images(b64_list, state.get("user_id", ""))
            state["saved_image_paths"] = saved_paths
            if saved_paths:
                print(f"  💾 图片已保存: {', '.join(saved_paths)}")
        if isinstance(content, str):
            messages = [{"role": "user", "content": full_prompt}]
        else:
            messages = [{"role": "user", "content": [{"type": "text", "text": full_prompt}] + content[1:]}]
    else:
        messages = [{"role": "user", "content": full_prompt}]

    resp = model.chat(messages)

    input_tokens = resp.extra_fields.get("usage", {}).get("prompt_tokens", 0)
    output_tokens = resp.extra_fields.get("usage", {}).get("completion_tokens", 0)
    model_name = getattr(model, 'primary', model).__class__.__name__ if hasattr(model, 'primary') else ""
    record_llm_call(model_name, input_tokens, output_tokens, state)

    try:
        result = json.loads(resp.text)
        msg_type = result.get("type", "new_task")
    except (json.JSONDecodeError, KeyError):
        msg_type = "new_task"

    if msg_type not in ("meta", "confirm", "interrupt", "new_task"):
        msg_type = "new_task"

    state["msg_type"] = msg_type

    logger.info("classify_result", extra={"msg_type": msg_type, "user_input": state["user_input"][:80]})
    return state
