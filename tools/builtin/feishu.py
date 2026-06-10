"""飞书开放平台内置工具集

直接调用飞书 REST API，无需 MCP 子进程。
配置：在 .env 中设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET。
"""

import json
import logging
import os
import asyncio
import time

import httpx

from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.tools.feishu")

# ── 配置 ──────────────────────────────────────────────────────

FEISHU_BASE_URL = "https://open.feishu.cn"
_app_id = os.environ.get("FEISHU_APP_ID", "")
_app_secret = os.environ.get("FEISHU_APP_SECRET", "")
_token_cache: dict = {"token": "", "expires_at": 0}
_token_lock = asyncio.Lock()

# 文件类型 → URL 路径映射（降级拼接用）
_FILE_TYPE_PATH = {
    "docx": "docx",
    "doc": "docs",
    "bitable": "base",
    "sheet": "sheets",
    "folder": "drive/folder",
    "mindnote": "mindnote",
    "slide": "slides",
    "file": "file",
}

# 从 API 返回的 url 中提取的企业域名缓存
_domain_cache: str = ""


# ── Token 管理 ────────────────────────────────────────────────

def _get_http_client() -> httpx.AsyncClient:
    """创建新的 HTTP 客户端。每次创建新实例，避免绑定到已关闭的事件循环。"""
    return httpx.AsyncClient(timeout=30.0)


async def _get_tenant_token() -> str:
    """获取 tenant_access_token，带缓存（提前 5 分钟刷新）和并发锁保护。"""
    global _token_cache
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]
    async with _token_lock:
        # 双重检查：等待锁后再次确认
        if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["token"]
        async with _get_http_client() as client:
            resp = await client.post(
                f"{FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": _app_id, "app_secret": _app_secret},
            )
            data = resp.json()
    token = data.get("tenant_access_token", "")
    if not token:
        code = data.get("code", -1)
        msg = data.get("msg", "unknown error")
        raise RuntimeError(f"获取飞书 tenant_access_token 失败 (code={code}): {msg}")
    expire = data.get("expire", 7200)
    _token_cache["token"] = token
    _token_cache["expires_at"] = time.time() + expire - 300
    logger.info("飞书 tenant_access_token 已刷新，有效期 %ds", expire)
    return token


async def _request(method: str, path: str, **kwargs) -> dict:
    """发送飞书 API 请求，自动附加 Authorization 头。"""
    token = await _get_tenant_token()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    if method.upper() != "DELETE" and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
    async with _get_http_client() as client:
        resp = await client.request(
            method, f"{FEISHU_BASE_URL}{path}", headers=headers, **kwargs
        )
    return resp.json()


def _check_config() -> ToolResult | None:
    """检查飞书配置是否完整。"""
    if not _app_id or not _app_secret:
        return ToolResult(
            success=False,
            error="飞书未配置。请在 .env 中设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET。",
        )
    return None


def _extract_domain_from_url(url: str) -> str:
    """从 URL 中提取企业域名前缀，如 https://pcnp42xbruvl.feishu.cn → pcnp42xbruvl"""
    try:
        # url 格式: https://xxx.feishu.cn/...
        host = url.split("//")[1].split("/")[0]  # xxx.feishu.cn
        prefix = host.split(".")[0]  # xxx
        if prefix and prefix != "open":
            return prefix
    except Exception as e:
        logger.debug("extract_domain failed: %s", e)
    return ""


async def _get_doc_url(document_id: str, file_type: str = "docx") -> str:
    """获取文档的可访问 URL。

    优先使用 metas/batch_query API 获取（with_url=true），
    降级使用 drive/v1/files API，
    最后降级使用已缓存的企业域名拼接。
    """
    global _domain_cache

    # 方式1：使用 metas/batch_query 获取 URL（最可靠）
    try:
        data = await _request(
            "POST",
            "/open-apis/drive/v1/metas/batch_query",
            json={
                "request_docs": [{"doc_token": document_id, "doc_type": file_type}],
                "with_url": True,
            },
        )
        if data.get("code") == 0:
            metas = data.get("data", {}).get("metas", [])
            if metas:
                url = metas[0].get("url", "")
                if url:
                    # 缓存企业域名
                    domain = _extract_domain_from_url(url)
                    if domain:
                        _domain_cache = domain
                    return url
    except Exception as e:
        logger.debug("get_doc_url via metas failed: %s", e)
    try:
        data = await _request("GET", f"/open-apis/drive/v1/files/{document_id}")
        if data.get("code") == 0:
            url = data.get("data", {}).get("url", "")
            if url:
                domain = _extract_domain_from_url(url)
                if domain:
                    _domain_cache = domain
                return url
    except Exception as e:
        logger.debug("get_doc_url via drive failed: %s", e)
    domain = _domain_cache or "feishu"
    path = _FILE_TYPE_PATH.get(file_type, "docx")
    return f"https://{domain}.feishu.cn/{path}/{document_id}"


async def _set_public_sharing(token: str, file_type: str = "docx") -> bool:
    """设置文档/表格为组织内可通过链接访问。

    tenant_access_token 创建的文档归属应用，用户默认无法访问。
    设置公开分享后，组织内用户可通过链接查看。
    使用 PATCH 方法更新权限设置。
    """
    try:
        data = await _request(
            "PATCH",
            f"/open-apis/drive/v1/permissions/{token}/public?type={file_type}",
            json={
                "external_access": True,
                "security_entity": "anyone_can_view",
                "comment_entity": "anyone_can_view",
                "share_entity": "anyone",
                "link_share_entity": "tenant_editable",
                "invite_external": True,
            },
        )
        return data.get("code") == 0
    except Exception as e:
        logger.warning("设置公开分享失败 (%s): %s", token, e)
        return False


# ── 块类型映射（简化 LLM 输入 → 飞书 API Block 结构）─────────

