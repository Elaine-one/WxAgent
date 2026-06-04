import asyncio
import json
import logging
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import uvicorn

from mcp_client.protocol import (
    create_response,
    create_error_response,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INTERNAL_ERROR,
    INVALID_PARAMS,
)
from mcp_client.transport import StdioTransport

logger = logging.getLogger("wxagent.mcp.server")


class MCPServer:
    def __init__(self, name: str = "wxagent-mcp-server", version: str = "1.0.0"):
        self.name = name
        self.version = version
        self._tool_handlers: dict[str, Callable] = {}
        self._tool_defs: dict[str, dict] = {}
        self._resource_handlers: dict[str, Callable] = {}
        self._resource_defs: dict[str, dict] = {}

    def register_tool_handler(self, name: str, handler: Callable, description: str = "", input_schema: dict | None = None):
        self._tool_handlers[name] = handler
        self._tool_defs[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema or {"type": "object", "properties": {}},
        }
        logger.debug("MCPServer registered tool: %s", name)

    async def handle_request(self, request: dict) -> dict | None:
        method = request.get("method", "")
        request_id = request.get("id")

        # JSON-RPC notifications (no id) should not receive a response
        if request_id is None:
            logger.debug("MCPServer received notification: %s", method)
            return None

        try:
            params = request.get("params")
            if method == "initialize":
                return self._handle_initialize(request_id, params)
            elif method == "tools/list":
                return self._handle_tools_list(request_id)
            elif method == "tools/call":
                return await self._handle_tools_call(request_id, params)
            elif method == "resources/list":
                return self._handle_resources_list(request_id)
            elif method == "resources/read":
                return await self._handle_resources_read(request_id, params)
            elif method == "ping":
                return create_response(request_id, result={}).to_dict()
            else:
                return create_error_response(request_id, METHOD_NOT_FOUND, f"Method not found: {method}").to_dict()
        except Exception as e:
            logger.exception("MCPServer handle_request error for method %s", method)
            return create_error_response(request_id, INTERNAL_ERROR, str(e)).to_dict()

    def _handle_initialize(self, request_id: int | str, params: dict | None) -> dict:
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }
        return create_response(request_id, result=result).to_dict()

    def _handle_tools_list(self, request_id: int | str) -> dict:
        tools = list(self._tool_defs.values())
        return create_response(request_id, result={"tools": tools}).to_dict()

    async def _handle_tools_call(self, request_id: int | str, params: dict | None) -> dict:
        if not params:
            return create_error_response(request_id, INVALID_PARAMS, "Missing params").to_dict()
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            return create_error_response(request_id, INVALID_PARAMS, f"Unknown tool: {tool_name}").to_dict()
        try:
            result = handler(**arguments)
            if asyncio.iscoroutine(result):
                result = await result
            content = [{"type": "text", "text": str(result)}]
            return create_response(request_id, result={"content": content}).to_dict()
        except Exception as e:
            logger.exception("MCPServer tool call error: %s", tool_name)
            content = [{"type": "text", "text": f"Error: {e}"}]
            return create_response(request_id, result={"content": content, "isError": True}).to_dict()

    def _handle_resources_list(self, request_id: int | str) -> dict:
        resources = list(self._resource_defs.values())
        return create_response(request_id, result={"resources": resources}).to_dict()

    async def _handle_resources_read(self, request_id: int | str, params: dict | None) -> dict:
        if not params:
            return create_error_response(request_id, INVALID_PARAMS, "Missing params").to_dict()
        uri = params.get("uri", "")
        handler = self._resource_handlers.get(uri)
        if handler is None:
            return create_error_response(request_id, INVALID_PARAMS, f"Unknown resource: {uri}").to_dict()
        try:
            result = handler()
            if asyncio.iscoroutine(result):
                result = await result
            contents = [{"uri": uri, "mimeType": "text/plain", "text": str(result)}]
            return create_response(request_id, result={"contents": contents}).to_dict()
        except Exception as e:
            logger.exception("MCPServer resource read error: %s", uri)
            return create_error_response(request_id, INTERNAL_ERROR, str(e)).to_dict()

    async def run_stdio(self):
        transport = StdioTransport()
        await transport.start()
        logger.info("MCPServer running on stdio")
        try:
            while True:
                try:
                    message = await transport.receive()
                except EOFError:
                    logger.info("MCPServer stdin closed")
                    break
                response = await self.handle_request(message)
                if response is not None:
                    await transport.send(response)
        except Exception as e:
            logger.exception("MCPServer stdio error: %s", e)
        finally:
            await transport.close()

    async def run_sse(self, host: str = "0.0.0.0", port: int = 8080):
        app = FastAPI(title=self.name)
        server = self
        sse_connections: list = []

        @app.get("/sse")
        async def sse_endpoint():
            import uuid as _uuid

            client_id = _uuid.uuid4().hex
            queue = asyncio.Queue()
            sse_connections.append({"id": client_id, "queue": queue})

            async def event_generator():
                yield f"event: endpoint\ndata: /message?client_id={client_id}\n\n"
                try:
                    while True:
                        msg = await queue.get()
                        yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.CancelledError:
                    pass
                finally:
                    sse_connections[:] = [c for c in sse_connections if c["id"] != client_id]

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        @app.post("/message")
        async def message_endpoint(request: Request):
            body = await request.json()
            response = await server.handle_request(body)
            client_id = request.query_params.get("client_id")
            if client_id:
                for conn in sse_connections:
                    if conn["id"] == client_id:
                        await conn["queue"].put(response)
                        break
            return Response(status_code=202)

        @app.get("/health")
        async def health():
            return {"status": "ok", "name": server.name, "version": server.version}

        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        uvicorn_server = uvicorn.Server(config)
        logger.info("MCPServer running SSE on %s:%d", host, port)
        await uvicorn_server.serve()
