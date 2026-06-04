"""MCP 加载器：启动时连接所有 MCP Server 并注册工具到 ToolRegistry。

使用 subprocess.Popen 创建子进程，管道不绑定事件循环，
因此启动时通过 asyncio.run() 连接后，后续任意事件循环均可正常调用。
"""

import asyncio
import logging

from mcp_client.client import MCPClient
from tools.base import ToolDef, ToolMeta, ToolType
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.mcp.loader")

_loader: "MCPLoader | None" = None


def get_mcp_loader() -> "MCPLoader":
    global _loader
    if _loader is None:
        _loader = MCPLoader()
    return _loader


async def connect_server(name: str, config: dict) -> list[str]:
    """连接 MCP Server 并注册工具。"""
    loader = get_mcp_loader()
    client = MCPClient(name=name, config=config)
    await client.connect()
    await client.initialize()
    return await loader.load_server(client)


async def disconnect_server(name: str) -> None:
    """断开 MCP Server 并注销工具。"""
    await get_mcp_loader().unload_server(name)


def init_mcp_servers_sync(servers: dict) -> "MCPLoader | None":
    """启动时同步连接所有 MCP Server。"""
    if not servers:
        return None
    loader = get_mcp_loader()

    async def _init():
        for name, cfg in servers.items():
            try:
                await connect_server(name, cfg)
                print(f"  MCP 服务 '{name}' 已连接")
            except Exception as e:
                print(f"  MCP 服务 '{name}' 连接失败: {e}")

    asyncio.run(_init())
    return loader


class MCPLoader:
    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
        self._tools: dict[str, list[str]] = {}

    async def load_server(self, client: MCPClient) -> list[str]:
        """连接 client，发现工具并注册到 ToolRegistry。"""
        name = client.name
        self._clients[name] = client
        registered: list[str] = []

        tools = await client.list_tools()
        for tool in tools:
            tool_name = tool.get("name", "")
            mcp_name = f"mcp_{name}_{tool_name}"
            schema = tool.get("inputSchema", {})

            tool_def = ToolDef(
                name=mcp_name,
                description=f"[MCP:{name}] {tool.get('description', '')}",
                parameters=schema.get("properties", {}),
                required=schema.get("required", []),
            )
            tool_meta = ToolMeta(
                name=mcp_name,
                type=ToolType.MCP,
                description=tool.get("description", ""),
                config={"mcp_server": name, "mcp_tool": tool_name},
            )

            handler = _make_handler(name, tool_name)
            ToolRegistry.register_mcp(tool_def, handler, tool_meta)
            registered.append(mcp_name)

        self._tools[name] = registered
        logger.info("MCPLoader loaded %d tools from '%s'", len(registered), name)
        return registered

    async def unload_server(self, name: str):
        """卸载 MCP Server 的所有工具并关闭连接。"""
        for t in self._tools.pop(name, []):
            ToolRegistry.unregister(t)
        client = self._clients.pop(name, None)
        if client:
            await client.close()
        logger.info("MCPLoader unloaded '%s'", name)


def _make_handler(server_name: str, tool_name: str):
    """创建 MCP 工具调用 handler。"""
    async def handler(**kwargs):
        kwargs.pop("state", None)
        kwargs.pop("user_id", "")
        loader = get_mcp_loader()
        client = loader._clients.get(server_name)
        if not client:
            return f"MCP Server '{server_name}' 未连接"

        response = await client.call_tool(tool_name, kwargs)

        # JSON-RPC 错误
        rpc_err = response.get("error")
        if rpc_err:
            return f"MCP 调用错误: {rpc_err.get('message', rpc_err)}"

        # 工具执行结果
        result = response.get("result", {})
        texts = [
            item.get("text", "") for item in result.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        output = "\n".join(texts) if texts else str(result)
        if result.get("isError"):
            return f"MCP 工具执行失败: {output}"
        return output

    return handler
