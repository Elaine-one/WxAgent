import concurrent.futures
import logging

from core.state import AgentState
from observability.metrics import record_llm_call
from security.ai_reviewer import AISafetyReviewer, Verdict
from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_AI_REVIEW_TIMEOUT = 10


def _find_parallel_groups(steps: list[dict]) -> list[list[dict]]:
    groups = []
    done = set()
    pending = list(steps)

    while pending:
        batch = []
        leftover = []
        for s in pending:
            deps = s.get("depends_on", [])
            if all(d in done for d in deps):
                batch.append(s)
            else:
                leftover.append(s)

        if not batch:
            for s in leftover:
                groups.append([s])
            break

        groups.append(batch)
        done.update(s.get("step", i) for i, s in enumerate(batch))
        pending = leftover

    return groups


def _execute_parallel_group(steps: list[dict], state, user_id: str) -> list[dict]:
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(steps)) as pool:
        futures = {
            pool.submit(
                ToolRegistry.execute, s["tool"], s.get("args", {}),
                state, user_id,
            ): s for s in steps
        }
        for future in concurrent.futures.as_completed(futures):
            step = futures[future]
            try:
                result = future.result()
                results.append({"step": step, "result": result})
            except Exception as e:
                results.append({
                    "step": step,
                    "result": ToolResult(success=False, error=str(e)),
                })
    return results


def executor_node(state: AgentState, *, session, tools: list[ToolDef],
                  memory=None, default_model=None, model_cache=None) -> AgentState:
    step_idx = state["current_step"]
    if step_idx >= len(state["plan"]):
        logger.info("executor_skip", extra={"reason": "step_out_of_range"})
        return state

    remaining = state["plan"][step_idx:]
    if len(remaining) > 1:
        all_pending = all(
            s.get("status", "pending") in ("pending", None) and not s.get("depends_on", [])
            for s in remaining[1:min(len(remaining), 4)]
        )
        if all_pending:
            groups = _find_parallel_groups(remaining)
            if len(groups[0]) > 1:
                logger.info("parallel_execution", extra={"steps": len(groups[0])})
                group_results = _execute_parallel_group(groups[0], session, state["user_id"])
                for item in group_results:
                    s = item["step"]
                    r = item["result"]
                    s["status"] = "done" if r.success else "failed"
                    if r.success and memory and r.content:
                        try:
                            memory.store_fact(
                                state["user_id"],
                                f"tool:{s['tool']}:{s['description'][:50]}",
                                r.content[:500],
                            )
                        except Exception:
                            pass
                    if not r.success:
                        state["last_error"] = r.error or "并行执行失败"
                state["current_step"] += len(groups[0])
                return state

    step = state["plan"][step_idx]
    step["status"] = "running"
    logger.info("executor_start", extra={"step": step_idx, "tool": step["tool"]})

    if step["tool"] in ("run_shell", "system_action", "kill_process"):
        ai_reviewer_cfg = {}
        try:
            import yaml
            with open(config.PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
                ai_reviewer_cfg = yaml.safe_load(f).get("ai_reviewer", {})
        except Exception:
            pass
        reviewer = AISafetyReviewer(default_model, ai_reviewer_cfg)
        command = step["args"].get("command", "") or str(step["args"])
        intent = state.get("user_input", "")
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    reviewer.review, command,
                    user_intent=intent, risk_level="caution",
                )
                review_result = future.result(timeout=_AI_REVIEW_TIMEOUT)
        except concurrent.futures.TimeoutError:
            logger.warning("AI 审查超时，默认放行: %s", command[:100])
            review_result = None
        except Exception as e:
            logger.warning("AI 审查异常，默认放行: %s", e)
            review_result = None

        if review_result is not None:
            if review_result.verdict == Verdict.DENY:
                step["status"] = "failed"
                state["last_error"] = f"AI 安全审查拒绝: {review_result.reason}"
                return state
            elif review_result.verdict == Verdict.ASK_USER:
                state["pending_confirmation"] = {
                    "type": "ai_review",
                    "detail": f"AI 审查无法确定此操作的安全性: {review_result.reason}",
                    "step_index": step_idx,
                    "tool_name": step["tool"],
                }
                return state

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
        if memory and result.content:
            try:
                memory.store_fact(
                    state["user_id"],
                    f"tool:{step['tool']}:{step['description'][:50]}",
                    result.content[:500],
                )
            except Exception:
                pass
        logger.info("executor_success", extra={"step": step_idx, "tool": step["tool"]})
    else:
        step["status"] = "failed"
        state["last_error"] = result.error or "未知错误"
        state["pending_confirmation"] = {}
        logger.info("executor_failed", extra={"step": step_idx, "tool": step["tool"], "error": state["last_error"][:200]})

    return state