_BLOCK_TYPE_MAP = {
    "text": 2,
    "heading1": 3,
    "heading2": 4,
    "heading3": 5,
    "heading4": 6,
    "heading5": 7,
    "heading6": 8,
    "heading7": 9,
    "heading8": 10,
    "heading9": 11,
    "bullet": 12,
    "ordered": 13,
    "code": 14,
    "quote": 15,
    "todo": 17,
    "divider": 22,
}


def _build_block(block_type: str, content: str, language: str = "") -> dict:
    """将简化的块描述转换为飞书 API 要求的 Block 结构。"""
    bt = _BLOCK_TYPE_MAP.get(block_type, 2)
    elements = [{"text_run": {"content": content}}]

    if block_type == "code":
        return {
            "block_type": bt,
            "code": {
                "elements": elements,
                "language": language or "PlainText",
            },
        }
    elif block_type == "divider":
        return {"block_type": bt, "divider": {}}
    elif block_type.startswith("heading"):
        level = block_type.replace("heading", "")
        return {f"heading{level}": {"elements": elements}, "block_type": bt}
    elif block_type == "bullet":
        return {"block_type": bt, "bullet": {"elements": elements}}
    elif block_type == "ordered":
        return {"block_type": bt, "ordered": {"elements": elements}}
    elif block_type == "quote":
        return {"block_type": bt, "quote": {"elements": elements}}
    elif block_type == "todo":
        return {"block_type": bt, "todo": {"elements": elements}}
    else:
        return {"block_type": bt, "text": {"elements": elements}}


# ── 工具函数 ──────────────────────────────────────────────────

# --- 消息类 ---

