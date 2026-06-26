import httpx  # ConnectError

import config
from network.async_client import post_sync
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry

TOOL_META = ToolMeta(
    name="aria2",
    type=ToolType.BUILTIN,
    description="Aria2下载工具集：RPC下载、状态查询",
    version="1.0.0",
    tags=["download", "aria2", "rpc"],
)

_ARIA2_RPC_URL = config.ADV_ARIA2_RPC_URL


def _aria2_add(url: str, output_dir: str | None = None,
               state=None, user_id: str = "") -> ToolResult:
    params = [[url]]
    opts = {}
    if output_dir:
        opts["dir"] = output_dir
    if opts:
        params.append(opts)

    try:
        resp = post_sync(_ARIA2_RPC_URL, json={
            "jsonrpc": "2.0",
            "id": "wxagent",
            "method": "aria2.addUri",
            "params": params,
        }, timeout=config.ADV_ARIA2_RPC_TIMEOUT)
        result = resp.json()
        if "result" in result:
            return ToolResult(
                success=True,
                content=f"下载任务已添加，GID: {result['result']}",
            )
        return ToolResult(success=False, error=str(result.get("error", "未知错误")))
    except httpx.ConnectError:
        return ToolResult(
            success=False,
            error="Aria2 服务未启动。请先安装并启动 Aria2: aria2c --enable-rpc --rpc-listen-port=6800",
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _aria2_status(gid: str, state=None, user_id: str = "") -> ToolResult:
    try:
        resp = post_sync(_ARIA2_RPC_URL, json={
            "jsonrpc": "2.0",
            "id": "wxagent",
            "method": "aria2.tellStatus",
            "params": [gid, ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "files"]],
        }, timeout=config.ADV_ARIA2_RPC_TIMEOUT)
        result = resp.json()
        if "result" in result:
            info = result["result"]
            status = info.get("status", "unknown")
            total = int(info.get("totalLength", 0))
            completed = int(info.get("completedLength", 0))
            speed = int(info.get("downloadSpeed", 0))
            pct = (completed / total * 100) if total > 0 else 0
            speed_mb = speed / 1024 / 1024
            return ToolResult(
                success=True,
                content=f"状态: {status}\n进度: {pct:.1f}%\n速度: {speed_mb:.1f} MB/s",
            )
        return ToolResult(success=False, error=str(result.get("error", "未知错误")))
    except Exception as e:
        return ToolResult(success=False, error=str(e))


ToolRegistry.register(ToolDef(
    name="aria2_download",
    description="通过 Aria2 下载文件，支持 HTTP/FTP/磁力链接。需要本地运行 Aria2 RPC 服务。",
    parameters={
        "url": {"type": "string", "description": "下载链接（HTTP/FTP/磁力链接）"},
        "output_dir": {"type": "string", "description": "保存目录（可选，默认 workspace/downloads）"},
    },
    required=["url"],
), _aria2_add)

ToolRegistry.register(ToolDef(
    name="aria2_status",
    description="查询 Aria2 下载任务状态。",
    parameters={
        "gid": {"type": "string", "description": "下载任务 GID"},
    },
    required=["gid"],
), _aria2_status)
