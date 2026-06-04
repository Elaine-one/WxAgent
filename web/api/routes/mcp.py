from fastapi import APIRouter

from tools.registry import ToolRegistry

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


def _is_server_connected(name: str) -> bool:
    prefix = f"mcp_{name}_"
    return any(k.startswith(prefix) for k in ToolRegistry._mcp_handlers)


def _count_server_tools(name: str) -> int:
    prefix = f"mcp_{name}_"
    return sum(1 for k in ToolRegistry._mcp_handlers if k.startswith(prefix))


@router.get("/status")
async def mcp_status():
    import config as cfg
    servers = []
    connected_count = 0
    for name in cfg.MCP_SERVERS:
        is_connected = _is_server_connected(name)
        if is_connected:
            connected_count += 1
        servers.append({
            "name": name,
            "transport": cfg.MCP_SERVERS[name].get("transport", "stdio"),
            "status": "connected" if is_connected else "disconnected",
            "tools_count": _count_server_tools(name) if is_connected else 0,
        })
    return {
        "enabled": cfg.MCP_ENABLED,
        "servers_count": len(cfg.MCP_SERVERS),
        "connected_count": connected_count,
        "servers": servers,
    }


@router.get("/tools")
async def mcp_tools():
    mcp_tools = ToolRegistry.get_mcp_tools()
    tools_data = []
    for t in mcp_tools:
        meta = ToolRegistry.get_meta(t.name)
        server_name = meta.config.get("mcp_server", "") if meta and meta.config else ""
        tools_data.append({
            "name": t.name,
            "server": server_name,
            "description": t.description,
            "parameters": t.parameters,
            "required": t.required,
        })
    return {
        "tools": tools_data,
        "count": len(mcp_tools),
    }


@router.post("/connect/{server_name}")
async def connect_server(server_name: str):
    import config as cfg
    if server_name not in cfg.MCP_SERVERS:
        return {"success": False, "error": f"Server '{server_name}' not configured"}
    try:
        from mcp_client.loader import connect_server as mcp_connect
        result = await mcp_connect(server_name, cfg.MCP_SERVERS[server_name])

        # 刷新运行时工具列表，确保 LLM 能感知新 MCP 工具
        import tools as tools_mod
        tools_mod.refresh_runtime_tools()

        return {"success": True, "tools_loaded": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/disconnect/{server_name}")
async def disconnect_server(server_name: str):
    try:
        from mcp_client.loader import disconnect_server as mcp_disconnect
        try:
            await mcp_disconnect(server_name)
        except Exception:
            pass
        ToolRegistry.unregister_mcp(server_name)

        # 刷新运行时工具列表
        import tools as tools_mod
        tools_mod.refresh_runtime_tools()

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/toggle")
async def toggle_mcp(enabled: bool = True):
    import config as cfg
    cfg.MCP_ENABLED = enabled
    return {"success": True, "enabled": enabled}
