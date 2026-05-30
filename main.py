#!/usr/bin/env python3
"""
微信 Bot — 通过 iLink 协议将大模型接入微信

工具能力：读文件、列目录、搜文件、发文件/图片到微信、执行命令
支持 OpenAI 兼容接口（DeepSeek/Qwen/OpenAI 等）和 Anthropic 原生接口

用法：
    pip install httpx openai anthropic cryptography python-dotenv qrcode
    编辑 .env 填入 API Key
    python main.py
"""
import signal
import sys
import time
import traceback

import config
import ilink
import llm
import tools
from ilink import SessionState, SessionExpired


def main():
    signal.signal(signal.SIGINT, lambda *_: setattr(config, "running", False))

    if not config.LLM_API_KEY:
        print("错误：请在 .env 中设置 LLM_API_KEY")
        sys.exit(1)

    print(f"LLM: {config.LLM_PROVIDER} | 模型: {config.LLM_MODEL} | 工具: {len(tools.ALL_TOOLS)} 个")
    if config.LLM_PROVIDER == "openai":
        print(f"地址: {config.LLM_BASE_URL}")

    # --- 加载或创建 session ---
    state = ilink.load_session(str(config.SESSION_FILE))
    if state is None:
        state = do_login()
    print(f"会话已加载 (token=...{state.token[-8:]})\n")

    # --- 初始化 LLM ---
    model = llm.create_llm(
        config.LLM_PROVIDER, config.LLM_API_KEY,
        config.LLM_BASE_URL, config.LLM_MODEL, tools.ALL_TOOLS,
    )

    # --- 对话历史 ---
    conversations: dict[str, list[dict]] = {}

    # --- 主循环 ---
    consecutive_errors = 0
    print("开始监听消息... (Ctrl+C 退出)\n")

    while config.running:
        try:
            msgs = ilink.get_updates(state)
        except SessionExpired:
            print("\n⚠ Session 过期，需要重新登录")
            state = do_login()
            conversations.clear()
            continue
        except Exception as e:
            consecutive_errors += 1
            print(f"\ngetUpdates 错误 ({consecutive_errors}/3): {e}")
            if consecutive_errors >= 3:
                print("连续失败，等待 30s...")
                _sleep(30)
                consecutive_errors = 0
            else:
                _sleep(2)
            continue

        consecutive_errors = 0

        for msg in msgs:
            if not config.running:
                break
            uid = msg.from_user_id
            print(f"\n[{uid}] {msg.text[:100]}{'...' if len(msg.text) > 100 else ''}")

            try:
                reply = _agent_loop(model, uid, msg.text, conversations, state)
                if reply:
                    ilink.send_message(state, uid, reply)
                    ilink.save_session(state, str(config.SESSION_FILE))
                    print(f"  → 已回复 ({len(reply)} chars)")
            except Exception as e:
                print(f"  ✗ 回复失败: {e}")
                traceback.print_exc()
                try:
                    ilink.send_message(state, uid, f"抱歉，处理出错：{e}")
                except Exception:
                    pass

    print("\n已退出")


# ---------------------------------------------------------------------------
# Agent 循环 — 多轮工具调用
# ---------------------------------------------------------------------------

def _agent_loop(model: llm.BaseLLM, user_id: str, user_text: str,
                conversations: dict, state: SessionState) -> str:
    """用户消息 → LLM → [工具调用 → LLM]×N → 文本回复"""
    conv = conversations.get(user_id, [])
    if not conv:
        conv = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    conv.append({"role": "user", "content": user_text})

    for _round in range(config.MAX_TOOL_ROUNDS):
        resp = model.chat(conv)

        if not resp.tool_calls:
            msg = {"role": "assistant", "content": resp.text}
            msg.update(resp.extra_fields)  # 保留厂商特有字段（如 DeepSeek reasoning_content）
            conv.append(msg)
            _trim_history(conv, config.MAX_HISTORY)
            conversations[user_id] = conv
            return resp.text

        print(f"  🔧 调用 {len(resp.tool_calls)} 个工具: {[tc.name for tc in resp.tool_calls]}")
        conv.append(model.wrap_tool_call(resp.tool_calls, resp.extra_fields))

        for tc in resp.tool_calls:
            result = tools.execute(tc.name, tc.args, state, user_id)
            if len(result) > 4000:
                result = result[:4000] + "\n...(结果已截断)"
            conv.append(model.wrap_tool_result(tc, result))
            print(f"  ✓ {tc.name} → {len(result)} chars")

    # 超限：强制总结
    conv.append({"role": "user", "content": "请基于以上工具调用结果给出最终回复。"})
    final = model.chat(conv)
    final_msg = {"role": "assistant", "content": final.text}
    final_msg.update(final.extra_fields)
    conv.append(final_msg)
    _trim_history(conv, config.MAX_HISTORY)
    conversations[user_id] = conv
    return final.text


def _trim_history(conv: list, max_n: int) -> None:
    if len(conv) <= max_n + 1:
        return
    system = conv[0] if conv[0]["role"] == "system" else None
    recent = conv[-max_n:]
    conv.clear()
    if system:
        conv.append(system)
    conv.extend(recent)


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------

def do_login() -> SessionState:
    print("正在获取登录二维码...")
    qrcode_url, qrcode = ilink.start_qr_login()
    try:
        import qrcode as qrlib
        qr = qrlib.QRCode()
        qr.add_data(qrcode_url)
        qr.print_ascii(invert=True)
    except ImportError:
        pass
    print(f"\n用手机微信扫描上方二维码，或访问：\n{qrcode_url}\n")
    print("等待扫码...", end="", flush=True)
    result = ilink.wait_for_login(qrcode)
    state = SessionState(token=result.bot_token, base_url=result.base_url)
    state.context_tokens[result.user_id] = ""
    ilink.save_session(state, str(config.SESSION_FILE))
    return state


def _sleep(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end and config.running:
        time.sleep(0.1)


if __name__ == "__main__":
    main()
