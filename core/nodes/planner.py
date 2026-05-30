import json
import logging
import time

import config
from core.state import AgentState, PlanStep
from llm.base import BaseLLM
from tools.base import ToolDef

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """你是个人电脑 AI 助手。用户通过微信与你对话。根据用户请求，制定分步执行计划。

可用工具：
{tool_list}

用户请求: {user_input}

回复 JSON 格式：
{{"plan": [{{"step": 0, "description": "步骤描述", "tool": "工具名", "args": {{}}}}]}}

规则：
- 简单闲聊/问答 → 空 plan []
- 单步操作 → 1 个 step
- 多步任务 → 按依赖顺序列出，最多 {max_steps} 步
- 每个 step 的 tool 必须是可用工具之一
- 不要规划危险操作（删除文件、修改系统设置等）
- 需要用户确认的操作，在 description 中说明"""


def planner_node(state: AgentState, *, model: BaseLLM,
                 session, tools: list[ToolDef], memory=None) -> AgentState:
    tool_lines = [f"- {t.name}: {t.description}" for t in tools]
    prompt = PLANNER_PROMPT.format(
        tool_list="\n".join(tool_lines),
        user_input=state["user_input"],
        max_steps=config.MAX_TOOL_ROUNDS,
    )
    resp = model.chat([
        {"role": "system", "content": config.SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    try:
        data = json.loads(resp.text)
        plan_data = data.get("plan", [])
        state["plan"] = [PlanStep(**s) for s in plan_data]
    except (json.JSONDecodeError, KeyError, TypeError):
        state["plan"] = []
    state["current_step"] = 0
    state["retry_counts"] = {}
    state["task_id"] = f"task_{int(time.time())}"
    logger.info("plan_generated", extra={"steps": len(state["plan"]), "task_id": state["task_id"]})
    return state
