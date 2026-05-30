import json
import logging

from core.state import AgentState
from observability.metrics import record_llm_call
from tools.base import ToolDef

logger = logging.getLogger(__name__)

FIX_PROMPT = """工具执行失败，分析错误并给出修正方案。

工具: {tool_name}
参数: {args}
错误: {error}
重试: {retry_count}/3

可用工具列表：
{tool_list}

修正策略参考（不限于此）:
- 文件路径错误 → 用 search_files 搜索定位 → 重试
- 依赖缺失 → 请求安装依赖 → 重试
- 权限不足 → 尝试替代方案 → 提示用户
- 参数错误 → 分析错误信息 → 修正参数
- 资源被占用 → 释放资源或等待 → 重试
- 网络超时 → 减小请求范围或重试
- 编码/格式问题 → 尝试不同编码或格式

回复 JSON:
{{"analysis": "原因", "action": "fix_args"|"pip_install"|"give_up",
  "new_args": {{}} 或 null, "package_name": "包名" 或 null,
  "give_up_reason": "放弃原因" 或 null}}"""


def self_heal_node(state: AgentState, *, session, tools: list[ToolDef],
                   memory=None, default_model=None, model_cache=None) -> AgentState:
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
    model = default_model
    if model_cache and "code_execution" in model_cache:
        model = model_cache["code_execution"]
    resp = model.chat([{"role": "user", "content": prompt}])

    input_tokens = resp.extra_fields.get("usage", {}).get("prompt_tokens", 0)
    output_tokens = resp.extra_fields.get("usage", {}).get("completion_tokens", 0)
    model_name = getattr(model, 'primary', model).__class__.__name__ if hasattr(model, 'primary') else ""
    record_llm_call(model_name, input_tokens, output_tokens, state)

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
