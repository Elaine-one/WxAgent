"""MCP 客户端：通过 stdio（子进程）或 SSE 与 MCP Server 通信。

关键设计：stdio 使用 subprocess.Popen（同步管道），而非 asyncio.create_subprocess_exec。
同步管道不绑定事件循环，因此无论在哪个事件循环中调用都能正常工作。
I/O 操作通过 asyncio.to_thread() 在线程中执行，避免阻塞事件循环。
"""

import asyncio
import json
import logging
import os
import subprocess
import threading

from mcp_client.protocol import create_request, INTERNAL_ERROR
from mcp_client.transport import SSETransport

logger = logging.getLogger("wxagent.mcp.client")


class MCPClient:
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.tools: list[dict] = []
        self._proc: subprocess.Popen | None = None
        self._transport: SSETransport | None = None
        self._lock = threading.Lock()
        self._request_id: int = 0
        self._stderr_lines: list[str] = []
        self._stderr_lock = threading.Lock()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    # ── 连接 ──────────────────────────────────────────

    async def connect(self):
        transport = self.config.get("transport", "stdio")
        if transport == "stdio":
            self._start_stdio()
        elif transport == "sse":
            await self._start_sse()
        else:
            raise ValueError(f"Unknown transport: {transport}")

    def _start_stdio(self):
        command = self.config.get("command", "")
        args = self.config.get("args", [])
        env = self.config.get("env", {})
        if command == "python":
            import sys
            command = sys.executable
        full_cmd = [command] + args
        proc_env = {**os.environ, **env}
        self._proc = subprocess.Popen(
            full_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=proc_env,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        logger.info("MCPClient '%s' started: %s", self.name, " ".join(full_cmd))

        # 启动后校验进程是否存活
        import time
        time.sleep(0.5)
        if self._proc.poll() is not None:
            stderr_tail = self.get_stderr_tail(20)
            stderr_text = "\n".join(stderr_tail) if stderr_tail else "(无 stderr 输出)"
            raise RuntimeError(
                f"MCP server '{self.name}' 启动失败 (exit code {self._proc.returncode}): "
                f"{stderr_text}"
            )

    async def _start_sse(self):
        self._transport = SSETransport(
            url=self.config.get("url", ""),
            headers=self.config.get("headers", {}),
        )
        await self._transport.start()
        logger.info("MCPClient '%s' connected via SSE", self.name)

    def _drain_stderr(self):
        """后台线程持续读取 stderr，防止管道阻塞。"""
        while self._proc and self._proc.stderr:
            line = self._proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            with self._stderr_lock:
                self._stderr_lines.append(text)
                if len(self._stderr_lines) > 100:
                    self._stderr_lines = self._stderr_lines[-100:]
            logger.debug("MCPClient '%s' stderr: %s", self.name, text)

    def get_stderr_tail(self, n: int = 20) -> list[str]:
        """获取最近 n 行 stderr 输出。"""
        with self._stderr_lock:
            return self._stderr_lines[-n:]

    # ── 收发消息 ──────────────────────────────────────

    async def _send(self, message: dict) -> dict | None:
        """发送消息。请求（有 id）会等待响应，通知（无 id）只发送不等待。"""
        is_notification = "id" not in message
        if self._proc is not None:
            if self._proc.poll() is not None:
                raise RuntimeError(f"MCP server exited (code {self._proc.returncode})")
            if is_notification:
                await asyncio.to_thread(self._write_stdio, message)
                return None
            return await asyncio.to_thread(self._send_stdio, message)
        if self._transport is not None:
            await self._transport.send(message)
            if is_notification:
                return None
            return await self._transport.receive()
        raise RuntimeError("MCP client not connected")

    def _write_stdio(self, message: dict):
        """只写不读（用于通知消息）。"""
        line = json.dumps(message, ensure_ascii=False) + "\n"
        with self._lock:
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()
        logger.debug("MCPClient '%s' → %s", self.name, line.strip())

    def _send_stdio(self, message: dict) -> dict | None:
        line = json.dumps(message, ensure_ascii=False) + "\n"
        with self._lock:
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()
        logger.debug("MCPClient '%s' → %s", self.name, line.strip())
        resp = self._proc.stdout.readline()
        if not resp:
            stderr_tail = self.get_stderr_tail(10)
            stderr_text = "\n".join(stderr_tail) if stderr_tail else ""
            detail = f" (stderr: {stderr_text})" if stderr_text else ""
            raise EOFError(f"MCP server closed stdout{detail}")
        text = resp.decode("utf-8").strip()
        logger.debug("MCPClient '%s' ← %s", self.name, text)
        return json.loads(text)

    async def _request(self, method: str, params: dict | None = None) -> dict:
        msg = create_request(method=method, params=params, request_id=self._next_id()).to_dict()
        try:
            response = await self._send(msg)
            return response or {"error": {"code": INTERNAL_ERROR, "message": "No response"}}
        except Exception as e:
            logger.error("MCPClient '%s' %s failed: %s", self.name, method, e)
            return {"error": {"code": INTERNAL_ERROR, "message": str(e)}}

    # ── 协议方法 ──────────────────────────────────────

    async def initialize(self) -> dict:
        resp = await self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": self.name, "version": "1.0.0"},
        })
        # 发送 initialized 通知
        notification = create_request(
            method="notifications/initialized", params=None, request_id=0
        ).to_dict()
        notification.pop("id", None)
        try:
            await self._send(notification)
        except Exception as e:
            logger.warning("MCPClient '%s' initialized notification failed: %s", self.name, e)
        return resp.get("result", {})

    async def list_tools(self) -> list[dict]:
        resp = await self._request("tools/list")
        self.tools = resp.get("result", {}).get("tools", [])
        logger.info("MCPClient '%s' discovered %d tools", self.name, len(self.tools))
        return self.tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self._request("tools/call", {"name": name, "arguments": arguments})

    async def close(self):
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None
        if self._transport is not None:
            await self._transport.close()
            self._transport = None
        logger.info("MCPClient '%s' closed", self.name)
