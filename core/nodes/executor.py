import logging

from core.state import AgentState
from llm.base import BaseLLM
from tools.base import ToolDef
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def executor_node(state: AgentState, *, model: BaseLLM,
                  session, tools: list[ToolDef], memory=None) -> AgentState:
    step_idx = state["current_step"]
    if step_idx >= len(state["plan"]):
        logger.info("executor_skip", extra={"reason": "step_out_of_range"})
        return state

    step = state["plan"][step_idx]
    step["status"] = "running"
    logger.info("executor_start", extra={"step": step_idx, "tool": step["tool"]})

    result = ToolRegistry.execute(step["tool"], step["args"], session, state["user_id"])

    if result.success:
        step["status"] = "done"
        state["last_error"] = ""
        if result.requires_confirmation:
            state["pending_confirmation"] = result.confirmation_detail or {
                "type": "confirm",
                "detail": step["description"],
                "step_index": step_idx,
                "tool_name": step["tool"],
            }
        else:
            state["pending_confirmation"] = {}
        logger.info("executor_success", extra={"step": step_idx, "tool": step["tool"]})
    else:
        step["status"] = "failed"
        state["last_error"] = result.error or "未知错误"
        state["pending_confirmation"] = {}
        logger.info("executor_failed", extra={"step": step_idx, "tool": step["tool"], "error": state["last_error"][:200]})

    return state