async def _feishu_send_message(
    receive_id: str, msg_type: str = "text", content: str = "",
    state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        body = {"receive_id": receive_id, "msg_type": msg_type, "content": content}
        data = await _request(
            "POST", "/open-apis/im/v1/messages?receive_id_type=open_id", json=body
        )
        if data.get("code") != 0:
            return ToolResult(success=False, error=f"发送失败: {data.get('msg', '')}")
        return ToolResult(success=True, content="消息发送成功", display="飞书消息已发送")
    except Exception as e:
        logger.exception("feishu_send_message failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_send_group_message(
    chat_id: str, msg_type: str = "text", content: str = "",
    state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        body = {"receive_id": chat_id, "msg_type": msg_type, "content": content}
        data = await _request(
            "POST", "/open-apis/im/v1/messages?receive_id_type=chat_id", json=body
        )
        if data.get("code") != 0:
            return ToolResult(success=False, error=f"发送失败: {data.get('msg', '')}")
        return ToolResult(success=True, content="群消息发送成功", display="飞书群消息已发送")
    except Exception as e:
        logger.exception("feishu_send_group_message failed")
        return ToolResult(success=False, error=str(e))


# --- 文档类 ---

async def _feishu_create_document(
    title: str, folder_token: str = "", state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        body = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        data = await _request("POST", "/open-apis/docx/v1/documents", json=body)
        if data.get("code") != 0:
            return ToolResult(success=False, error=f"创建文档失败: {data.get('msg', '')}")

        doc_info = data.get("data", {}).get("document", {})
        document_id = doc_info.get("document_id", "")

        # 设置公开分享，让组织内用户可通过链接访问
        sharing_ok = await _set_public_sharing(document_id, "docx")

        url = await _get_doc_url(document_id, "docx") if document_id else ""
        sharing_note = "\n已设置公开分享，组织内用户可通过链接访问。" if sharing_ok else "\n注意：未设置公开分享，你可能需要在飞书中手动添加权限。"

        result = f"文档创建成功！\n标题: {title}\n文档ID: {document_id}\n链接: {url}{sharing_note}"
        return ToolResult(success=True, content=result, display=f"飞书文档已创建: {title}")
    except Exception as e:
        logger.exception("feishu_create_document failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_get_document(
    document_id: str, state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        data = await _request(
            "GET", f"/open-apis/docx/v1/documents/{document_id}/raw_content"
        )
        if data.get("code") != 0:
            return ToolResult(success=False, error=f"获取文档失败: {data.get('msg', '')}")
        content = data.get("data", {}).get("content", "")
        return ToolResult(success=True, content=content, display="飞书文档内容已获取")
    except Exception as e:
        logger.exception("feishu_get_document failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_add_document_blocks(
    document_id: str,
    blocks: list,
    state=None,
    user_id: str = "",
) -> ToolResult:
    """向文档添加内容块。blocks 参数为内容块数组，格式：
    [{"block_type":"text","content":"文本"},{"block_type":"heading1","content":"标题"}]
    支持的 block_type: text, heading1-9, bullet, ordered, code, quote, todo, divider
    code 块可额外传 "language" 字段。
    """
    if err := _check_config():
        return err
    try:
        # 兼容字符串输入（LLM 可能仍传 JSON 字符串）
        if isinstance(blocks, str):
            try:
                blocks_list = json.loads(blocks)
            except json.JSONDecodeError as e:
                return ToolResult(
                    success=False,
                    error=f"blocks JSON 解析失败: {e}。请确保传入完整的 JSON 数组。",
                )
        else:
            blocks_list = blocks
        if not isinstance(blocks_list, list):
            return ToolResult(success=False, error="blocks 参数必须是数组")
        if not blocks_list:
            return ToolResult(success=False, error="blocks 数组不能为空")
        children = []
        for b in blocks_list:
            if not isinstance(b, dict):
                continue
            bt = b.get("block_type", "text")
            content = b.get("content", "")
            language = b.get("language", "")
            # 校验 block_type，未知类型降级为 text
            if bt not in _BLOCK_TYPE_MAP:
                bt = "text"
            # divider 不需要 content
            if bt == "divider":
                content = ""
            # 非 divider 必须有 content
            elif not content:
                content = " "
            children.append(_build_block(bt, content, language))

        if not children:
            return ToolResult(success=False, error="没有有效的内容块可添加")

        # 分批提交（飞书 API 单次限制 50 个 block）
        BATCH_SIZE = 50
        total_added = 0
        for i in range(0, len(children), BATCH_SIZE):
            batch = children[i:i + BATCH_SIZE]
            data = await _request(
                "POST",
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                json={"children": batch},
            )
            if data.get("code") != 0:
                return ToolResult(
                    success=False, error=f"添加内容块失败: {data.get('msg', '')}"
                )
            total_added += len(data.get("data", {}).get("children", []))
        return ToolResult(
            success=True,
            content=f"成功添加 {total_added} 个内容块到文档",
            display=f"飞书文档内容已更新（+{total_added}块）",
        )
    except Exception as e:
        logger.exception("feishu_add_document_blocks failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_get_document_blocks(
    document_id: str, page_size: int = 500, state=None, user_id: str = ""
) -> ToolResult:
    """获取飞书文档的所有块信息，包括 block_id、类型和内容摘要。
    返回的 block_id 可用于 feishu_update_document_block 和 feishu_delete_document_block。
    """
    if err := _check_config():
        return err
    try:
        all_blocks = []
        page_token = ""
        while True:
            params = {
                "page_size": str(min(page_size, 500)),
                "document_revision_id": "-1",
            }
            if page_token:
                params["page_token"] = page_token
            data = await _request(
                "GET",
                f"/open-apis/docx/v1/documents/{document_id}/blocks",
                params=params,
            )
            if data.get("code") != 0:
                return ToolResult(
                    success=False, error=f"获取文档块失败: {data.get('msg', '')}"
                )
            items = data.get("data", {}).get("items", [])
            all_blocks.extend(items)
            page_token = data.get("data", {}).get("page_token", "")
            if not page_token or not items:
                break

        if not all_blocks:
            return ToolResult(success=True, content="文档暂无内容块")

        # 格式化输出：提取关键信息
        lines = [f"文档共 {len(all_blocks)} 个块：\n"]
        for b in all_blocks:
            block_id = b.get("block_id", "")
            block_type = b.get("block_type", "")
            # 提取文本内容摘要
            text_preview = _extract_block_text(b, max_len=80)
            lines.append(
                f"- block_id: {block_id} | type: {block_type} | {text_preview}"
            )
        return ToolResult(
            success=True,
            content="\n".join(lines),
            display=f"获取到 {len(all_blocks)} 个文档块",
        )
    except Exception as e:
        logger.exception("feishu_get_document_blocks failed")
        return ToolResult(success=False, error=str(e))


def _extract_block_text(block: dict, max_len: int = 80) -> str:
    """从块结构中提取文本内容摘要。"""
    # 遍历块的各个可能包含文本的字段
    for key in (
        "text", "heading1", "heading2", "heading3", "heading4",
        "heading5", "heading6", "heading7", "heading8", "heading9",
        "bullet", "ordered", "code", "quote", "todo", "callout",
    ):
        section = block.get(key)
        if section and isinstance(section, dict):
            elements = section.get("elements", [])
            texts = []
            for el in elements:
                text_run = el.get("text_run", {})
                content = text_run.get("content", "")
                if content:
                    texts.append(content)
            if texts:
                full = "".join(texts)
                if len(full) > max_len:
                    return full[:max_len] + "..."
                return full
    return ""


async def _feishu_update_document_block(
    document_id: str,
    block_id: str,
    block_type: str = "",
    content: str = "",
    language: str = "",
    state=None,
    user_id: str = "",
) -> ToolResult:
    """更新飞书文档中指定块的内容。需要提供 block_id（可通过 feishu_get_document_blocks 获取）。
    block_type 和 content 用于构建更新内容，支持的 block_type 同 feishu_add_document_blocks。
    """
    if err := _check_config():
        return err
    try:
        if not content and not block_type:
            return ToolResult(
                success=False, error="必须提供 content 参数"
            )
        # 构建更新请求体 — 单块 PATCH 接口直接传操作字段，不需要 requests 数组
        update_body = {}
        if content:
            elements = [{"text_run": {"content": content}}]
            update_body["update_text_elements"] = {"elements": elements}

        data = await _request(
            "PATCH",
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}",
            json=update_body,
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"更新块失败: {data.get('msg', '')}"
            )
        return ToolResult(
            success=True,
            content=f"块 {block_id} 更新成功",
            display="飞书文档块已更新",
        )
    except Exception as e:
        logger.exception("feishu_update_document_block failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_batch_update_blocks(
    document_id: str,
    updates: list,
    state=None,
    user_id: str = "",
) -> ToolResult:
    """批量更新飞书文档中多个块的内容。updates 为更新数组，每个元素包含 block_id、content 和可选的 block_type。
    示例: [{"block_id":"xxx","content":"新内容","block_type":"text"}]
    单次最多更新 200 个块。
    """
    if err := _check_config():
        return err
    try:
        if not updates:
            return ToolResult(success=False, error="updates 数组不能为空")
        if len(updates) > 200:
            return ToolResult(success=False, error="单次最多更新 200 个块")

        requests = []
        for u in updates:
            if not isinstance(u, dict):
                continue
            block_id = u.get("block_id", "")
            content = u.get("content", "")
            if not block_id:
                continue
            update_req = {"block_id": block_id}
            if content:
                elements = [{"text_run": {"content": content}}]
                update_req["update_text_elements"] = {"elements": elements}
            requests.append(update_req)

        if not requests:
            return ToolResult(success=False, error="没有有效的更新请求")

        data = await _request(
            "PATCH",
            f"/open-apis/docx/v1/documents/{document_id}/blocks/batch_update",
            json={"requests": requests},
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"批量更新块失败: {data.get('msg', '')}"
            )
        return ToolResult(
            success=True,
            content=f"批量更新 {len(requests)} 个块成功",
            display=f"飞书文档已批量更新 {len(requests)} 个块",
        )
    except Exception as e:
        logger.exception("feishu_batch_update_blocks failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_delete_document_block(
    document_id: str, block_id: str, state=None, user_id: str = ""
) -> ToolResult:
    """删除飞书文档中指定的块。需要提供 block_id（可通过 feishu_get_document_blocks 获取）。
    注意：删除操作不可撤销。
    """
    if err := _check_config():
        return err
    try:
        data = await _request(
            "DELETE",
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}",
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"删除块失败: {data.get('msg', '')}"
            )
        return ToolResult(
            success=True,
            content=f"块 {block_id} 已删除",
            display="飞书文档块已删除",
        )
    except Exception as e:
        logger.exception("feishu_delete_document_block failed")
        return ToolResult(success=False, error=str(e))


# --- 多维表格类 ---

async def _feishu_create_bitable(
    name: str, folder_token: str = "", state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        body = {"name": name}
        if folder_token:
            body["folder_token"] = folder_token
        data = await _request("POST", "/open-apis/bitable/v1/apps", json=body)
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"创建多维表格失败: {data.get('msg', '')}"
            )
        app = data.get("data", {}).get("app", {})
        app_token = app.get("app_token", "")
        table_id = app.get("default_table_id", "")
        url = app.get("url", "")
        if url:
            domain = _extract_domain_from_url(url)
            if domain:
                _domain_cache = domain
        if not url:
            domain = _domain_cache or "feishu"
            url = f"https://{domain}.feishu.cn/base/{app_token}"

        # 设置公开分享，让组织内用户可通过链接访问
        sharing_ok = await _set_public_sharing(app_token, "bitable")
        sharing_note = "\n已设置公开分享，组织内用户可通过链接访问。" if sharing_ok else "\n注意：未设置公开分享，你可能需要在飞书中手动添加权限。"

        result = (
            f"多维表格创建成功！\n"
            f"名称: {name}\n"
            f"app_token: {app_token}\n"
            f"默认数据表ID: {table_id}\n"
            f"链接: {url}{sharing_note}"
        )
        return ToolResult(
            success=True, content=result, display=f"飞书多维表格已创建: {name}"
        )
    except Exception as e:
        logger.exception("feishu_create_bitable failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_list_bitable_tables(
    app_token: str, page_size: int = 20, state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        data = await _request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables",
            params={"page_size": str(page_size)},
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"获取数据表列表失败: {data.get('msg', '')}"
            )
        tables = data.get("data", {}).get("items", [])
        if not tables:
            return ToolResult(success=True, content="该多维表格暂无数据表")
        lines = []
        for t in tables:
            lines.append(f"- {t.get('name', '')} (table_id: {t.get('table_id', '')})")
        return ToolResult(
            success=True,
            content="\n".join(lines),
            display=f"共 {len(tables)} 个数据表",
        )
    except Exception as e:
        logger.exception("feishu_list_bitable_tables failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_create_bitable_table(
    app_token: str, table_name: str, fields: str = "",
    state=None, user_id: str = ""
) -> ToolResult:
    """在多维表格中创建数据表。fields 为 JSON 字符串，格式：
    [{"field_name":"名称","field_type":1}]
    field_type: 1=多行文本, 2=数字, 3=单选, 4=多选, 5=日期, 7=复选框, 11=人员, 13=电话, 15=URL, 17=公式
    不传 fields 则创建空数据表。
    """
    if err := _check_config():
        return err
    try:
        body: dict = {"table": {"name": table_name}}
        if fields:
            fields_list = json.loads(fields) if isinstance(fields, str) else fields
            body["table"]["fields"] = fields_list
        data = await _request(
            "POST", f"/open-apis/bitable/v1/apps/{app_token}/tables", json=body
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"创建数据表失败: {data.get('msg', '')}"
            )
        table_info = data.get("data", {}).get("table", {})
        table_id = table_info.get("table_id", "")
        return ToolResult(
            success=True,
            content=f"数据表创建成功！\n名称: {table_name}\ntable_id: {table_id}",
            display=f"飞书数据表已创建: {table_name}",
        )
    except json.JSONDecodeError:
        return ToolResult(success=False, error="fields 参数 JSON 格式错误")
    except Exception as e:
        logger.exception("feishu_create_bitable_table failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_list_bitable(
    app_token: str, table_id: str, page_size: int = 20,
    state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        data = await _request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            params={"page_size": str(page_size)},
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"获取记录失败: {data.get('msg', '')}"
            )
        items = data.get("data", {}).get("items", [])
        if not items:
            return ToolResult(success=True, content="暂无记录")
        # 格式化记录为可读文本
        lines = []
        for i, item in enumerate(items, 1):
            fields = item.get("fields", {})
            record_id = item.get("record_id", "")
            field_strs = [f"{k}: {v}" for k, v in fields.items()]
            lines.append(f"[{i}] record_id={record_id} | {' | '.join(field_strs)}")
        return ToolResult(
            success=True,
            content="\n".join(lines),
            display=f"共 {len(items)} 条记录",
        )
    except Exception as e:
        logger.exception("feishu_list_bitable failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_add_bitable_records(
    app_token: str, table_id: str, records: str,
    state=None, user_id: str = ""
) -> ToolResult:
    """向多维表格添加记录。records 为 JSON 字符串，格式：
    [{"fields":{"姓名":"张三","年龄":25}},{"fields":{"姓名":"李四","年龄":30}}]
    使用批量接口一次性插入。
    """
    if err := _check_config():
        return err
    try:
        records_list = json.loads(records) if isinstance(records, str) else records
        # 使用批量创建接口
        data = await _request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            json={"records": records_list},
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"批量添加记录失败: {data.get('msg', '')}"
            )
        added = data.get("data", {}).get("records", [])
        return ToolResult(
            success=True,
            content=f"成功添加 {len(added)} 条记录",
            display=f"飞书多维表格记录已添加（{len(added)}条）",
        )
    except json.JSONDecodeError:
        return ToolResult(success=False, error="records 参数 JSON 格式错误")
    except Exception as e:
        logger.exception("feishu_add_bitable_records failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_add_bitable_field(
    app_token: str, table_id: str, field_name: str, field_type: int = 1,
    field_property: str = "", state=None, user_id: str = ""
) -> ToolResult:
    """向多维表格添加字段。field_type: 1=多行文本, 2=数字, 3=单选, 4=多选, 5=日期, 7=复选框, 11=人员, 15=URL, 17=公式
    field_property 为可选 JSON 字符串，如单选字段: {"options":[{"name":"选项1"},{"name":"选项2"}]}
    """
    if err := _check_config():
        return err
    try:
        body: dict = {"field_name": field_name, "field_type": field_type}
        if field_property:
            body["property"] = (
                json.loads(field_property)
                if isinstance(field_property, str)
                else field_property
            )
        data = await _request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            json=body,
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"添加字段失败: {data.get('msg', '')}"
            )
        field_info = data.get("data", {}).get("field", {})
        field_id = field_info.get("field_id", "")
        return ToolResult(
            success=True,
            content=f"字段添加成功！\n字段名: {field_name}\nfield_id: {field_id}",
            display=f"飞书多维表格字段已添加: {field_name}",
        )
    except json.JSONDecodeError:
        return ToolResult(success=False, error="field_property 参数 JSON 格式错误")
    except Exception as e:
        logger.exception("feishu_add_bitable_field failed")
        return ToolResult(success=False, error=str(e))


