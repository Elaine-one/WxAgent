"""
微信 iLink Bot 协议层 — 基于 @tencent-weixin/openclaw-weixin v2.4.4
实现：扫码登录、长轮询收消息、发文本消息、Session 持久化

CDN 文件上传见 ilink_upload.py
"""
import base64
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
FIXED_AUTH_URL = "https://ilinkai.weixin.qq.com"  # 固定的扫码登录服务器
ILINK_APP_ID = "bot"                                 # iLink 应用标识
BOT_TYPE = "3"                                       # Bot 类型编号
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"  # CDN 上传基础地址
DEFAULT_LONGPOLL_TIMEOUT_MS = 35_000                 # 长轮询超时（毫秒）
DEFAULT_API_TIMEOUT_S = 15                           # 普通 API 超时（秒）
DEFAULT_UPLOAD_TIMEOUT_S = 60                        # CDN 上传超时（秒）
SESSION_EXPIRED_ERRCODE = -14                        # session 过期的错误码

# 媒体类型（proto: UploadMediaType）
UPLOAD_TYPE_IMAGE = 1
UPLOAD_TYPE_VIDEO = 2
UPLOAD_TYPE_FILE  = 3
UPLOAD_TYPE_VOICE = 4

# 消息项类型（proto: MessageItemType）
ITEM_TYPE_TEXT  = 1
ITEM_TYPE_IMAGE = 2
ITEM_TYPE_VOICE = 3
ITEM_TYPE_FILE  = 4
ITEM_TYPE_VIDEO = 5


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _build_client_version() -> int:
    """构造客户端版本号（uint32 格式：0x00MMNNPP）"""
    return 0x0001000B  # 等价于 1.0.11


def _random_wechat_uin() -> str:
    """生成随机 X-WECHAT-UIN 头（uint32 十进制 → base64）"""
    u32 = secrets.randbits(32)
    return base64.b64encode(str(u32).encode()).decode()


def _build_base_info() -> dict:
    """构造 base_info — 每个 API 请求的顶层字段"""
    return {
        "channel_version": "2.4.4",
        "bot_agent": "OpenClaw",
    }


