import asyncio
import logging
import threading
import time
from collections import OrderedDict

import config
from channel.client import InboundMessage, SessionState
from channel.sender import send_message
from core.deps import Deps
from core.state import AgentState
from llm.streaming import split_for_wechat
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.dispatcher")


class Dispatcher:
    MAX_SESSIONS = config.ADV_MAX_SESSIONS
    SESSION_TTL_SECONDS = config.ADV_SESSION_TTL_SECONDS

    def __init__(self, graph, session: SessionState, memory=None):
        self.graph = graph
        self.session = session
        self.memory = memory
        self.deps: Deps = getattr(graph, "_deps", None)
        self._sessions: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        # 持久事件循环：所有异步操作共享，避免 asyncio.run() 反复创建/销毁循环
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()
        self._setup_task_callback()

    def _configurable(self, uid: str) -> dict:
        if self.deps:
            self.deps.session = self.session
        return {"configurable": {"thread_id": uid, "deps": self.deps}}

    def _run_async(self, coro):
        """在持久事件循环中运行异步协程并等待结果。"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

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
        configurable = self._configurable(uid)

        _FIELD_MAP = {
            "image_url": "image_urls", "image_media_ref": "image_media_refs",
            "file_url": "file_urls", "file_media_ref": "file_media_refs",
            "file_name": "file_names", "file_size": "file_sizes",
            "voice_url": "voice_urls", "voice_media_ref": "voice_media_refs",
            "video_url": "video_urls", "video_media_ref": "video_media_refs",
        }
        media_state = {}
        for attr, state_key in _FIELD_MAP.items():
            val = getattr(msg, attr, None)
            if val:
                media_state[state_key] = [val]

        # 多语音合并时，使用完整列表覆盖单条
        all_voice_urls = getattr(msg, "_all_voice_urls", None)
        all_voice_media_refs = getattr(msg, "_all_voice_media_refs", None)
        if all_voice_urls:
            media_state["voice_urls"] = all_voice_urls
        if all_voice_media_refs:
            media_state["voice_media_refs"] = all_voice_media_refs

        # 流式发送回调：边收边发，记录已发送的字符数
        _stream_sent_chars = [0]  # 用列表以便在闭包中修改

        def _stream_callback(text: str):
            try:
                send_message(self.session, uid, text)
                _stream_sent_chars[0] += len(text)
                time.sleep(config.ADV_BUBBLE_SEND_INTERVAL)
            except Exception:
                pass

        # 通过 Deps（configurable 通道）传递回调，不放入 state（避免序列化失败）
        if self.deps:
            self.deps.stream_callback = _stream_callback

        # Skill 触发词匹配（Trigger Recall）
        candidate_skills = ToolRegistry.match_triggers(msg.text)
        candidate_skill_names = [m.name for m in candidate_skills] if candidate_skills else []
        if candidate_skill_names:
            logger.info("skill_trigger_match", extra={"user_id": uid, "skills": candidate_skill_names, "input": msg.text[:80]})

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
                    "candidate_skill_names": candidate_skill_names,
                }
                self.graph.update_state(configurable, state_update, as_node="wait_user")
                logger.info("interrupt_resume", extra={"user_id": uid, "user_input": msg.text[:80]})
                result = self._run_async(self.graph.ainvoke(None, configurable))
            else:
                state = self._get_or_create_state(uid)
                state["user_input"] = msg.text
                state["msg_type"] = msg.msg_type
                state.update(media_state)
                state["candidate_skill_names"] = candidate_skill_names
                result = self._run_async(self.graph.ainvoke(state, configurable))
        else:
            state = self._get_or_create_state(uid)
            if state.get("task_complete"):
                state = self._new_state(uid)
            state["user_input"] = msg.text
            state["msg_type"] = msg.msg_type
            state.update(media_state)
            state["interrupted"] = bool(state.get("messages") and len(state.get("messages", [])) > 1 and not state.get("task_complete"))
            state["candidate_skill_names"] = candidate_skill_names
            logger.info("new_invocation", extra={"user_id": uid, "user_input": msg.text[:80]})
            result = self._run_async(self.graph.ainvoke(state, configurable))

        # 清理 deps 上的回调
        if self.deps:
            self.deps.stream_callback = None

        if result is not None:
            self._save_state(uid, result)

            messages = result.get("messages", [])
            if len(messages) > result.get("messages_window", 50):
                if self.memory:
                    try:
                        compressed = self.memory.maybe_compress(messages, self._get_model())
                        result["messages"] = compressed
                        logger.info("messages_compressed", extra={"user_id": uid, "before": len(messages), "after": len(compressed)})
                    except Exception:
                        pass

        if result and result.get("final_response"):
            # 流式回调已发送部分文本，只发送剩余部分
            full_text = result["final_response"]
            if _stream_sent_chars[0] > 0 and _stream_sent_chars[0] < len(full_text):
                remaining = full_text[_stream_sent_chars[0]:]
                if remaining.strip():
                    logger.info("send_remaining", extra={"user_id": uid, "sent": _stream_sent_chars[0], "remaining": len(remaining)})
                    self._send_bubbles(uid, remaining)
            elif _stream_sent_chars[0] == 0:
                # 没有通过流式回调发送，走常规气泡发送
                logger.info("send_response", extra={"user_id": uid, "text_preview": full_text[:200], "text_len": len(full_text)})
                self._send_bubbles(uid, full_text)
        elif result and result.get("pending_confirmation") and not result.get("task_complete"):
            detail = result["pending_confirmation"]
            confirm_text = self._format_confirmation(detail)
            logger.info("send_confirm", extra={"user_id": uid, "confirm_type": detail.get("type", ""), "text_preview": confirm_text[:200]})
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
        elif confirm_type == "delete_file":
            path = detail.get("path", "")
            size = detail.get("size", 0)
            size_str = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
            return (
                f"⚠ 即将删除文件\n"
                f"路径: {path}\n"
                f"大小: {size_str}\n"
                f"此操作不可恢复！\n\n"
                f"确认删除请回复 Y，取消回复 N"
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
            time.sleep(config.ADV_BUBBLE_SEND_INTERVAL)

    def _new_state(self, uid: str) -> dict:
        return {
            "user_id": uid,
            "task_id": "",
            "messages": [{"role": "system", "content": config.get_system_prompt()}],
            "user_input": "",
            "last_error": "",
            "pending_confirmation": {},
            "confirmation_response": "",
            "interrupted": False,
            "interrupted_message": "",
            "msg_type": "",
            "final_response": "",
            "task_complete": False,
            "messages_window": config.ADV_MESSAGES_WINDOW,
            "user_preferences": {},
            "active_tools": [],
            "cost": {"llm_calls": 0, "total_tokens": 0, "estimated_usd": 0.0},
            "image_urls": [],
            "image_media_refs": [],
            "image_description": "",
            "memory_context": "",
            "confirm_rounds": 0,
            "saved_image_paths": [],
            "file_urls": [],
            "file_media_refs": [],
            "file_names": [],
            "file_sizes": [],
            "saved_file_paths": [],
            "voice_urls": [],
            "voice_media_refs": [],
            "voice_transcription": "",
            "video_urls": [],
            "video_media_refs": [],
            "candidate_skill_names": [],
        }