# --- 云空间类 ---

async def _feishu_create_folder(
    name: str, folder_token: str = "", state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        body = {"name": name}
        if folder_token:
            body["folder_token"] = folder_token
        data = await _request(
            "POST", "/open-apis/drive/v1/files/create_folder", json=body
        )
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"创建文件夹失败: {data.get('msg', '')}"
            )
        token = data.get("data", {}).get("token", "")
        url = data.get("data", {}).get("url", "")
        result = f"文件夹创建成功！\n名称: {name}\nfolder_token: {token}\n链接: {url}"
        return ToolResult(
            success=True, content=result, display=f"飞书文件夹已创建: {name}"
        )
    except Exception as e:
        logger.exception("feishu_create_folder failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_list_folder(
    folder_token: str = "", page_size: int = 20,
    state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        params: dict = {"page_size": str(page_size)}
        if folder_token:
            params["folder_token"] = folder_token
        data = await _request("GET", "/open-apis/drive/v1/files", params=params)
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"获取文件夹内容失败: {data.get('msg', '')}"
            )
        files = data.get("data", {}).get("files", [])
        if not files:
            return ToolResult(success=True, content="文件夹为空")
        lines = []
        for f in files:
            name = f.get("name", "")
            ftype = f.get("type", "")
            token = f.get("token", "")
            lines.append(f"- {name} (类型: {ftype}, token: {token})")
        return ToolResult(
            success=True,
            content="\n".join(lines),
            display=f"共 {len(files)} 个文件/文件夹",
        )
    except Exception as e:
        logger.exception("feishu_list_folder failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_upload_file(
    file_path: str, parent_node: str, file_name: str = "",
    state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        import pathlib

        p = pathlib.Path(file_path)
        if not p.exists():
            return ToolResult(success=False, error=f"文件不存在: {file_path}")
        name = file_name or p.name
        token = await _get_tenant_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(p, "rb") as f:
                resp = await client.post(
                    f"{FEISHU_BASE_URL}/open-apis/drive/v1/medias/upload_all",
                    headers=headers,
                    data={"parent_node": parent_node, "file_name": name},
                    files={"file": (name, f)},
                )
        data = resp.json()
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"上传文件失败: {data.get('msg', '')}"
            )
        file_token = data.get("data", {}).get("file_token", "")
        return ToolResult(
            success=True,
            content=f"文件上传成功！\n文件名: {name}\nfile_token: {file_token}",
            display=f"飞书文件已上传: {name}",
        )
    except Exception as e:
        logger.exception("feishu_upload_file failed")
        return ToolResult(success=False, error=str(e))


