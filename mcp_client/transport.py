import asyncio
import json
import logging
import sys
import time

import httpx

logger = logging.getLogger("wxagent.mcp.transport")


class StdioTransport:
    """Simple stdio transport using sys.stdin/stdout directly."""

    async def start(self):
        pass

    async def send(self, message: dict):
        line = json.dumps(message, ensure_ascii=False) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        logger.debug("StdioTransport sent: %s", line.strip())

    async def receive(self) -> dict:
        loop = asyncio.get_event_loop()
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            raise EOFError("stdin closed")
        line = line.strip()
        if not line:
            raise EOFError("empty line from stdin")
        logger.debug("StdioTransport received: %s", line)
        return json.loads(line)

    async def close(self):
        pass


class SSETransport:
    def __init__(self, url: str, headers: dict | None = None):
        self.url = url
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None
        self._sse_response: httpx.Response | None = None
        self._message_endpoint: str | None = None
        self._queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        self._client = httpx.AsyncClient(headers=self.headers, timeout=httpx.Timeout(30.0))
        sse_url = self.url.rstrip("/") + "/sse"
        try:
            self._sse_response = await self._client.build_request(
                "GET", sse_url, headers={"Accept": "text/event-stream"}
            ).send()
            asyncio.create_task(self._read_sse_stream())
        except Exception as e:
            logger.error("SSETransport start failed: %s", e)
            raise

    async def _read_sse_stream(self):
        try:
            async for line in self._sse_response.aiter_lines():
                if line.startswith("event: endpoint"):
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.startswith("/"):
                        self._message_endpoint = data_str
                        logger.debug("SSE message endpoint: %s", self._message_endpoint)
                        continue
                    try:
                        message = json.loads(data_str)
                        await self._queue.put(message)
                    except json.JSONDecodeError:
                        logger.warning("SSE invalid JSON: %s", data_str)
        except Exception as e:
            logger.error("SSE stream error: %s", e)

    async def send(self, message: dict):
        if self._client is None:
            raise RuntimeError("SSETransport not started")
        endpoint = self._message_endpoint or "/message"
        url = self.url.rstrip("/") + endpoint
        try:
            response = await self._client.post(
                url,
                json=message,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.debug("SSETransport sent to %s: %s", url, json.dumps(message, ensure_ascii=False))
        except Exception as e:
            logger.error("SSETransport send failed: %s", e)
            raise

    async def receive(self) -> dict:
        return await self._queue.get()

    async def close(self):
        if self._sse_response is not None:
            await self._sse_response.aclose()
            self._sse_response = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class FeishuMCPTransport:
    """飞书官方 MCP 远程服务传输层。

    飞书官方 MCP 不走标准 SSE 协议，而是自定义的 HTTP POST 接口：
    - 每次请求都是独立的 HTTP POST 到 https://mcp.feishu.cn/mcp
    - 鉴权通过 X-Lark-MCP-TAT Header（tenant_access_token）
    - 需要在 Header 中声明允许的工具列表（X-Lark-MCP-Allowed-Tools）
    - 同步请求-响应模式，send() 直接返回响应
    """

    MCP_URL = "https://mcp.feishu.cn/mcp"
    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    def __init__(self, app_id: str, app_secret: str, allowed_tools: list[str] | None = None):
        self._app_id = app_id
        self._app_secret = app_secret
        self._allowed_tools = allowed_tools or []
        self._client: httpx.AsyncClient | None = None
        self._token_cache: dict = {"token": "", "expires_at": 0}
        self._token_lock = asyncio.Lock()
        self._last_response: dict | None = None

    async def start(self):
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        # 预获取 TAT，验证配置是否正确
        await self._get_tat()
        logger.info("FeishuMCPTransport started, allowed_tools=%s", self._allowed_tools)

    async def _get_tat(self) -> str:
        """获取 tenant_access_token，带缓存（提前 5 分钟刷新）。"""
        if self._token_cache["token"] and time.time() < self._token_cache["expires_at"]:
            return self._token_cache["token"]
        async with self._token_lock:
            if self._token_cache["token"] and time.time() < self._token_cache["expires_at"]:
                return self._token_cache["token"]
            resp = await self._client.post(
                self.TOKEN_URL,
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            data = resp.json()
        token = data.get("tenant_access_token", "")
        if not token:
            code = data.get("code", -1)
            msg = data.get("msg", "unknown error")
            raise RuntimeError(f"获取飞书 TAT 失败 (code={code}): {msg}")
        expire = data.get("expire", 7200)
        self._token_cache["token"] = token
        self._token_cache["expires_at"] = time.time() + expire - 300
        logger.info("飞书 MCP TAT 已刷新，有效期 %ds", expire)
        return token

    async def send(self, message: dict) -> dict | None:
        """发送 JSON-RPC 消息到飞书官方 MCP，直接返回响应。

        与 SSE Transport 不同，飞书 MCP 是同步请求-响应模式，
        send() 直接返回响应 dict，不需要单独调用 receive()。
        """
        if self._client is None:
            raise RuntimeError("FeishuMCPTransport not started")

        tat = await self._get_tat()
        headers = {
            "Content-Type": "application/json",
            "X-Lark-MCP-TAT": tat,
        }
        if self._allowed_tools:
            headers["X-Lark-MCP-Allowed-Tools"] = ",".join(self._allowed_tools)

        try:
            resp = await self._client.post(self.MCP_URL, json=message, headers=headers)
            resp.raise_for_status()
            # 飞书 MCP 对通知消息可能返回空响应体
            body = resp.text.strip()
            if not body:
                logger.debug("FeishuMCPTransport empty response (notification)")
                self._last_response = None
                return None
            result = resp.json()
            logger.debug("FeishuMCPTransport response: %s", json.dumps(result, ensure_ascii=False)[:500])
            self._last_response = result
            return result
        except httpx.HTTPStatusError as e:
            logger.error("FeishuMCPTransport HTTP error: %s %s", e.response.status_code, e.response.text[:200])
            raise
        except Exception as e:
            logger.error("FeishuMCPTransport send failed: %s", e)
            raise

    async def receive(self) -> dict:
        """返回上一次 send 的响应（兼容 MCPClient 的 send/receive 分离设计）。"""
        if self._last_response is not None:
            resp = self._last_response
            self._last_response = None
            return resp
        raise RuntimeError("FeishuMCPTransport: no response available, call send() first")

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._token_cache = {"token": "", "expires_at": 0}
        logger.info("FeishuMCPTransport closed")
