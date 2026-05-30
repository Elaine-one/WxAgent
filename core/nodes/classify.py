import json
import logging

from core.state import AgentState
from llm.base import BaseLLM
from tools.base import ToolDef

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """判断用户消息的类型，回复 JSON:
{{"type": "meta"|"confirm"|"new_task"|"interrupt"}}
- meta: 元命令（/reset、/help、/status、/tasks、/usage）
- confirm: 对确认请求的回复（Y/N/是/否/确认/取消等）
- interrupt: 当前有任务在执行，用户想打断/纠正/放弃
- new_task: 其他一切新请求
当前是否有正在执行的任务: {has_active_task}
用户消息: {user_input}"""


def classify_node(state: AgentState, *, model: BaseLLM,
                  session, tools: list[ToolDef], memory=None) -> AgentState:
    has_active = bool(state.get("plan") and not state.get("task_complete"))
    prompt = CLASSIFY_PROMPT.format(
        has_active_task=has_active,
        user_input=state["user_input"],
    )
    resp = model.chat([{"role": "user", "content": prompt}])
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
