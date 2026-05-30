import json
import time
from typing import Optional

import httpx

from channel.client import (
    BOT_TYPE, DEFAULT_API_TIMEOUT_S, FIXED_AUTH_URL, LoginResult, _build_headers,
)


def start_qr_login() -> tuple[str, str]:
    body = json.dumps({"local_token_list": []})
    url = f"{FIXED_AUTH_URL}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
    h = _build_headers()
    resp = httpx.post(url, content=body, headers=h, timeout=DEFAULT_API_TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    return data["qrcode_img_content"], data["qrcode"]


def poll_qr_status(qrcode: str, verify_code: Optional[str] = None) -> dict:
    ep = f"ilink/bot/get_qrcode_status?qrcode={qrcode}"
    if verify_code:
        ep += f"&verify_code={verify_code}"
    url = f"{FIXED_AUTH_URL}/{ep}"
    h = _build_headers()
    try:
        resp = httpx.get(url, headers=h, timeout=40)
        resp.raise_for_status()
        return resp.json()
    except httpx.ReadTimeout:
        return {"status": "wait"}


def wait_for_login(qrcode: str, timeout_s: int = 480) -> LoginResult:
    deadline = time.time() + timeout_s
    scanned_printed = False

    while time.time() < deadline:
        status_resp = poll_qr_status(qrcode)
        status = status_resp.get("status", "wait")

        if status == "wait":
            print(".", end="", flush=True)
            time.sleep(1)
        elif status == "scaned":
            if not scanned_printed:
                print("\n正在验证...")
                scanned_printed = True
            time.sleep(1)
        elif status == "scaned_but_redirect":
            time.sleep(1)
        elif status == "confirmed":
            if not status_resp.get("ilink_bot_id"):
                raise RuntimeError("登录失败：服务器未返回 ilink_bot_id")
            bot_token = status_resp.get("bot_token", "")
            base_url = status_resp.get("baseurl", FIXED_AUTH_URL)
            print(f"\n已连接！")
            return LoginResult(
                bot_token=bot_token,
                bot_id=status_resp["ilink_bot_id"],
                base_url=base_url.rstrip("/"),
                user_id=status_resp.get("ilink_user_id", ""),
            )
        elif status == "expired":
            print("\n二维码已过期，正在刷新...")
            qrcode_url, qrcode = start_qr_login()
            _display_qr_hint(qrcode_url)
            scanned_printed = False
        elif status == "need_verifycode":
            code = input("\n输入手机微信显示的数字：")
            verified = poll_qr_status(qrcode, verify_code=code)
            if verified.get("status") == "confirmed":
                bot_token = verified.get("bot_token", "")
                base_url = verified.get("baseurl", FIXED_AUTH_URL)
                print(f"\n已连接！")
                return LoginResult(
                    bot_token=bot_token,
                    bot_id=verified["ilink_bot_id"],
                    base_url=base_url.rstrip("/"),
                    user_id=verified.get("ilink_user_id", ""),
                )
            elif verified.get("status") == "need_verifycode":
                print("验证码错误，请重试")
                continue
            else:
                continue
        elif status == "verify_code_blocked":
            print("\n多次输入错误，正在刷新二维码...")
            qrcode_url, qrcode = start_qr_login()
            _display_qr_hint(qrcode_url)
            scanned_printed = False
        elif status == "binded_redirect":
            print("\n已连接过此机器，无需重复连接。")
            raise SystemExit(0)
        else:
            time.sleep(1)

    raise RuntimeError("登录超时，请重试")


def _display_qr_hint(qrcode_url: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode()
        qr.add_data(qrcode_url)
        qr.print_ascii(invert=True)
    except ImportError:
        pass
    print(f"若二维码未能显示，请访问：{qrcode_url}")