# --- 日历类 ---

async def _feishu_list_calendar(
    start_time: str, end_time: str, calendar_id: str = "",
    page_size: int = 50, state=None, user_id: str = ""
) -> ToolResult:
    if err := _check_config():
        return err
    try:
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "page_size": str(page_size),
        }
        if calendar_id:
            path = f"/open-apis/calendar/v4/calendars/{calendar_id}/events"
        else:
            path = "/open-apis/calendar/v4/events"
        data = await _request("GET", path, params=params)
        if data.get("code") != 0:
            return ToolResult(
                success=False, error=f"获取日历事件失败: {data.get('msg', '')}"
            )
        events = data.get("data", {}).get("items", [])
        if not events:
            return ToolResult(success=True, content="该时间段无日历事件")
        lines = []
        for ev in events:
            summary = ev.get("summary", "")
            start = ev.get("start_time", "")
            end = ev.get("end_time", "")
            lines.append(f"- {summary} ({start} ~ {end})")
        return ToolResult(
            success=True,
            content="\n".join(lines),
            display=f"共 {len(events)} 个日历事件",
        )
    except Exception as e:
        logger.exception("feishu_list_calendar failed")
        return ToolResult(success=False, error=str(e))


# --- 云空间文件管理类 ---

async def _feishu_delete_file(
    file_token: str, file_type: str = "docx", state=None, user_id: str = ""
) -> ToolResult:
    """删除飞书云空间中的文件/文档/表格。删除后进入回收站。"""
    if err := _check_config():
        return err
    try:
        data = await _request(
            "DELETE",
            f"/open-apis/drive/v1/files/{file_token}",
            params={"type": file_type},
        )
        if data.get("code") != 0:
            return ToolResult(success=False, error=f"删除失败: {data.get('msg', '')}")
        task_id = data.get("data", {}).get("task_id", "")
        result = f"删除成功！文件已移入回收站。"
        if task_id:
            result += f"\n异步任务ID: {task_id}（文件夹删除为异步操作）"
        return ToolResult(success=True, content=result, display="飞书文件已删除")
    except Exception as e:
        logger.exception("feishu_delete_file failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_copy_file(
    file_token: str, folder_token: str, name: str,
    file_type: str = "docx", state=None, user_id: str = ""
) -> ToolResult:
    """复制飞书云空间中的文件到指定文件夹。"""
    if err := _check_config():
        return err
    try:
        body = {"name": name, "folder_token": folder_token, "type": file_type}
        data = await _request(
            "POST",
            f"/open-apis/drive/v1/files/{file_token}/copy",
            json=body,
        )
        if data.get("code") != 0:
            return ToolResult(success=False, error=f"复制失败: {data.get('msg', '')}")
        copy_token = data.get("data", {}).get("file_token", "")
        url = await _get_doc_url(copy_token, file_type) if copy_token else ""
        return ToolResult(
            success=True,
            content=f"复制成功！\n新文件 token: {copy_token}\n链接: {url}",
            display=f"飞书文件已复制: {name}",
        )
    except Exception as e:
        logger.exception("feishu_copy_file failed")
        return ToolResult(success=False, error=str(e))


