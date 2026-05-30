import logging
import threading
import time

import config
from channel.sender import send_message
from core.state import AgentState
from observability.metrics import record_llm_call
from tools.base import ToolDef

logger = logging.getLogger(__name__)

MOBILE_ADAPTATION_RULE = """
[移动端适配规则]
- 数据行数 > 10 行时，优先调用 run_python 生成图表（matplotlib）而非输出原始表格
- 长文本分段发送，每段 ≤ 480 字符
- 文件路径使用相对路径，避免绝对路径占屏
- 列表项 ≤ 8 个，超出则摘要
"""

RESPOND_PROMPT = """你是个人电脑 AI 助手，通过微信与用户对话。请基于以下信息生成自然回复。

用户原始请求: {user_input}
任务完成状态: {task_complete}
执行结果:
{plan_summary}
{error_context}

规则：
- 用中文回复，简洁自然，像朋友聊天
- 成功时总结成果，列出关键信息
- 失败时诚实说明原因，给出替代建议
- 不要生成 URL 或 Markdown 表格
- 控制在 1500 字以内
{mobile_rules}"""

PROGRESS_INTERVAL_SECONDS = 5


def _send_progress(session, user_id: str, stop: threading.Event):
    time.sleep(5)
    if stop.is_set():
        return
    try:
        send_message(session, user_id, "⏳ 正在生成回复...")
    except Exception:
        pass


def respond_node(state: AgentState, *, session, tools: list[ToolDef],
                 memory=None, default_model=None, model_cache=None) -> AgentState:
    model = default_model
    if model_cache and "text" in model_cache:
        model = model_cache["text"]

    icon_map = {"done": "✅", "failed": "❌", "pending": "⬜", "skipped": "⏭️"}
    plan_lines = []
    for s in state["plan"]:
        icon = icon_map.get(s["status"], "?")
        plan_lines.append(f"  {icon} {s['description']}")

    error_context = ""
    if state.get("last_error"):
        error_context = f"\n最近错误: {state['last_error']}"

    prompt = RESPOND_PROMPT.format(
        user_input=state.get("user_input", ""),
        task_complete=state.get("task_complete", True),
        plan_summary="\n".join(plan_lines) if plan_lines else "（直接回复，未使用工具）",
        error_context=error_context,
        mobile_rules=MOBILE_ADAPTATION_RULE,
    )

    context = ""
    if memory:
        try:
            context = memory.build_context_prompt(state.get("user_id", ""), state.get("user_input", ""))
        except Exception:
            pass

    full_prompt = f"[用户上下文]\n{context}\n\n{prompt}" if context else prompt

    messages = [
        {"role": "system", "content": config.SYSTEM_PROMPT},
        {"role": "user", "content": full_prompt},
    ]

    stop_progress = threading.Event()
    progress_thread = None
    if session:
        progress_thread = threading.Thread(
            target=_send_progress,
            args=(session, state["user_id"], stop_progress),
            daemon=True,
        )
        progress_thread.start()

    try:
        resp = model.chat(messages)
    finally:
        stop_progress.set()
        if progress_thread:
            progress_thread.join(timeout=1)

    input_tokens = resp.extra_fields.get("usage", {}).get("prompt_tokens", 0)
    output_tokens = resp.extra_fields.get("usage", {}).get("completion_tokens", 0)
    model_name = getattr(model, 'primary', model).__class__.__name__ if hasattr(model, 'primary') else ""
    record_llm_call(model_name, input_tokens, output_tokens, state)

    state["final_response"] = resp.text
    state["task_complete"] = True
    logger.info("respond_generated", extra={"response_len": len(resp.text)})

    if memory:
        try:
            memory.store_conversation(
                state["user_id"],
                [{"role": "user", "content": state["user_input"]},
                 {"role": "assistant", "content": resp.text}],
            )
            memory.learn_from_interaction(
                state["user_id"],
                state["user_input"],
                resp.text,
            )
        except Exception:
            pass

    return state