def _build_headers(token: Optional[str] = None) -> dict:
    """构造 iLink API 请求头，包含鉴权和版本信息"""
    h = {
        "Content-Type": "application/json",
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(_build_client_version()),
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------
@dataclass
class LoginResult:
    """扫码登录成功后返回的凭证"""
    bot_token: str       # bot 鉴权 token
    bot_id: str          # 例如 "xxx@im.bot"
    base_url: str        # 当前 IDC 的 API 地址
    user_id: str         # 扫码用户的微信 ID，例如 "xxx@im.wechat"


@dataclass
class InboundMessage:
    """收到的微信消息"""
    seq: int
    from_user_id: str
    session_id: str
    context_token: str   # 回传此值以维持会话连续性
    text: str
    msg_id: int = 0
    create_time_ms: int = 0


@dataclass
class SessionState:
    """Bot 会话状态，可序列化到磁盘以支持断线重连"""
    token: str
    base_url: str
    cdn_base_url: str = CDN_BASE_URL
    get_updates_buf: str = ""                      # 长轮询游标
    context_tokens: dict[str, str] = field(default_factory=dict)  # user_id → context_token


class SessionExpired(Exception):
    """Session 过期，需要重新扫码登录"""


# ---------------------------------------------------------------------------
# 认证：二维码扫码登录
# ---------------------------------------------------------------------------
def start_qr_login() -> tuple[str, str]:
    """请求登录二维码。返回 (二维码URL, qrcode密钥)"""
    body = json.dumps({"local_token_list": []})
    url = f"{FIXED_AUTH_URL}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
    h = _build_headers()
    resp = httpx.post(url, content=body, headers=h, timeout=DEFAULT_API_TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    return data["qrcode_img_content"], data["qrcode"]


def poll_qr_status(qrcode: str, verify_code: Optional[str] = None) -> dict:
    """长轮询扫码状态，最多阻塞约 35 秒"""
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
    """阻塞等待用户扫码确认，超时 8 分钟。确认后返回登录凭证"""
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
    """在终端用 ASCII 字符显示二维码"""
    try:
        import qrcode
        qr = qrcode.QRCode()
        qr.add_data(qrcode_url)
        qr.print_ascii(invert=True)
    except ImportError:
        pass
    print(f"若二维码未能显示，请访问：{qrcode_url}")


# ---------------------------------------------------------------------------
# 消息接收：长轮询 getUpdates
# ---------------------------------------------------------------------------
def get_updates(state: SessionState, timeout_ms: int = DEFAULT_LONGPOLL_TIMEOUT_MS) -> list[InboundMessage]:
    """长轮询获取新消息，最多阻塞 timeout_ms 毫秒"""
    url = f"{state.base_url}/ilink/bot/getupdates"
    body = json.dumps({
        "get_updates_buf": state.get_updates_buf,
        "base_info": _build_base_info(),
    })
    h = _build_headers(token=state.token)

    try:
        resp = httpx.post(url, content=body, headers=h, timeout=(timeout_ms / 1000) + 5)
        resp.raise_for_status()
        data = resp.json()
    except httpx.ReadTimeout:
        return []

    # 检查 session 是否过期（errcode = -14）
    errcode = data.get("errcode", 0)
    ret = data.get("ret", 0)
    if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
        raise SessionExpired("session 已过期，需要重新登录")

    if (ret != 0 and ret is not None) or (errcode != 0 and errcode is not None):
        raise RuntimeError(f"getUpdates 错误: ret={ret} errcode={errcode} errmsg={data.get('errmsg', '')}")

    # 更新轮询游标
    new_buf = data.get("get_updates_buf", "")
    if new_buf:
        state.get_updates_buf = new_buf

    # 更新服务端建议的下次轮询间隔
    suggested_ms = data.get("longpolling_timeout_ms", 0)
    if suggested_ms > 0:
        state._next_poll_timeout = suggested_ms  # type: ignore

    # 解析消息列表
    msgs: list[InboundMessage] = []
    for raw in data.get("msgs", []):
        msg = _parse_message(raw)
        if msg is None:
            continue
        # 保存 context_token，回复时需要原样回传以维持会话连续性
        if msg.context_token:
            state.context_tokens[msg.from_user_id] = msg.context_token
        msgs.append(msg)

    return msgs


def _parse_message(raw: dict) -> Optional[InboundMessage]:
    """从 WeixinMessage 中提取文本和元数据"""
    item_list = raw.get("item_list", [])
    text_parts = []
    for item in item_list:
        if item.get("type") == ITEM_TYPE_TEXT:
            t = item.get("text_item", {}).get("text", "")
            if t:
                text_parts.append(t)
        elif item.get("type") == ITEM_TYPE_VOICE:
            vt = item.get("voice_item", {}).get("text", "")
            if vt:
                text_parts.append(vt)

    if not text_parts:
        return None  # 暂不处理纯媒体消息

    return InboundMessage(
        seq=raw.get("seq", 0),
        msg_id=raw.get("message_id", 0),
        from_user_id=raw.get("from_user_id", ""),
        session_id=raw.get("session_id", ""),
        context_token=raw.get("context_token", ""),
        text="".join(text_parts),
        create_time_ms=raw.get("create_time_ms", 0),
    )


# ---------------------------------------------------------------------------
# 消息发送（纯文本）
# ---------------------------------------------------------------------------
def send_message(state: SessionState, to_user: str, text: str) -> str:
    """向微信用户发送文本消息。返回 client_id 作为消息 ID"""
    client_id = f"bot-{secrets.token_hex(8)}"
    ctx_token = state.context_tokens.get(to_user, "")

    url = f"{state.base_url}/ilink/bot/sendmessage"
    body = json.dumps({
        "msg": {
            "from_user_id": "",
            "to_user_id": to_user,
            "client_id": client_id,
            "message_type": 2,   # 消息类型：2 = BOT
            "message_state": 2,  # 消息状态：2 = FINISH（生成完毕）
            "item_list": [
                {"type": ITEM_TYPE_TEXT, "text_item": {"text": text}}
            ],
            "context_token": ctx_token,
        },
        "base_info": _build_base_info(),
    })
    h = _build_headers(token=state.token)
    resp = httpx.post(url, content=body, headers=h, timeout=DEFAULT_API_TIMEOUT_S)
    resp.raise_for_status()
    return client_id


# ---------------------------------------------------------------------------
# Session 持久化（断线重连不需要重新扫码）
# ---------------------------------------------------------------------------
def save_session(state: SessionState, path: str = "session.json") -> None:
    """将会话状态保存到磁盘"""
    with open(path, "w") as f:
        json.dump({
            "token": state.token,
            "base_url": state.base_url,
            "cdn_base_url": state.cdn_base_url,
            "get_updates_buf": state.get_updates_buf,
            "context_tokens": state.context_tokens,
        }, f, indent=2)
    os.chmod(path, 0o600)


def load_session(path: str = "session.json") -> Optional[SessionState]:
    """从磁盘恢复会话状态"""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    s = SessionState(
        token=data["token"],
        base_url=data["base_url"],
        cdn_base_url=data.get("cdn_base_url", CDN_BASE_URL),
        get_updates_buf=data.get("get_updates_buf", ""),
    )
    s.context_tokens = data.get("context_tokens", {})
    return s
