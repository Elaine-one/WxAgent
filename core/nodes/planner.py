import json
import logging
import time

import config
from core.state import AgentState, PlanStep
from observability.metrics import record_llm_call
from tools.base import ToolDef

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """你是个人电脑 AI 助手。用户通过微信与你对话。根据用户请求，制定分步执行计划。

可用工具：
{tool_list}

用户请求: {user_input}

回复 JSON 格式：
{{"plan": [{{"step": 0, "description": "步骤描述", "tool": "工具名", "args": {{}}, "depends_on": []}}]}}

规则：
- 简单闲聊/问答 → 空 plan []
- 单步操作 → 1 个 step
- 多步任务 → 按依赖顺序列出，最多 {max_steps} 步
- 每个 step 的 tool 必须是可用工具之一
- 不要规划危险操作（删除文件、修改系统设置等）
- 需要用户确认的操作，在 description 中说明
- depends_on: 依赖的前置 step 编号列表，空数组=无依赖可并行"""


def planner_node(state: AgentState, *, session, tools: list[ToolDef],
                 memory=None, default_model=None, model_cache=None) -> AgentState:
    model = default_model
    if model_cache and "planning" in model_cache:
        model = model_cache["planning"]

    tool_lines = [f"- {t.name}: {t.description}" for t in tools]
    prompt = PLANNER_PROMPT.format(
        tool_list="\n".join(tool_lines),
        user_input=state["user_input"],
        max_steps=config.MAX_TOOL_ROUNDS,
    )

    context = ""
    if memory:
        try:
            context = memory.build_context_prompt(state.get("user_id", ""), state["user_input"])
        except Exception:
            pass

    full_prompt = f"[用户上下文]\n{context}\n\n{prompt}" if context else prompt

    if state.get("image_description"):
        full_prompt += f"\n\n[图片内容识别结果]\n{state['image_description']}"

    resp = model.chat([
        {"role": "system", "content": config.SYSTEM_PROMPT},
        {"role": "user", "content": full_prompt},
    ])

    input_tokens = resp.extra_fields.get("usage", {}).get("prompt_tokens", 0)
    output_tokens = resp.extra_fields.get("usage", {}).get("completion_tokens", 0)
    model_name = getattr(model, 'primary', model).__class__.__name__ if hasattr(model, 'primary') else ""
    record_llm_call(model_name, input_tokens, output_tokens, state)

    try:
        data = json.loads(resp.text)
        plan_data = data.get("plan", [])
        for s in plan_data:
            s.setdefault("depends_on", [])
        state["plan"] = [PlanStep(**s) for s in plan_data]
    except (json.JSONDecodeError, KeyError, TypeError):
        state["plan"] = []
    state["current_step"] = 0
    state["retry_counts"] = {}
    state["task_id"] = f"task_{int(time.time())}"
    logger.info("plan_generated", extra={"steps": len(state["plan"]), "task_id": state["task_id"]})
    return state