async def _feishu_move_file(
    file_token: str, folder_token: str,
    file_type: str = "docx", state=None, user_id: str = ""
) -> ToolResult:
    """移动飞书云空间中的文件到指定文件夹。"""
    if err := _check_config():
        return err
    try:
        body = {"folder_token": folder_token, "type": file_type}
        data = await _request(
            "POST",
            f"/open-apis/drive/v1/files/{file_token}/move",
            json=body,
        )
        if data.get("code") != 0:
            return ToolResult(success=False, error=f"移动失败: {data.get('msg', '')}")
        return ToolResult(
            success=True,
            content=f"移动成功！\n文件 token: {file_token}\n目标文件夹: {folder_token}",
            display="飞书文件已移动",
        )
    except Exception as e:
        logger.exception("feishu_move_file failed")
        return ToolResult(success=False, error=str(e))


# --- 权限类 ---

async def _feishu_add_permission(
    token: str, file_type: str = "docx", member_type: str = "openid",
    member_id: str = "", perm: str = "edit",
    state=None, user_id: str = ""
) -> ToolResult:
    """给飞书文档/表格添加协作者权限。

    使用 tenant_access_token 创建的文档归属应用，用户默认无法访问。
    通过此工具添加协作者后，指定用户即可访问。

    也可以设置公开分享（不指定 member_id 时自动设置公开链接分享）。
    """
    if err := _check_config():
        return err
    try:
        if not member_id:
            # 不指定用户时，设置公开链接分享
            ok = await _set_public_sharing(token, file_type)
            if ok:
                return ToolResult(
                    success=True,
                    content=f"已设置公开分享，组织内用户可通过链接访问和编辑。\ntoken: {token}\ntype: {file_type}",
                    display="飞书文档已设置公开分享",
                )
            else:
                return ToolResult(
                    success=False,
                    error="设置公开分享失败，可能缺少权限管理 API 权限。请在飞书开发者后台开通 drive:permission 权限。",
                )
        else:
            # 添加指定协作者
            data = await _request(
                "POST",
                f"/open-apis/drive/v1/permissions/{token}/members?type={file_type}",
                json={
                    "member_type": member_type,
                    "member_id": member_id,
                    "perm": perm,
                },
            )
            if data.get("code") != 0:
                return ToolResult(
                    success=False,
                    error=f"添加权限失败: {data.get('msg', '')}。提示：确保应用已开通 drive:permission 权限，且 member_id 正确。",
                )
            return ToolResult(
                success=True,
                content=f"权限添加成功！\ntoken: {token}\n协作者: {member_id} ({member_type})\n权限: {perm}",
                display=f"飞书文档权限已添加: {perm}",
            )
    except Exception as e:
        logger.exception("feishu_add_permission failed")
        return ToolResult(success=False, error=str(e))


# ── 注册工具 ──────────────────────────────────────────────────

TOOL_META = ToolMeta(
    name="feishu",
    type=ToolType.BUILTIN,
    description="飞书开放平台工具集：文档、多维表格、云空间、消息、日历",
    version="2.0.0",
    tags=["feishu", "lark", "document", "bitable", "drive"],
)

# --- 消息类 ---

ToolRegistry.register(
    ToolDef(
        name="feishu_send_message",
        description="发送消息给飞书用户。需要用户的 open_id。",
        parameters={
            "receive_id": {"type": "string", "description": "接收者的 open_id"},
            "msg_type": {"type": "string", "description": "消息类型，默认 text", "default": "text"},
            "content": {"type": "string", "description": "消息内容（文本消息直接传字符串，富文本传 JSON）"},
        },
        required=["receive_id", "content"],
    ),
    _feishu_send_message,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_send_group_message",
        description="发送消息到飞书群聊。需要群聊的 chat_id。",
        parameters={
            "chat_id": {"type": "string", "description": "群聊 ID"},
            "msg_type": {"type": "string", "description": "消息类型，默认 text", "default": "text"},
            "content": {"type": "string", "description": "消息内容"},
        },
        required=["chat_id", "content"],
    ),
    _feishu_send_group_message,
)

# --- 文档类 ---

