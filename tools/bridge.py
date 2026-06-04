"""Tool Search 桥接工具 - 按需加载工具的三个核心桥接。

替代全量工具 schema 注入，LLM 通过以下流程按需发现和调用工具：
1. tool_search(query) → 搜索匹配工具
2. tool_describe(tool_name) → 加载完整参数 schema
3. tool_call(tool_name, arguments) → 执行真实工具

参考: Hermes Agent Tool Search (Nous Research)
"""

import json
import logging

from tools.base import ToolDef, ToolMeta, ToolResult, ToolType
from tools.registry import ToolRegistry
from tools.search import engine as search_engine

logger = logging.getLogger("wxagent.tools.bridge")


# ── tool_search ──────────────────────────────────────────────

TOOL_SEARCH_DEF = ToolDef(
    name="tool_search",
    description=(
        "搜索可用工具。当你需要执行某个操作但不确定有哪些工具可用时，"
        "先用此工具搜索。返回匹配的工具列表（名称、描述、相关性评分）。"
        "然后使用 tool_describe 查看具体参数格式，再用 tool_call 执行。"
    ),
    parameters={
        "query": {
            "type": "string",
            "description": "搜索关键词，描述你想执行的操作，如 '搜索网页'、'读取文件'、'发送消息'",
        },
        "top_k": {
            "type": "integer",
            "description": "返回结果数量，默认 5",
        },
    },
    required=["query"],
)

TOOL_SEARCH_META = ToolMeta(
    name="tool_search",
    type=ToolType.SYSTEM_MODE,
    description="搜索可用工具",
    always_load=True,
)


def _tool_search(query: str, top_k: int = 5, state=None, user_id: str = "") -> ToolResult:
    results = search_engine.search(query, top_k=top_k)
    if not results:
        return ToolResult(
            success=True,
            content="未找到匹配的工具。请尝试不同的关键词，或使用 tool_describe 查看特定工具。",
        )
    lines = ["找到以下匹配工具：\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['name']}** (类型: {r['type']}, 相关度: {r['score']})")
        lines.append(f"   {r['description']}")
    lines.append("\n使用 tool_describe 查看工具的完整参数格式，使用 tool_call 执行工具。")
    return ToolResult(success=True, content="\n".join(lines))


# ── tool_describe ────────────────────────────────────────────

TOOL_DESCRIBE_DEF = ToolDef(
    name="tool_describe",
    description=(
        "获取工具的完整参数 schema。在 tool_search 找到工具后，"
        "调用此工具查看该工具需要哪些参数及参数格式，"
        "然后按 schema 构造参数并使用 tool_call 执行。"
    ),
    parameters={
        "tool_name": {
            "type": "string",
            "description": "工具名称，从 tool_search 结果中获取",
        },
    },
    required=["tool_name"],
)

TOOL_DESCRIBE_META = ToolMeta(
    name="tool_describe",
    type=ToolType.SYSTEM_MODE,
    description="获取工具完整参数格式",
    always_load=True,
)


def _tool_describe(tool_name: str, state=None, user_id: str = "") -> ToolResult:
    info = search_engine.describe(tool_name)
    if not info:
        # 尝试模糊匹配
        results = search_engine.search(tool_name, top_k=3)
        if results:
            names = [f"- {r['name']}: {r['description']}" for r in results]
            return ToolResult(
                success=False,
                error=f"未找到工具 '{tool_name}'。你是否指以下工具之一？\n" + "\n".join(names),
            )
        return ToolResult(success=False, error=f"未找到工具 '{tool_name}'。请先用 tool_search 搜索。")

    lines = [
        f"工具: {info['name']}",
        f"类型: {info.get('type', 'unknown')}",
        f"描述: {info['description']}",
        "",
        "参数格式 (JSON Schema):",
    ]
    if info.get("parameters"):
        lines.append("```json")
        lines.append(json.dumps(info["parameters"], ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("（无参数）")

    if info.get("required"):
        lines.append(f"\n必填参数: {', '.join(info['required'])}")

    lines.append("\n请按上述参数格式构造 arguments，然后使用 tool_call 执行。")
    return ToolResult(success=True, content="\n".join(lines))


# ── tool_call ────────────────────────────────────────────────

TOOL_CALL_DEF = ToolDef(
    name="tool_call",
    description=(
        "执行指定工具。在 tool_search 找到工具并用 tool_describe 查看参数格式后，"
        "使用此工具执行真实调用。arguments 必须符合 tool_describe 返回的参数 schema。"
    ),
    parameters={
        "tool_name": {
            "type": "string",
            "description": "要执行的工具名称",
        },
        "arguments": {
            "type": "object",
            "description": "工具参数，格式由 tool_describe 返回的 schema 决定",
        },
    },
    required=["tool_name", "arguments"],
)

TOOL_CALL_META = ToolMeta(
    name="tool_call",
    type=ToolType.SYSTEM_MODE,
    description="执行指定工具",
    always_load=True,
)


async def _tool_call(tool_name: str, arguments: dict, state=None, user_id: str = "") -> ToolResult:
    # 防止递归调用桥接工具
    if tool_name in ("tool_search", "tool_describe", "tool_call"):
        return ToolResult(
            success=False,
            error=f"不能通过 tool_call 调用桥接工具 '{tool_name}'，请直接调用。",
        )

    # 检查工具是否存在
    if tool_name not in ToolRegistry._tools:
        return ToolResult(
            success=False,
            error=f"工具 '{tool_name}' 不存在。请先用 tool_search 搜索可用工具。",
        )

    # 检查工具是否启用
    meta = ToolRegistry.get_meta(tool_name)
    if meta and not meta.enabled:
        return ToolResult(success=False, error=f"工具 '{tool_name}' 已禁用。")

    # 执行真实工具
    logger.info(f"bridge tool_call → {tool_name}({json.dumps(arguments, ensure_ascii=False)[:200]})")
    result = await ToolRegistry.aexecute(tool_name, arguments, state, user_id)

    # 透传 requires_confirmation
    return result


# ── 注册桥接工具 ─────────────────────────────────────────────

BRIDGE_DEFS = [TOOL_SEARCH_DEF, TOOL_DESCRIBE_DEF, TOOL_CALL_DEF]
BRIDGE_HANDLERS = [_tool_search, _tool_describe, _tool_call]
BRIDGE_METAS = [TOOL_SEARCH_META, TOOL_DESCRIBE_META, TOOL_CALL_META]


def register_bridge_tools() -> None:
    """将三个桥接工具注册到 ToolRegistry。"""
    for defn, handler, meta in zip(BRIDGE_DEFS, BRIDGE_HANDLERS, BRIDGE_METAS):
        ToolRegistry.register_with_meta(defn, handler, meta)
    # 构建搜索索引
    search_engine.build_index()
    logger.info("Bridge tools registered: tool_search, tool_describe, tool_call")


def get_bridge_defs() -> list[ToolDef]:
    """返回桥接工具定义列表。"""
    return list(BRIDGE_DEFS)
