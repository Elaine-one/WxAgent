from dataclasses import dataclass
import uuid

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass
class MCPError:
    code: int
    message: str
    data: dict | None = None

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


@dataclass
class MCPRequest:
    jsonrpc: str = "2.0"
    id: int | str = 0
    method: str = ""
    params: dict | None = None

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "id": self.id, "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        return d


@dataclass
class MCPResponse:
    jsonrpc: str = "2.0"
    id: int | str = 0
    result: dict | None = None
    error: dict | None = None

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


@dataclass
class MCPNotification:
    jsonrpc: str = "2.0"
    method: str = ""
    params: dict | None = None

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        return d


def create_request(method: str, params: dict | None = None, request_id: int | str | None = None) -> MCPRequest:
    if request_id is None:
        request_id = uuid.uuid4().int % (2**31)
    return MCPRequest(id=request_id, method=method, params=params)


def create_response(request_id: int | str, result: dict | None = None) -> MCPResponse:
    return MCPResponse(id=request_id, result=result)


def create_notification(method: str, params: dict | None = None) -> MCPNotification:
    return MCPNotification(method=method, params=params)


def create_error_response(request_id: int | str, code: int, message: str, data: dict | None = None) -> MCPResponse:
    error = MCPError(code=code, message=message, data=data)
    return MCPResponse(id=request_id, error=error.to_dict())
