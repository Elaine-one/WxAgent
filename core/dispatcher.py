import logging
import time
from collections import OrderedDict

import config
from channel.client import InboundMessage, SessionState
from channel.sender import send_message
from core.state import AgentState
from llm.streaming import split_for_wechat

logger = logging.getLogger(__name__)


class Dispatcher:
    MAX_SESSIONS = 100
    SESSION_TTL_SECONDS = 3600 * 24

    def __init__(self, graph, session: SessionState, memory=None):
        self.graph = graph
        self.session = session
        self.memory = memory
        self._sessions: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._setup_task_callback()

    def _get_or_create_state(self, uid: str) -> dict:
        now = time.time()
        if uid in self._sessions:
            ts, state = self._sessions.pop(uid)
            self._sessions[uid] = (now, state)
            return state
        expired = [
            k for k, (ts, _) in self._sessions.items()
            if now - ts > self.SESSION_TTL_SECONDS
        ]
        for k in expired:
            del self._sessions[k]
        while len(self._sessions) >= self.MAX_SESSIONS:
            self._sessions.popitem(last=False)
        state = self._new_state(uid)
        self._sessions[uid] = (now, state)
        return state

    def _save_state(self, uid: str, state: dict) -> None:
        now = time.time()
        self._sessions[uid] = (now, state)

    def handle_message(self, msg: InboundMessage) -> None:
        uid = msg.from_user_id
        configurable = {"configurable": {"thread_id": uid}}

        image_urls = []
        image_media_refs = []
        if msg.msg_type == "image":
            if msg.image_url:
                image_urls = [msg.image_url]
            if msg.image_media_ref:
                image_media_refs = [msg.image_media_ref]
            if not image_urls and image_media_refs:
                logger.info("image_no_url_but_has_media_ref, will download via media_ref")

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
                state = self._get_or_create_state(uid)
                state["user_input"] = msg.text
                state["msg_type"] = msg.msg_type
                state["image_urls"] = image_urls
                state["image_media_refs"] = image_media_refs
                result = self.graph.invoke(state, configurable)
        else:
            state = self._get_or_create_state(uid)
            if state.get("task_complete"):
                state = self._new_state(uid)
            state["user_input"] = msg.text
            state["msg_type"] = msg.msg_type
            state["image_urls"] = image_urls
            state["image_media_refs"] = image_media_refs
            state["interrupted"] = bool(state.get("plan") and not state.get("task_complete"))
            logger.info("new_invocation", extra={"uid": uid, "user_input": msg.text[:80]})
            result = self.graph.invoke(state, configurable)

        if result is not None:
            self._save_state(uid, result)

            messages = result.get("messages", [])
            if len(messages) > result.get("messages_window", 50):
                if self.memory:
                    try:
                        compressed = self.memory.maybe_compress(messages, self._get_model())
                        result["messages"] = compressed
                        logger.info("messages_compressed", extra={"uid": uid, "before": len(messages), "after": len(compressed)})
                    except Exception:
                        pass

        if result and result.get("final_response"):
            self._send_bubbles(uid, result["final_response"])
        elif result and result.get("pending_confirmation") and not result.get("task_complete"):
            detail = result["pending_confirmation"]
            confirm_text = self._format_confirmation(detail)
            send_message(self.session, uid, confirm_text)

    def _get_model(self):
        try:
            from llm import create_llm
            from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
            return create_llm(LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)
        except Exception:
            return None

    def _setup_task_callback(self):
        try:
            from tasks.manager import get_task_manager
            tm = get_task_manager()

            def on_complete(task_id: str):
                info = tm.query(task_id)
                if info is None:
                    return
                status = "完成" if info.status.value == "completed" else "失败"
                msg = f"你的异步任务 [{info.task_type}] 已{status}。"
                if info.status.value == "completed" and info.result:
                    msg += f"\n结果: {info.result[:300]}"
                elif info.error:
                    msg += f"\n错误: {info.error[:200]}"
                if self.session:
                    try:
                        send_message(self.session, info.user_id, msg)
                    except Exception:
                        pass

            tm.set_on_complete(on_complete)
        except Exception:
            pass

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
            "image_urls": [],
            "image_media_refs": [],
            "image_description": "",
        }
