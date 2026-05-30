import logging
import time

import config
from channel.client import InboundMessage, SessionState
from channel.sender import send_message
from core.state import AgentState
from llm.streaming import split_for_wechat

logger = logging.getLogger(__name__)


class Dispatcher:

    def __init__(self, graph, session: SessionState):
        self.graph = graph
        self.session = session
        self._sessions: dict[str, dict] = {}

    def handle_message(self, msg: InboundMessage) -> None:
        uid = msg.from_user_id
        configurable = {"configurable": {"thread_id": uid}}

        try:
            snapshot = self.graph.get_state(configurable)
        except Exception:
            snapshot = None

        if snapshot and snapshot.next:
            pending_node = snapshot.next[0] if snapshot.next else ""
            if pending_node == "wait_user":
                state_update = {
                    "user_input": msg.text,
                    "confirmation_response": msg.text,
                }
                self.graph.update_state(configurable, state_update, as_node="wait_user")
                logger.info("interrupt_resume", extra={"uid": uid, "user_input": msg.text[:80]})
                result = self.graph.invoke(None, configurable)
            else:
                if uid not in self._sessions:
                    self._sessions[uid] = self._new_state(uid)
                state = self._sessions[uid]
                state["user_input"] = msg.text
                result = self.graph.invoke(state, configurable)
        else:
            if uid in self._sessions:
                state = self._sessions[uid]
                if state.get("task_complete"):
                    state = self._new_state(uid)
                    self._sessions[uid] = state
            else:
                self._sessions[uid] = self._new_state(uid)
                state = self._sessions[uid]
            state["user_input"] = msg.text
            state["interrupted"] = bool(state.get("plan") and not state.get("task_complete"))
            logger.info("new_invocation", extra={"uid": uid, "user_input": msg.text[:80]})
            result = self.graph.invoke(state, configurable)

        if result is not None:
            self._sessions[uid] = result

        if result and result.get("final_response"):
            self._send_bubbles(uid, result["final_response"])
        elif result and result.get("pending_confirmation") and not result.get("task_complete"):
            detail = result["pending_confirmation"]
            confirm_text = self._format_confirmation(detail)
            send_message(self.session, uid, confirm_text)

    def _format_confirmation(self, detail: dict) -> str:
        confirm_type = detail.get("type", "confirm")
        if confirm_type == "dangerous_command":
            targets = detail.get("affected_targets", [])
            target_str = "\n".join(f"  - {t}" for t in targets[:5])
            return (
                f"⚠ 即将执行危险操作\n"
                f"原因: {detail.get('reason', '未知')}\n"
                f"命令: {detail.get('command', '')[:200]}\n"
                f"影响目标:\n{target_str}\n\n"
                f"确认执行请回复 Y，取消回复 N"
            )
        elif confirm_type == "cloud_consent":
            return f"☁ {detail.get('message', '此操作会将数据发送到云端服务，是否继续？')}\n确认请回复 Y，取消回复 N"
        elif confirm_type == "pip_install":
            return f"即将安装 Python 包: {detail.get('package_name', '')}\n确认请回复 Y，取消回复 N"
        else:
            return f"即将执行：{detail.get('detail', '未知操作')}\n确认请回复 Y，取消回复 N"

    def _send_bubbles(self, uid: str, text: str) -> None:
        segments = split_for_wechat(text)
        for seg in segments:
            send_message(self.session, uid, seg)
            time.sleep(0.3)

    def _new_state(self, uid: str) -> dict:
        return {
            "user_id": uid,
            "task_id": "",
            "messages": [{"role": "system", "content": config.SYSTEM_PROMPT}],
            "user_input": "",
            "plan": [],
            "current_step": 0,
            "retry_counts": {},
            "last_error": "",
            "pending_confirmation": {},
            "confirmation_response": "",
            "interrupted": False,
            "interrupted_message": "",
            "msg_type": "",
            "_reflector_decision": "",
            "final_response": "",
            "task_complete": False,
            "messages_window": 50,
            "user_preferences": {},
            "active_tools": [],
            "cost": {"llm_calls": 0, "total_tokens": 0, "estimated_usd": 0.0},
        }
