import json
import logging

from core.state import AgentState
from llm.base import BaseLLM
from tools.base import ToolDef

logger = logging.getLogger(__name__)

FIX_PROMPT = """工具执行失败，分析错误并给出修正方案。

工具: {tool_name}
参数: {args}
错误: {error}
重试: {retry_count}/3

可用工具列表：
{tool_list}

回复 JSON:
{{"analysis": "原因", "action": "fix_args"|"pip_install"|"give_up",
  "new_args": {{}} 或 null, "package_name": "包名" 或 null,
  "give_up_reason": "放弃原因" 或 null}}"""


def self_heal_node(state: AgentState, *, model: BaseLLM,
                   session, tools: list[ToolDef], memory=None) -> AgentState:
    step_idx = state["current_step"]
    step = state["plan"][step_idx]
    current_retries = state["retry_counts"].get(step_idx, 0)
    tool_lines = [f"- {t.name}: {t.description}" for t in tools]

    prompt = FIX_PROMPT.format(
        tool_name=step["tool"],
        args=json.dumps(step.get("args", {}), ensure_ascii=False),
        error=state["last_error"],
        retry_count=current_retries + 1,
        tool_list="\n".join(tool_lines),
    )
    resp = model.chat([{"role": "user", "content": prompt}])
    try:
        fix = json.loads(resp.text)
    except (json.JSONDecodeError, KeyError):
        fix = {"action": "give_up", "give_up_reason": "无法解析 LLM 修复方案"}

    action = fix.get("action", "give_up")

    if action == "fix_args" and fix.get("new_args"):
        step["args"] = fix["new_args"]
        logger.info("self_heal_fix_args", extra={"step": step_idx, "tool": step["tool"]})
    elif action == "pip_install" and fix.get("package_name"):
        state["pending_confirmation"] = {
            "type": "pip_install",
            "detail": f"需要安装 Python 包: {fix['package_name']}",
            "step_index": step_idx,
            "tool_name": step["tool"],
            "package_name": fix["package_name"],
        }
        logger.info("self_heal_pip_install", extra={"step": step_idx, "package": fix["package_name"]})
    elif action == "give_up":
        step["status"] = "failed"
        state["last_error"] = fix.get("give_up_reason", "自愈放弃")
        logger.info("self_heal_give_up", extra={"step": step_idx, "reason": state["last_error"][:200]})

    state["retry_counts"][step_idx] = current_retries + 1
    return state
