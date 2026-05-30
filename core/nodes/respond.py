import logging

import config
from core.state import AgentState
from llm.base import BaseLLM
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


async def respond_with_progress(stream, sender, session_id):
    import asyncio
    import time
    last_send = time.time()
    buffer = ""
    async for chunk in stream:
        buffer += chunk
        if time.time() - last_send >= PROGRESS_INTERVAL_SECONDS:
            sender.send_text(session_id, "⏳ 正在生成回复...")
            last_send = time.time()
    return buffer


def respond_node(state: AgentState, *, model: BaseLLM,
                 session, tools: list[ToolDef], memory=None) -> AgentState:
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
    messages = [
        {"role": "system", "content": config.SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    resp = model.chat(messages)
    state["final_response"] = resp.text
    state["task_complete"] = True
    logger.info("respond_generated", extra={"response_len": len(resp.text)})
    return state
