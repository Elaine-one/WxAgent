import asyncio
import json
import logging
import sys

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