ToolRegistry.register(
    ToolDef(
        name="feishu_create_document",
        description="创建飞书文档并返回可访问的链接。创建后可用 feishu_add_document_blocks 添加内容。",
        parameters={
            "title": {"type": "string", "description": "文档标题"},
            "folder_token": {"type": "string", "description": "目标文件夹 token，空字符串表示根目录"},
        },
        required=["title"],
    ),
    _feishu_create_document,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_get_document",
        description="获取飞书文档的纯文本内容。",
        parameters={
            "document_id": {"type": "string", "description": "文档 ID"},
        },
        required=["document_id"],
    ),
    _feishu_get_document,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_add_document_blocks",
        description=(
            "向飞书文档末尾追加内容块。注意：此工具只能追加新内容，不能修改或删除已有内容。"
            "如需修改已有内容，请用 feishu_update_document_block；如需删除内容，请用 feishu_delete_document_block。"
            "blocks 为内容块数组，每个元素包含 block_type 和 content。"
            "支持的 block_type: text, heading1-9, bullet, ordered, code, quote, todo, divider。"
            "code 块可额外传 language 字段。"
            "示例: [{\"block_type\":\"text\",\"content\":\"文本\"},{\"block_type\":\"heading1\",\"content\":\"标题\"}]"
        ),
        parameters={
            "document_id": {"type": "string", "description": "文档 ID"},
            "blocks": {
                "type": "array",
                "description": "内容块数组",
                "items": {
                    "type": "object",
                    "properties": {
                        "block_type": {
                            "type": "string",
                            "description": "块类型: text, heading1-9, bullet, ordered, code, quote, todo, divider",
                        },
                        "content": {
                            "type": "string",
                            "description": "块内容文本（divider 类型不需要）",
                        },
                        "language": {
                            "type": "string",
                            "description": "代码块语言（仅 code 类型需要），如 python, javascript",
                        },
                    },
                    "required": ["block_type", "content"],
                },
            },
        },
        required=["document_id", "blocks"],
    ),
    _feishu_add_document_blocks,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_get_document_blocks",
        description="获取飞书文档的所有块信息，包括 block_id、类型和内容摘要。返回的 block_id 可用于更新或删除块。用于二次编辑文档前获取块结构。",
        parameters={
            "document_id": {"type": "string", "description": "文档 ID"},
            "page_size": {
                "type": "integer",
                "description": "每页数量，默认 500（最大 500）",
                "default": 500,
            },
        },
        required=["document_id"],
    ),
    _feishu_get_document_blocks,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_update_document_block",
        description="更新飞书文档中指定块的内容。需要先通过 feishu_get_document_blocks 获取 block_id。用于二次编辑文档时修改已有内容。注意：此工具每次只能更新一个块，如需批量更新多个块，请使用 feishu_batch_update_blocks。",
        parameters={
            "document_id": {"type": "string", "description": "文档 ID"},
            "block_id": {"type": "string", "description": "要更新的块 ID"},
            "block_type": {
                "type": "string",
                "description": "块类型: text, heading1-9, bullet, ordered, code, quote, todo, divider",
            },
            "content": {"type": "string", "description": "新的块内容文本"},
            "language": {
                "type": "string",
                "description": "代码块语言（仅 code 类型需要）",
            },
        },
        required=["document_id", "block_id"],
    ),
    _feishu_update_document_block,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_batch_update_blocks",
        description="批量更新飞书文档中多个块的内容。每个更新项需包含 block_id 和 content。用于二次编辑时同时修改多个块。单次最多 200 个块。",
        parameters={
            "document_id": {"type": "string", "description": "文档 ID"},
            "updates": {
                "type": "array",
                "description": "更新数组，每项包含 block_id 和 content",
                "items": {
                    "type": "object",
                    "properties": {
                        "block_id": {"type": "string", "description": "块 ID"},
                        "content": {"type": "string", "description": "新的块内容"},
                    },
                    "required": ["block_id", "content"],
                },
            },
        },
        required=["document_id", "updates"],
    ),
    _feishu_batch_update_blocks,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_delete_document_block",
        description="删除飞书文档中指定的块。当用户要求删除/移除文档中的某段内容时使用此工具。需要先通过 feishu_get_document_blocks 获取目标块的 block_id，然后调用此工具删除。删除操作不可撤销。",
        parameters={
            "document_id": {"type": "string", "description": "文档 ID"},
            "block_id": {"type": "string", "description": "要删除的块 ID"},
        },
        required=["document_id", "block_id"],
    ),
    _feishu_delete_document_block,
)

# --- 多维表格类 ---

ToolRegistry.register(
    ToolDef(
        name="feishu_create_bitable",
        description="创建飞书多维表格并返回链接和 app_token。创建后可用 feishu_add_bitable_field 添加字段、feishu_add_bitable_records 添加记录。",
        parameters={
            "name": {"type": "string", "description": "多维表格名称"},
            "folder_token": {"type": "string", "description": "目标文件夹 token，空字符串表示根目录"},
        },
        required=["name"],
    ),
    _feishu_create_bitable,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_list_bitable_tables",
        description="列出飞书多维表格中的所有数据表。",
        parameters={
            "app_token": {"type": "string", "description": "多维表格的 app_token"},
            "page_size": {"type": "integer", "description": "每页数量，默认 20", "default": 20},
        },
        required=["app_token"],
    ),
    _feishu_list_bitable_tables,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_create_bitable_table",
        description=(
            "在多维表格中创建数据表。fields 为 JSON 字符串，格式："
            '[{"field_name":"姓名","field_type":1},{"field_name":"年龄","field_type":2}]。'
            "field_type: 1=多行文本, 2=数字, 3=单选, 4=多选, 5=日期, 7=复选框, 11=人员, 15=URL, 17=公式"
        ),
        parameters={
            "app_token": {"type": "string", "description": "多维表格的 app_token"},
            "table_name": {"type": "string", "description": "数据表名称"},
            "fields": {
                "type": "string",
                "description": '字段定义 JSON 数组字符串，如 [{"field_name":"姓名","field_type":1}]。不传则创建空表',
            },
        },
        required=["app_token", "table_name"],
    ),
    _feishu_create_bitable_table,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_list_bitable",
        description="查看飞书多维表格数据表中的记录。",
        parameters={
            "app_token": {"type": "string", "description": "多维表格的 app_token"},
            "table_id": {"type": "string", "description": "数据表 ID"},
            "page_size": {"type": "integer", "description": "每页记录数，默认 20", "default": 20},
        },
        required=["app_token", "table_id"],
    ),
    _feishu_list_bitable,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_add_bitable_records",
        description=(
            "向飞书多维表格添加记录。records 为 JSON 字符串，格式："
            '[{"fields":{"姓名":"张三","年龄":25}},{"fields":{"姓名":"李四","年龄":30}}]'
        ),
        parameters={
            "app_token": {"type": "string", "description": "多维表格的 app_token"},
            "table_id": {"type": "string", "description": "数据表 ID"},
            "records": {
                "type": "string",
                "description": '记录 JSON 数组字符串，如 [{"fields":{"姓名":"张三"}}]',
            },
        },
        required=["app_token", "table_id", "records"],
    ),
    _feishu_add_bitable_records,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_add_bitable_field",
        description=(
            "向飞书多维表格添加字段。field_type: 1=多行文本, 2=数字, 3=单选, 4=多选, "
            "5=日期, 7=复选框, 11=人员, 15=URL, 17=公式。"
            "单选/多选字段可传 field_property 定义选项。"
        ),
        parameters={
            "app_token": {"type": "string", "description": "多维表格的 app_token"},
            "table_id": {"type": "string", "description": "数据表 ID"},
            "field_name": {"type": "string", "description": "字段名称"},
            "field_type": {"type": "integer", "description": "字段类型，默认 1（多行文本）", "default": 1},
            "field_property": {
                "type": "string",
                "description": '字段属性 JSON 字符串，如单选: {"options":[{"name":"选项1"}]}',
            },
        },
        required=["app_token", "table_id", "field_name"],
    ),
    _feishu_add_bitable_field,
)

