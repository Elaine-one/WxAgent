import logging
import sys
from functools import partial

from langgraph.graph import END, StateGraph

from core.state import AgentState
from core.nodes.classify import classify_node
from core.nodes.planner import planner_node
from core.nodes.executor import executor_node
from core.nodes.self_heal import self_heal_node
from core.nodes.reflector import reflector_node
from core.nodes.respond import respond_node
from llm import create_llm
from llm.fallback import LLMFallback
from llm.router import ModelRouter
from tools.registry import ToolRegistry

import config as cfg

logger = logging.getLogger(__name__)


def _build_model_cache(model, tools_list) -> dict:
    cache = {"default": model}
    router = ModelRouter()

    for task_type, route in router.config.get("task_overrides", {}).items():
        try:
            cache[task_type] = create_llm(
                route.get("provider", cfg.LLM_PROVIDER),
                route.get("api_key", cfg.LLM_API_KEY),
                route.get("base_url", cfg.LLM_BASE_URL),
                route.get("model", cfg.LLM_MODEL),
                tools_list,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "model_cache task '%s' 跳过: %s", task_type, e
            )

    for modality, route in router.config.get("routes", {}).items():
        try:
            if modality == "vision":
                api_key = cfg.VISION_API_KEY
                base_url = cfg.VISION_BASE_URL or route.get("base_url", cfg.LLM_BASE_URL)
                model_name = cfg.VISION_MODEL or route.get("model", cfg.LLM_MODEL)
            else:
                api_key = route.get("api_key", cfg.LLM_API_KEY)
                base_url = route.get("base_url", cfg.LLM_BASE_URL)
                model_name = route.get("model", cfg.LLM_MODEL)
            cache[modality] = create_llm(
                route.get("provider", cfg.LLM_PROVIDER),
                api_key,
                base_url,
                model_name,
                tools_list,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "model_cache route '%s' 跳过: %s", modality, e
            )

    if cfg.LLM_FALLBACK_API_KEY and cfg.LLM_FALLBACK_MODEL:
        try:
            fallback_llm = create_llm(
                cfg.LLM_PROVIDER,
                cfg.LLM_FALLBACK_API_KEY,
                cfg.LLM_FALLBACK_BASE_URL or cfg.LLM_BASE_URL,
                cfg.LLM_FALLBACK_MODEL,
                tools_list,
            )
            for key in list(cache.keys()):
                if key != "default":
                    cache[key] = LLMFallback(cache[key], fallback_llm)
            cache["default"] = LLMFallback(cache["default"], fallback_llm)
        except Exception:
            pass

    return cache


def _after_classify(state: AgentState) -> str:
    msg_type = state.get("msg_type", "new_task")
    if msg_type == "confirm":
        resp = state.get("confirmation_response", "").strip().upper()
        if resp in ("N", "否", "取消", "NO", "CANCEL"):
            step_idx = state["current_step"]
            if step_idx < len(state["plan"]):
                state["plan"][step_idx]["status"] = "skipped"
            state["pending_confirmation"] = {}
            state["confirmation_response"] = ""
            return "reflector"
        state["confirmation_response"] = ""
        return "resume_confirm"
    if msg_type == "meta":
        return "handle_meta"
    if msg_type == "interrupt":
        return "handle_interrupt"
    return "planner"


def _after_executor(state: AgentState) -> str:
    step_idx = state["current_step"]
    step = state["plan"][step_idx] if step_idx < len(state["plan"]) else None
    if step and step["status"] == "failed":
        return "self_heal"
    if step and state.get("pending_confirmation"):
        return "need_confirm"
    return "reflector"


def _after_self_heal(state: AgentState) -> str:
    step_idx = state["current_step"]
    if state["retry_counts"].get(step_idx, 0) >= 3:
        return "max_retries"
    step = state["plan"][step_idx] if step_idx < len(state["plan"]) else None
    if step and step["status"] == "failed":
        return "max_retries"
    if state.get("pending_confirmation", {}).get("type") == "pip_install":
        return "need_confirm"
    return "retry"


def _after_reflector(state: AgentState) -> str:
    decision = state.get("_reflector_decision", "all_done")
    if decision == "all_done":
        return "respond"
    if decision == "next_step":
        step_idx = state["current_step"]
        return "executor" if step_idx < len(state["plan"]) else "respond"
    return "planner"


def wait_user_node(state: AgentState) -> AgentState:
    return state


