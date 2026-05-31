#!/usr/bin/env python3
import argparse
import atexit
import signal
import sys
import time
import traceback

import config
import channel
import llm
import tools
from channel import SessionState, SessionExpired
from channel.message import message_signature, merge_messages
from core.agent_loop import agent_loop, do_login, interruptible_sleep
from observability.logger import get_logger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="离线模式，不连接微信")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *_: setattr(config, "running", False))

    if not config.LLM_API_KEY:
        print("错误：请在 .env 中设置 LLM_API_KEY")
        sys.exit(1)

    get_logger()
    config.ensure_data_dirs()
    config.ensure_workspace()
    config.init_workspace_packages("basic")

    try:
        import jieba
        jieba.initialize()
    except Exception:
        pass

    phase3_ctx = init_phase3()
    atexit.register(_cleanup, phase3_ctx)

    print(f"LLM: {config.LLM_PROVIDER} | 模型: {config.LLM_MODEL} | 工具: {len(tools.ALL_TOOLS)} 个")
    if config.LLM_PROVIDER == "openai":
        print(f"地址: {config.LLM_BASE_URL}")

    model = llm.create_llm(
        config.LLM_PROVIDER, config.LLM_API_KEY,
        config.LLM_BASE_URL, config.LLM_MODEL, tools.ALL_TOOLS,
    )

    if config.AGENT_BACKEND == "langgraph":
        from core.graph import build_agent_graph
        from core.dispatcher import Dispatcher
        _graph = build_agent_graph(
            model, None, tools.ALL_TOOLS,
            memory_manager=phase3_ctx["memory"],
        )
        _dispatcher = Dispatcher(_graph, None, memory=phase3_ctx["memory"])
        _use_langgraph = True
        print(f"Agent 后端: LangGraph")
    else:
        _use_langgraph = False
        conversations: dict[str, list[dict]] = {}
        from core.graph import _build_model_cache
        phase3_ctx["model_cache"] = _build_model_cache(model, tools.ALL_TOOLS)
        print(f"Agent 后端: legacy")

    if args.dry_run:
        _dry_run_loop(model, _use_langgraph, _dispatcher if _use_langgraph else None, conversations, phase3_ctx)
        return

    state = channel.load_session(str(config.SESSION_FILE))
    if state is None:
        state = do_login()
    print(f"会话已加载 (token=...{state.token[-8:]})\n")

    if _use_langgraph:
        _dispatcher.session = state

    consecutive_errors = 0
    print("开始监听消息... (Ctrl+C 退出)\n")

    pending_msgs: dict[str, list] = {}
    last_msg_time: dict[str, float] = {}
    last_processed: dict[str, tuple[str, float]] = {}
    DEBOUNCE_DELAY = 3.0

    while config.running:
        try:
            msgs = channel.get_updates(state)
        except SessionExpired:
            print("\n⚠ Session 过期，需要重新登录")
            state = do_login()
            if not _use_langgraph:
                conversations.clear()
            pending_msgs.clear()
            last_msg_time.clear()
            last_processed.clear()
            continue
        except Exception as e:
            consecutive_errors += 1
            print(f"\ngetUpdates 错误 ({consecutive_errors}/3): {e}")
            if consecutive_errors >= 3:
                print("连续失败，等待 30s...")
                interruptible_sleep(30)
                consecutive_errors = 0
            else:
                interruptible_sleep(2)
            continue

        consecutive_errors = 0

        for msg in msgs:
            if not config.running:
                break
            uid = msg.from_user_id
            print(f"\n[{uid}] {msg.text[:100]}{'...' if len(msg.text) > 100 else ''}")
            pending_msgs.setdefault(uid, []).append(msg)
            last_msg_time[uid] = time.time()

        now = time.time()
        ready_uids = [
            uid for uid, t in last_msg_time.items()
            if now - t >= DEBOUNCE_DELAY and uid in pending_msgs
        ]

        for uid in ready_uids:
            batch = pending_msgs.pop(uid)
            del last_msg_time[uid]

            if not batch:
                continue

            merged_msg = merge_messages(batch)

            msg_sig = message_signature(merged_msg)
            prev_sig, _ = last_processed.get(uid, ("", 0))
            if msg_sig and msg_sig == prev_sig:
                print(f"  ⏭ 重复消息，跳过")
                continue
            if msg_sig:
                last_processed[uid] = (msg_sig, now)

            try:
                if _use_langgraph:
                    _dispatcher.handle_message(merged_msg)
                    channel.save_session(state, str(config.SESSION_FILE))
                else:
                    reply = agent_loop(model, uid, merged_msg, conversations, state, phase3_ctx)
                    if reply:
                        channel.send_message(state, uid, reply)
                        channel.save_session(state, str(config.SESSION_FILE))
                        print(f"  → 已回复 ({len(reply)} chars)")
            except Exception as e:
                print(f"  ✗ 回复失败: {e}")
                traceback.print_exc()
                try:
                    channel.send_message(state, uid, f"抱歉，处理出错：{e}")
                except Exception:
                    pass

        stale = [uid for uid, (_, t) in last_processed.items() if now - t > 60]
        for uid in stale:
            del last_processed[uid]

        if not msgs and not ready_uids:
            interruptible_sleep(0.3)

    print("\n已退出")


def init_phase3():
    from security.audit import AuditLogger
    from memory.manager import MemoryManager
    from memory.indexer import BackgroundIndexer
    from tasks.manager import get_task_manager

    audit = AuditLogger()
    memory = MemoryManager()
    tasks = get_task_manager()

    # 仅在 config.yaml 中 indexer.enabled=true 时启动文件索引
    # 基础模式下不需要 ChromaDB + SentenceTransformer，节省 CPU/内存
    indexer = None
    try:
        import yaml
        with open(config.PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            idx_cfg = yaml.safe_load(f).get("indexer", {})
        if idx_cfg.get("enabled", False):
            indexer = BackgroundIndexer()
            indexer.start()
    except Exception:
        pass

    return {
        "audit": audit,
        "memory": memory,
        "tasks": tasks,
        "indexer": indexer,
        "model_cache": None,
    }


def _cleanup(phase3_ctx):
    from tasks.manager import get_task_manager
    tm = get_task_manager()
    try:
        tm.io_pool.shutdown(wait=False)
    except Exception:
        pass
    try:
        tm.cpu_pool.shutdown(wait=False)
    except Exception:
        pass
    indexer = phase3_ctx.get("indexer")
    if indexer:
        indexer.stop()


def _dry_run_loop(model, use_langgraph: bool, dispatcher, conversations: dict, phase3_ctx):
    from channel.client import InboundMessage
    print("离线模式 — 输入消息，Ctrl+C 退出\n")
    while config.running:
        try:
            text = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not text.strip():
            continue
        if use_langgraph and dispatcher is not None:
            msg = InboundMessage(seq=0, from_user_id="dry-run", session_id="",
                                context_token="", text=text)
            dispatcher.handle_message(msg)
        else:
            msg = InboundMessage(seq=0, from_user_id="dry-run", session_id="",
                                context_token="", text=text)
            reply = agent_loop(model, "dry-run", msg, conversations, None, phase3_ctx)
            if reply:
                print(f"\n助手: {reply}\n")


if __name__ == "__main__":
    main()
