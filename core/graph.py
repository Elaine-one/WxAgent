import logging
import sys

from langgraph.graph import END, StateGraph

from core.deps import Deps, get_deps
from core.state import AgentState
from core.nodes.classify import classify_node
from core.nodes.react import react_node
from llm import create_llm
from llm.fallback import LLMFallback
from llm.router import ModelRouter
from tools.registry import ToolRegistry

import config as cfg

logger = logging.getLogger("wxagent.graph")


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
            logger.warning(
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
            logger.warning(
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
            pending = state.get("pending_confirmation", {})
            tool_call_id = pending.get("tool_call_id", "")
            if tool_call_id:
                state["messages"] = [{"role": "tool", "content": "用户已取消此操作", "tool_call_id": tool_call_id}]
            state["pending_confirmation"] = {}
            state["confirmation_response"] = ""
            state["final_response"] = "已取消操作。"
            state["task_complete"] = True
            return "respond"
        state["confirmation_response"] = ""
        return "resume_confirm"
    if msg_type == "meta":
        return "handle_meta"
    if msg_type == "interrupt":
        return "handle_interrupt"
    return "react"


def _after_react(state: AgentState) -> str:
    if state.get("pending_confirmation"):
        return "need_confirm"
    return "respond"


def wait_user_node(state: AgentState) -> AgentState:
    return state


def handle_meta_node(state: AgentState, config) -> AgentState:
    deps = get_deps(config)
    inp = state["user_input"].strip()
    inp_lower = inp.lower()

    if inp_lower.startswith("/help"):
        tool_list = "\n".join(f"  {t.name}: {t.description}" for t in deps.tools)
        state["final_response"] = (
            f"可用命令：\n"
            f"/help /status /tasks /usage /reset\n"
            f"/cal - 查看飞书日历\n"
            f"/doc <标题> - 创建飞书文档\n"
            f"/msg <内容> - 发送飞书消息\n"
            f"\n可用工具：\n{tool_list}"
        )
    elif inp_lower.startswith("/status"):
        state["final_response"] = f"会话正常 | 用户: {state['user_id']}"
    elif inp_lower.startswith("/tasks"):
        try:
            from tasks.manager import get_task_manager
            tm = get_task_manager()
            running = tm.list_running()
            if running:
                task_lines = [f"  [{t.status.value}] {t.task_type} ({t.task_id})" for t in running]
                state["final_response"] = f"正在执行的任务 ({len(running)}):\n" + "\n".join(task_lines)
            else:
                state["final_response"] = "没有正在执行的任务"
        except Exception:
            state["final_response"] = "没有正在执行的任务"
    elif inp_lower.startswith("/usage"):
        cost = state.get("cost", {})
        state["final_response"] = (
            f"LLM 使用统计\n"
            f"调用次数: {cost.get('llm_calls', 0)}\n"
            f"Token 消耗: {cost.get('total_tokens', 0):,}\n"
            f"估算费用: ${cost.get('estimated_usd', 0):.4f}"
        )
    elif inp_lower.startswith("/reset"):
        state["last_error"] = ""
        state["pending_confirmation"] = {}
        state["confirmation_response"] = ""
        state["task_complete"] = True
        state["final_response"] = "已重置会话状态"
    elif inp_lower.startswith("/cal"):
        state["user_input"] = "查看我的飞书日历"
        state["msg_type"] = "new_task"
        state["task_complete"] = False
        return state
    elif inp_lower.startswith("/doc"):
        title = inp[4:].strip() if len(inp) > 4 else "新建文档"
        state["user_input"] = f"在飞书创建一个文档，标题是：{title}"
        state["msg_type"] = "new_task"
        state["task_complete"] = False
        return state
    elif inp_lower.startswith("/msg"):
        content = inp[4:].strip() if len(inp) > 4 else ""
        if content:
            state["user_input"] = f"在飞书发送消息：{content}"
        else:
            state["user_input"] = "发送飞书消息"
        state["msg_type"] = "new_task"
        state["task_complete"] = False
        return state
    else:
        state["final_response"] = "未知命令。输入 /help 查看可用命令。"
    state["task_complete"] = True
    return state


def handle_interrupt_node(state: AgentState, config) -> AgentState:
    state["interrupted_message"] = state["user_input"]
    state["interrupted"] = True
    return state


def handle_confirm_node(state: AgentState, config) -> AgentState:
    deps = get_deps(config)
    real_session = deps.real_session(config)
    pending = state.get("pending_confirmation", {})
    confirm_type = pending.get("type", "confirm")
    tool_call_id = pending.get("tool_call_id", "")

    if confirm_type == "dangerous_command":
        command = pending.get("command", "")
        result = ToolRegistry.execute("run_shell", {"command": command, "_skip_risk_check": True}, real_session, state.get("user_id", ""))
        state["last_error"] = "" if result.success else result.error

        if result.success:
            result_text = result.content[:4000] if result.content else "命令执行成功"
        else:
            result_text = f"错误：{result.error or '执行失败'}"
        state["messages"] = [{"role": "tool", "content": result_text, "tool_call_id": tool_call_id}]
        logger.info("dangerous_command_confirmed", extra={"user_id": state.get("user_id", ""), "command": command[:200], "success": result.success})

    elif confirm_type == "pip_install":
        package_name = pending.get("package_name", "")
        try:
            import subprocess
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                capture_output=True, text=True, timeout=60,
            )
            state["last_error"] = ""
            install_result = f"包 {package_name} 安装成功" if proc.returncode == 0 else f"安装失败: {proc.stderr[:500]}"
            state["messages"] = [{"role": "tool", "content": install_result, "tool_call_id": tool_call_id}]
            logger.info("pip_install_confirmed", extra={"user_id": state.get("user_id", ""), "package": package_name, "success": proc.returncode == 0})
        except Exception as e:
            state["last_error"] = f"pip install 失败: {e}"
            state["messages"] = [{"role": "tool", "content": f"安装失败: {e}", "tool_call_id": tool_call_id}]
            logger.info("pip_install_failed", extra={"user_id": state.get("user_id", ""), "package": package_name, "error": str(e)[:200]})

    elif confirm_type == "skill_action":
        skill_name = pending.get("skill_name", "")
        tool_name = pending.get("tool_name", "")
        tool_args = pending.get("tool_args", {})
        pending_actions = pending.get("pending_actions", [])
        results = []
        if tool_name:
            result = ToolRegistry.execute(tool_name, tool_args, real_session, state.get("user_id", ""))
            status = "✓" if result.success else "✗"
            content = result.display or (result.content[:80] if result.content else "")
            results.append(f"{status} {tool_name}: {content}")
        for action in pending_actions:
            a_tool_name = action.get("tool")
            a_tool_args = action.get("args", {})
            if a_tool_name:
                result = ToolRegistry.execute(a_tool_name, a_tool_args, real_session, state.get("user_id", ""))
                status = "✓" if result.success else "✗"
                content = result.display or (result.content[:80] if result.content else "")
                results.append(f"{status} {a_tool_name}: {content}")
        result_text = f"Skill '{skill_name}' executed:\n" + "\n".join(results)
        state["messages"] = [{"role": "tool", "content": result_text[:4000], "tool_call_id": tool_call_id}]
        state["last_error"] = ""
        logger.info("skill_action_confirmed", extra={"user_id": state.get("user_id", ""), "skill": skill_name, "tool": tool_name})

    else:
        tool_name = pending.get("tool_name", "")
        tool_args = pending.get("tool_args", {})
        if tool_name:
            result = ToolRegistry.execute(tool_name, tool_args, real_session, state.get("user_id", ""))
            result_text = result.content if result.success else f"错误：{result.error or '未知错误'}"
            state["messages"] = [{"role": "tool", "content": result_text[:4000], "tool_call_id": tool_call_id}]
            state["last_error"] = "" if result.success else result.error

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

    deps = Deps(
        model=model,
        model_cache=model_cache,
        tools=tools_list,
        memory=memory_manager,
        session=session,
    )

    builder = StateGraph(AgentState)

    builder.add_node("classify", classify_node)
    builder.add_node("react", react_node)
    builder.add_node("handle_meta", handle_meta_node)
    builder.add_node("handle_interrupt", handle_interrupt_node)
    builder.add_node("handle_confirm", handle_confirm_node)
    builder.add_node("wait_user", wait_user_node)

    builder.set_entry_point("classify")

    builder.add_conditional_edges("classify", _after_classify, {
        "react": "react",
        "handle_meta": "handle_meta",
        "handle_interrupt": "handle_interrupt",
        "resume_confirm": "handle_confirm",
        "respond": END,
    })
    builder.add_edge("handle_meta", END)
    builder.add_edge("handle_interrupt", "react")
    builder.add_conditional_edges("react", _after_react, {
        "respond": END,
        "need_confirm": "wait_user",
    })
    builder.add_edge("wait_user", "handle_confirm")
    builder.add_edge("handle_confirm", "react")

    graph = builder.compile(checkpointer=checkpointer, interrupt_before=["wait_user"])
    graph._deps = deps
    return graph
