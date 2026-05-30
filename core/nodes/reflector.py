import json
import logging

from core.state import AgentState
from observability.metrics import record_llm_call
from tools.base import ToolDef

logger = logging.getLogger(__name__)

REFLECTOR_PROMPT = """评估任务执行状态，决定下一步。

用户原始请求: {user_input}

执行计划:
{plan_summary}

当前进度: 步骤 {current_step}/{total_steps}
上一步结果: {last_result}

回复 JSON:
{{"decision": "all_done"|"next_step"|"replan", "reason": "判断理由"}}
- all_done: 用户意图已满足，可以回复
- next_step: 当前步骤完成，继续下一步
- replan: 需要调整后续步骤（如某步失败需改变策略）"""


def reflector_node(state: AgentState, *, session, tools: list[ToolDef],
                   memory=None, default_model=None, model_cache=None) -> AgentState:
    plan_lines = []
    icon_map = {"done": "✅", "failed": "❌", "running": "🔄", "pending": "⬜", "skipped": "⏭️"}
    for s in state["plan"]:
        icon = icon_map.get(s["status"], "?")
        plan_lines.append(f"  {icon} 步骤{s['step']}: {s['description']} [{s['status']}]")

    last_step = state["plan"][state["current_step"]] if state["plan"] else {"status": "done", "description": "无"}

    prompt = REFLECTOR_PROMPT.format(
        user_input=state.get("user_input", ""),
        plan_summary="\n".join(plan_lines),
        current_step=state["current_step"],
        total_steps=len(state["plan"]),
        last_result=f"{last_step['status']}: {last_step['description']}",
    )
    model = default_model
    if model_cache and "planning" in model_cache:
        model = model_cache["planning"]
    resp = model.chat([{"role": "user", "content": prompt}])

    input_tokens = resp.extra_fields.get("usage", {}).get("prompt_tokens", 0)
    output_tokens = resp.extra_fields.get("usage", {}).get("completion_tokens", 0)
    model_name = getattr(model, 'primary', model).__class__.__name__ if hasattr(model, 'primary') else ""
    record_llm_call(model_name, input_tokens, output_tokens, state)

    try:
        data = json.loads(resp.text)
        decision = data.get("decision", "all_done")
    except (json.JSONDecodeError, KeyError):
        decision = "all_done"

    if decision not in ("all_done", "next_step", "replan"):
        decision = "all_done"

    state["_reflector_decision"] = decision

    if decision == "next_step":
        state["current_step"] += 1
    elif decision == "all_done":
        state["task_complete"] = True

    logger.info("reflector_decision", extra={"decision": decision, "current_step": state["current_step"]})
    return state
