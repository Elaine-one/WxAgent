"""专用 HTTP I/O 异步客户端。

独立事件循环线程 + 共享 httpx.AsyncClient，所有 HTTP 请求（同步/异步）
统一经过此层，享受异步 I/O 的非阻塞连接管理 + HTTP/2 多路复用。
"""

import asyncio
import atexit
import logging
import queue
import threading
from typing import Optional

import httpx

logger = logging.getLogger("wxagent.network")

# 检测 HTTP/2 支持
try:
    import h2 as _h2
    _HTTP2_SUPPORTED = True
except ImportError:
    _HTTP2_SUPPORTED = False
    logger.info("h2 未安装，HTTP/2 不可用。安装: pip install httpx[http2]")

_loop: Optional[asyncio.AbstractEventLoop] = None
_client: Optional[httpx.AsyncClient] = None
_started: bool = False
_lock = threading.Lock()


def _ensure_started():
    global _loop, _client, _started
    if _started:
        return
    with _lock:
        if _started:
            return
        _loop = asyncio.new_event_loop()
        _client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=8,
                keepalive_expiry=15,
            ),
            timeout=httpx.Timeout(30.0),
            http2=_HTTP2_SUPPORTED,
            trust_env=False,
        )
        t = threading.Thread(target=_loop.run_forever, daemon=True, name="http-loop")
        t.start()
        atexit.register(_shutdown)
        _started = True
        logger.info("HTTP loop started (thread=%s, http2=%s)", t.name, _HTTP2_SUPPORTED)


def _shutdown():
    global _client, _loop, _started
    if _client:
        try:
            future = asyncio.run_coroutine_threadsafe(_client.aclose(), _loop)
            future.result(timeout=5)
        except Exception:
            pass
    if _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
    _client = None
    _loop = None
    _started = False


def _run(coro):
    """提交协程到 HTTP 循环，阻塞当前线程等待结果。"""
    _ensure_started()
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()


# ---- 异步 API（给 async 调用者使用）----

async def request(method: str, url: str, **kwargs) -> httpx.Response:
    _ensure_started()
    return await _client.request(method, url, **kwargs)


async def get(url: str, **kwargs) -> httpx.Response:
    return await request("GET", url, **kwargs)


async def post(url: str, **kwargs) -> httpx.Response:
    return await request("POST", url, **kwargs)


def stream(method: str, url: str, **kwargs):
    """返回 httpx.AsyncClient.stream 的 async context manager。
    调用者必须用 `async with` 使用。"""
    _ensure_started()
    return _client.stream(method, url, **kwargs)


# ---- 同步 API（给 sync 调用者使用）----

def request_sync(method: str, url: str, **kwargs) -> httpx.Response:
    return _run(request(method, url, **kwargs))


def get_sync(url: str, **kwargs) -> httpx.Response:
    return _run(get(url, **kwargs))


def post_sync(url: str, **kwargs) -> httpx.Response:
    return _run(post(url, **kwargs))


class _SyncStreamCtx:
    """将异步流式响应桥接为同步 context manager。

    HTTP 循环线程作为生产者将分块推入队列，
    调用者线程作为消费者按需取出。
    """

    def __init__(self, method: str, url: str, kwargs: dict):
        self._q: queue.Queue = queue.Queue(maxsize=2)
        self._method = method
        self._url = url
        self._kwargs = kwargs
        self._resp = None
        self._entered = False

    def __enter__(self):
        _ensure_started()
        asyncio.run_coroutine_threadsafe(self._produce(), _loop)
        msg_type, payload = self._q.get()
        if msg_type == "error":
            raise payload
        self._resp = payload
        self._entered = True
        return self

    def __exit__(self, *args):
        pass

    async def _produce(self):
        try:
            async with _client.stream(self._method, self._url, **self._kwargs) as resp:
                self._q.put(("response", resp))
                async for chunk in resp.aiter_bytes(65536):
                    self._q.put(("chunk", chunk))
                self._q.put(("done", None))
        except Exception as e:
            self._q.put(("error", e))

    def raise_for_status(self):
        if self._resp:
            self._resp.raise_for_status()

    @property
    def headers(self):
        return self._resp.headers if self._resp else {}

    @property
    def status_code(self):
        return self._resp.status_code if self._resp else 0

    def iter_bytes(self, chunk_size: int = 65536):
        while True:
            msg_type, payload = self._q.get()
            if msg_type == "error":
                raise payload
            if msg_type == "done":
                break
            yield payload


def stream_sync(method: str, url: str, **kwargs):
    """同步流式请求，返回可 `with` 使用的 context manager。"""
    return _SyncStreamCtx(method, url, kwargs)


# ---- 跨循环异步 API（给运行在其他事件循环中的 async 调用者使用）----

async def _run_async(coro):
    """提交协程到 HTTP 循环，从任意事件循环 await。

    使用 asyncio.wrap_future 桥接两个事件循环，调用者可以安全地
    在 dispatcher 的 LangGraph 循环中 await 此函数。
    """
    _ensure_started()
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return await asyncio.wrap_future(future)


async def async_request(method: str, url: str, **kwargs) -> httpx.Response:
    return await _run_async(request(method, url, **kwargs))


async def async_get(url: str, **kwargs) -> httpx.Response:
    return await _run_async(get(url, **kwargs))


async def async_post(url: str, **kwargs) -> httpx.Response:
    return await _run_async(post(url, **kwargs))