# --- 云空间类 ---

ToolRegistry.register(
    ToolDef(
        name="feishu_create_folder",
        description="在飞书云空间创建文件夹并返回 folder_token 和链接。",
        parameters={
            "name": {"type": "string", "description": "文件夹名称"},
            "folder_token": {"type": "string", "description": "父文件夹 token，空字符串表示根目录"},
        },
        required=["name"],
    ),
    _feishu_create_folder,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_list_folder",
        description="列出飞书云空间文件夹中的文件和子文件夹。",
        parameters={
            "folder_token": {"type": "string", "description": "文件夹 token，空字符串表示根目录"},
            "page_size": {"type": "integer", "description": "每页数量，默认 20", "default": 20},
        },
        required=[],
    ),
    _feishu_list_folder,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_upload_file",
        description="上传本地文件到飞书云空间。",
        parameters={
            "file_path": {"type": "string", "description": "本地文件路径"},
            "parent_node": {"type": "string", "description": "目标文件夹 token"},
            "file_name": {"type": "string", "description": "上传后的文件名，默认使用本地文件名"},
        },
        required=["file_path", "parent_node"],
    ),
    _feishu_upload_file,
)

# --- 日历类 ---

ToolRegistry.register(
    ToolDef(
        name="feishu_list_calendar",
        description="查看飞书日历中指定时间范围的事件。",
        parameters={
            "start_time": {"type": "string", "description": "开始时间，ISO 格式如 2024-01-01T00:00:00+08:00"},
            "end_time": {"type": "string", "description": "结束时间，ISO 格式如 2024-01-31T23:59:59+08:00"},
            "calendar_id": {"type": "string", "description": "日历 ID"},
            "page_size": {"type": "integer", "description": "每页数量，默认 50", "default": 50},
        },
        required=["start_time", "end_time", "calendar_id"],
    ),
    _feishu_list_calendar,
)

# --- 权限类 ---

ToolRegistry.register(
    ToolDef(
        name="feishu_add_permission",
        description=(
            "给飞书文档/表格添加协作者权限或设置公开分享。"
            "使用 tenant_access_token 创建的文档归属应用，用户默认无法访问，需要通过此工具添加权限。"
            "不指定 member_id 时会设置公开链接分享（组织内任何人可通过链接访问）。"
            "指定 member_id 时会添加该用户为协作者。"
        ),
        parameters={
            "token": {"type": "string", "description": "文档/表格的 token（文档为 document_id，多维表格为 app_token）"},
            "file_type": {
                "type": "string",
                "description": "文件类型：docx(文档)、bitable(多维表格)、sheet(表格)、folder(文件夹)",
                "default": "docx",
            },
            "member_type": {
                "type": "string",
                "description": "协作者类型：openid、email、userid、openchat",
                "default": "openid",
            },
            "member_id": {
                "type": "string",
                "description": "协作者 ID（如 open_id 或邮箱）。不传则设置公开链接分享",
            },
            "perm": {
                "type": "string",
                "description": "权限：view(只读)、edit(编辑)、full_access(管理)",
                "default": "edit",
            },
        },
        required=["token"],
    ),
    _feishu_add_permission,
)

# --- 云空间文件管理类 ---

ToolRegistry.register(
    ToolDef(
        name="feishu_delete_file",
        description="删除飞书云空间中的文件/文档/表格。删除后进入回收站，可恢复。需要应用具有删除权限。",
        parameters={
            "file_token": {"type": "string", "description": "要删除的文件 token（文档为 document_id，多维表格为 app_token）"},
            "file_type": {
                "type": "string",
                "description": "文件类型：docx(文档)、bitable(多维表格)、sheet(表格)、folder(文件夹)、doc(旧版文档)",
                "default": "docx",
            },
        },
        required=["file_token"],
    ),
    _feishu_delete_file,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_copy_file",
        description="复制飞书云空间中的文件到指定文件夹。",
        parameters={
            "file_token": {"type": "string", "description": "要复制的源文件 token"},
            "folder_token": {"type": "string", "description": "目标文件夹 token"},
            "name": {"type": "string", "description": "复制后的新文件名"},
            "file_type": {
                "type": "string",
                "description": "文件类型：docx、bitable、sheet、doc",
                "default": "docx",
            },
        },
        required=["file_token", "folder_token", "name"],
    ),
    _feishu_copy_file,
)

ToolRegistry.register(
    ToolDef(
        name="feishu_move_file",
        description="移动飞书云空间中的文件到指定文件夹。",
        parameters={
            "file_token": {"type": "string", "description": "要移动的文件 token"},
            "folder_token": {"type": "string", "description": "目标文件夹 token"},
            "file_type": {
                "type": "string",
                "description": "文件类型：docx、bitable、sheet、doc",
                "default": "docx",
            },
        },
        required=["file_token", "folder_token"],
    ),
    _feishu_move_file,
)


# ── 公开接口（供 web API 路由调用）───────────────────────────────

def is_configured() -> bool:
    """检查飞书是否已配置凭据。"""
    return bool(_app_id and _app_secret)


def get_domain_cache() -> str:
    """获取已缓存的企业域名。"""
    return _domain_cache
