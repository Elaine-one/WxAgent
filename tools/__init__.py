import logging

from tools.base import ToolDef, ToolResult, ToolMeta, ToolType, to_anthropic_schema, to_openai_schema
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.tools")

# 模块导入时自动发现并注册所有 builtin/skills 工具
ToolRegistry.discover()

# ── Tool Search 按需加载 ─────────────────────────────────────
# 启用后，LLM 仅看到桥接工具 + always_load 工具，
# 通过 tool_search → tool_describe → tool_call 按需发现和调用其他工具。

def _is_tool_search_enabled() -> bool:
    try:
        import config as cfg
        return cfg.TOOL_SEARCH_ENABLED
    except Exception:
        return False


def _get_always_load_names() -> set[str]:
    try:
        import config as cfg
        return set(cfg.TOOL_SEARCH_ALWAYS_LOAD)
    except Exception:
        return set()


def _build_llm_tools() -> list[ToolDef]:
    """构建发送给 LLM 的工具列表。

    - Tool Search 启用: 桥接工具 + always_load 工具
    - Tool Search 禁用: 全量工具（传统模式）
    """
    if _is_tool_search_enabled():
        from tools.bridge import register_bridge_tools, get_bridge_defs
        # 注册桥接工具到 Registry（幂等，重复调用安全）
        register_bridge_tools()

        # 桥接工具
        llm_tools = get_bridge_defs()

        # always_load 工具：始终全量暴露给 LLM
        always_names = _get_always_load_names()
        if always_names:
            for td in ToolRegistry.get_all_defs():
                if td.name in always_names and td.name not in ("tool_search", "tool_describe", "tool_call"):
                    llm_tools.append(td)
                    # 标记 meta.always_load
                    meta = ToolRegistry.get_meta(td.name)
                    if meta:
                        meta.always_load = True

        logger.info(f"Tool Search enabled: {len(llm_tools)} tools exposed to LLM "
                     f"(bridge: 3, always_load: {len(llm_tools) - 3})")
        return llm_tools
    else:
        return ToolRegistry.get_all_defs()


ALL_TOOLS = _build_llm_tools()


def execute(name: str, args: dict, state, user_id: str) -> str:
    result = ToolRegistry.execute(name, args, state, user_id)
    if result.success:
        return result.content
    return f"错误：{result.error}" if result.error else "未知错误"


def get_tool_stats() -> dict:
    return ToolRegistry.get_stats()


def list_tools(type: str = None, enabled: bool = None) -> list[dict]:
    tool_type = ToolType(type) if type else None
    metas = ToolRegistry.get_all_metas(type=tool_type, enabled=enabled)
    return [
        {
            "name": m.name,
            "type": m.type.value,
            "description": m.description,
            "enabled": m.enabled,
            "version": m.version,
            "tags": m.tags,
        }
        for m in metas
    ]


def reload_tools() -> dict:
    global ALL_TOOLS
    ALL_TOOLS = _build_llm_tools()
    return get_tool_stats()


def _update_model_tools(models: list, provider: str) -> None:
    """批量更新模型的 tool schema。"""
    if provider == "anthropic":
        schemas = to_anthropic_schema(ALL_TOOLS)
    else:
        schemas = to_openai_schema(ALL_TOOLS)
    for m in models:
        if hasattr(m, "update_tools"):
            m.update_tools(schemas)
        elif hasattr(m, "_model") and hasattr(m._model, "update_tools"):
            m._model.update_tools(schemas)


def refresh_runtime_tools() -> dict:
    """刷新 ALL_TOOLS 并同步更新运行中的模型和 Graph 的工具列表。

    在 MCP 工具变更（连接/断开）后调用，确保 LLM 能感知新工具。
    """
    stats = reload_tools()

    # Tool Search 模式下，MCP 工具变更需要重建搜索索引
    if _is_tool_search_enabled():
        from tools.search import engine as search_engine
        search_engine.build_index()

    try:
        import config as cfg
        provider = cfg.LLM_PROVIDER
    except Exception:
        provider = "openai"

    # 更新 LangGraph Deps.tools（graph._deps.tools）
    try:
        from core.graph import _runtime_graph_ref
        if _runtime_graph_ref is not None and hasattr(_runtime_graph_ref, "_deps"):
            _runtime_graph_ref._deps.tools = ALL_TOOLS

            # 更新主模型 + model_cache 中的所有模型
            models = []
            model = _runtime_graph_ref._deps.model
            if model:
                models.append(model)
            model_cache = _runtime_graph_ref._deps.model_cache
            if model_cache:
                models.extend(model_cache.values())
            _update_model_tools(models, provider)
    except Exception:
        pass

    # 更新 legacy 模式的 model_cache
    try:
        from core.graph import _runtime_model_cache_ref
        if _runtime_model_cache_ref is not None:
            _update_model_tools(list(_runtime_model_cache_ref.values()), provider)
    except Exception:
        pass

    return stats
