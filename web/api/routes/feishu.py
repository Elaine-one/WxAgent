"""飞书工作台 API 路由"""
import asyncio
import logging
import time

from fastapi import APIRouter

from tools.registry import ToolRegistry

router = APIRouter(prefix="/api/feishu", tags=["feishu"])

logger = logging.getLogger("wxagent.api.feishu")

# 状态缓存（TTL 60s）
_status_cache: dict = {"data": None, "expires_at": 0}
_STATUS_CACHE_TTL = 60


@router.get("/status")
async def feishu_status(skip_token_test: bool = False):
    """获取飞书集成状态：配置、连接、工具列表。"""
    # 检查缓存
    now = time.time()
    if _status_cache["data"] and now < _status_cache["expires_at"]:
        return _status_cache["data"]

    from tools.builtin.feishu import is_configured, get_domain_cache, _get_tenant_token

    configured = is_configured()

    # 获取飞书 builtin 工具
    feishu_tools = []
    all_defs = ToolRegistry.get_all_defs()
    for t in all_defs:
        if t.name.startswith("feishu_"):
            feishu_tools.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "required": t.required,
            })

    # 测试 token 是否可用（带超时保护）
    token_ok = False
    token_error = ""
    if configured and not skip_token_test:
        try:
            token = await asyncio.wait_for(_get_tenant_token(), timeout=5.0)
            token_ok = bool(token)
        except asyncio.TimeoutError:
            token_error = "获取 token 超时"
        except Exception as e:
            token_error = str(e)

    feishu_domain = get_domain_cache() or "feishu"

    result = {
        "configured": configured,
        "feishu_domain": feishu_domain,
        "token_ok": token_ok,
        "token_error": token_error,
        "tools_count": len(feishu_tools),
        "tools": feishu_tools,
    }

    # 缓存结果
    _status_cache["data"] = result
    _status_cache["expires_at"] = now + _STATUS_CACHE_TTL

    return result


@router.post("/test-connection")
async def test_feishu_connection():
    """测试飞书 API 连接：获取 token + 访问云空间。"""
    from tools.builtin.feishu import is_configured, _get_tenant_token, _request

    if not is_configured():
        return {"success": False, "error": "FEISHU_APP_ID 或 FEISHU_APP_SECRET 未配置"}

    try:
        token = await _get_tenant_token()
        if not token:
            return {"success": False, "error": "获取 tenant_access_token 失败"}

        # 测试：获取应用云空间根目录
        try:
            data = await _request("GET", "/open-apis/drive/v1/files?folder_token=")
            if data.get("code") != 0:
                return {
                    "success": True,
                    "token_ok": True,
                    "drive_ok": False,
                    "warning": f"Token 有效但云空间访问失败: {data.get('msg', '')}",
                }
            files = data.get("data", {}).get("files", [])
            return {
                "success": True,
                "token_ok": True,
                "drive_ok": True,
                "root_files_count": len(files),
            }
        except Exception as e:
            return {
                "success": True,
                "token_ok": True,
                "drive_ok": False,
                "warning": f"Token 有效但云空间访问异常: {e}",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/documents")
async def list_feishu_documents(folder_token: str = "", page_size: int = 50):
    """列出飞书云空间中的文件/文档。"""
    from tools.builtin.feishu import _request

    try:
        params = {"page_size": str(page_size), "order_by": "EditedTime", "direction": "DESC"}
        if folder_token:
            params["folder_token"] = folder_token
        data = await _request("GET", "/open-apis/drive/v1/files", params=params)
        if data.get("code") != 0:
            return {"success": False, "error": data.get("msg", ""), "files": []}
        files = data.get("data", {}).get("files", [])
        return {"success": True, "files": files, "count": len(files)}
    except Exception as e:
        return {"success": False, "error": str(e), "files": []}


@router.get("/bitables")
async def list_feishu_bitables():
    """列出应用创建的多维表格（通过云空间文件列表过滤）。"""
    from tools.builtin.feishu import _request

    try:
        data = await _request(
            "GET", "/open-apis/drive/v1/files",
            params={"folder_token": "", "order_by": "EditedTime", "direction": "DESC", "page_size": "100"},
        )
        if data.get("code") != 0:
            return {"success": False, "error": data.get("msg", ""), "bitables": []}
        files = data.get("data", {}).get("files", [])
        # 过滤多维表格
        bitables = [f for f in files if f.get("type") == "bitable"]
        return {"success": True, "bitables": bitables, "count": len(bitables)}
    except Exception as e:
        return {"success": False, "error": str(e), "bitables": []}


@router.delete("/documents/{file_token}")
async def delete_feishu_document(file_token: str, file_type: str = "docx"):
    """删除飞书云空间中的文件/文档/表格。删除后进入回收站。"""
    from tools.builtin.feishu import _request

    try:
        data = await _request(
            "DELETE",
            f"/open-apis/drive/v1/files/{file_token}",
            params={"type": file_type},
        )
        if data.get("code") != 0:
            return {"success": False, "error": f"删除失败: {data.get('msg', '')}"}
        task_id = data.get("data", {}).get("task_id", "")
        return {"success": True, "task_id": task_id}
    except Exception as e:
        return {"success": False, "error": str(e)}