def handle_meta_node(state: AgentState, *, session, tools, memory=None,
                     default_model=None, model_cache=None) -> AgentState:
    inp = state["user_input"].strip().lower()
    if inp.startswith("/help"):
        tool_list = "\n".join(f"  {t.name}: {t.description}" for t in tools)
        state["final_response"] = f"可用命令：\n/help /status /tasks /usage /reset\n\n可用工具：\n{tool_list}"
    elif inp.startswith("/status"):
        state["final_response"] = f"会话正常 | 用户: {state['user_id']}"
    elif inp.startswith("/tasks"):
        if state["plan"]:
            lines = [f"  {s['status']} 步骤{s['step']}: {s['description']}" for s in state["plan"]]
            state["final_response"] = "当前任务:\n" + "\n".join(lines)
        else:
            state["final_response"] = "没有正在执行的任务"
    elif inp.startswith("/usage"):
        cost = state.get("cost", {})
        state["final_response"] = (
            f"LLM 使用统计\n"
            f"调用次数: {cost.get('llm_calls', 0)}\n"
            f"Token 消耗: {cost.get('total_tokens', 0):,}\n"
            f"估算费用: ${cost.get('estimated_usd', 0):.4f}"
        )
    elif inp.startswith("/reset"):
        state["plan"] = []
        state["current_step"] = 0
        state["retry_counts"] = {}
        state["last_error"] = ""
        state["pending_confirmation"] = {}
        state["confirmation_response"] = ""
        state["task_complete"] = True
        state["final_response"] = "已重置会话状态"
    else:
        state["final_response"] = "未知命令。输入 /help 查看可用命令。"
    state["task_complete"] = True
    return state


def handle_interrupt_node(state: AgentState, *, session, tools, memory=None,
                          default_model=None, model_cache=None) -> AgentState:
    state["interrupted_message"] = state["user_input"]
    state["interrupted"] = True
    return state


def handle_confirm_node(state: AgentState, *, session, tools, memory=None,
                        default_model=None, model_cache=None) -> AgentState:
    pending = state.get("pending_confirmation", {})
    confirm_type = pending.get("type", "confirm")

    if confirm_type == "pip_install":
        package_name = pending.get("package_name", "")
        try:
            import subprocess
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                capture_output=True, text=True, timeout=60,
            )
            step_idx = state["current_step"]
            if step_idx < len(state["plan"]):
                state["plan"][step_idx]["status"] = "pending"
            state["last_error"] = ""
            logger.info("pip_install_confirmed", extra={"package": package_name})
        except Exception as e:
            state["last_error"] = f"pip install 失败: {e}"
            logger.info("pip_install_failed", extra={"package": package_name, "error": str(e)[:200]})

    elif confirm_type == "dangerous_command":
        command = pending.get("command", "")
        result = ToolRegistry.execute("run_shell", {"command": command}, session, state.get("user_id", ""))
        step_idx = state["current_step"]
        if step_idx < len(state["plan"]):
            state["plan"][step_idx]["status"] = "done" if result.success else "failed"
        state["last_error"] = "" if result.success else result.error
        logger.info("dangerous_command_confirmed", extra={"command": command[:200]})

    elif confirm_type == "cloud_consent":
        from security.data_border import get_consent_db
        consent_db = get_consent_db()
        consent_db.record_consent(state.get("user_id", ""), "DuckDuckGo 搜索引擎", True)
        logger.info("cloud_consent_confirmed", extra={"user_id": state.get("user_id", "")})

    state["pending_confirmation"] = {}
    state["confirmation_response"] = ""
    return state


def build_agent_graph(model, session, tools_list, memory_manager=None, checkpointer=None):
    if checkpointer is None:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            from config import WORKSPACE_DIR
            db_path = WORKSPACE_DIR / "data" / "checkpoints.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            checkpointer = SqliteSaver.from_conn_string(str(db_path))
        except ImportError:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()

    model_cache = _build_model_cache(model, tools_list)

    builder = StateGraph(AgentState)

    deps = {
        "session": session,
        "tools": tools_list,
        "memory": memory_manager,
        "default_model": model,
        "model_cache": model_cache,
    }
    builder.add_node("classify", partial(classify_node, **deps))
    builder.add_node("planner", partial(planner_node, **deps))
    builder.add_node("executor", partial(executor_node, **deps))
    builder.add_node("self_heal", partial(self_heal_node, **deps))
    builder.add_node("reflector", partial(reflector_node, **deps))
    builder.add_node("respond", partial(respond_node, **deps))
    builder.add_node("handle_meta", partial(handle_meta_node, **deps))
    builder.add_node("handle_interrupt", partial(handle_interrupt_node, **deps))
    builder.add_node("handle_confirm", partial(handle_confirm_node, **deps))
    builder.add_node("wait_user", wait_user_node)

    builder.set_entry_point("classify")

    builder.add_conditional_edges("classify", _after_classify, {
        "planner": "planner",
        "handle_meta": "handle_meta",
        "handle_interrupt": "planner",
        "resume_confirm": "handle_confirm",
        "reflector": "reflector",
    })
    builder.add_edge("handle_meta", END)
    builder.add_edge("planner", "executor")
    builder.add_conditional_edges("executor", _after_executor, {
        "reflector": "reflector",
        "self_heal": "self_heal",
        "need_confirm": "wait_user",
    })
    builder.add_conditional_edges("self_heal", _after_self_heal, {
        "retry": "executor",
        "max_retries": "respond",
        "need_confirm": "wait_user",
    })
    builder.add_edge("wait_user", "handle_confirm")
    builder.add_edge("handle_confirm", "executor")
    builder.add_conditional_edges("reflector", _after_reflector, {
        "respond": "respond",
        "executor": "executor",
        "planner": "planner",
    })
    builder.add_edge("respond", END)

    return builder.compile(checkpointer=checkpointer, interrupt_before=["wait_user"])
