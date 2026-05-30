import logging

import yaml

from config import PROJECT_ROOT
from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _load_scenarios() -> dict:
    try:
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("scenarios", {})
    except Exception:
        return {}


def _activate_scenario(name: str, state=None, user_id: str = "") -> ToolResult:
    cfg = _load_scenarios()
    sc = cfg.get(name)
    if not sc:
        available = list(cfg.keys())
        return ToolResult(
            success=False,
            error=f"未知场景: {name}。可用: {available}",
        )

    results = []
    for action in sc.get("actions", []):
        tool_name = action.get("tool")
        tool_args = action.get("args", {})
        if not tool_name:
            continue
        result = ToolRegistry.execute(tool_name, tool_args, state=state, user_id=user_id)
        status = "✓" if result.success else "✗"
        results.append(f"{status} {tool_name}: {result.display or result.content[:80]}")

    return ToolResult(
        success=True,
        content=f"场景 '{name}' 执行完成:\n" + "\n".join(results),
        display=f"'{sc.get('description', name)}' 已就绪",
    )


def _list_scenarios(state=None, user_id: str = "") -> ToolResult:
    cfg = _load_scenarios()
    lines = [
        f"- {name}: {sc.get('description', '')} ({len(sc.get('actions', []))} 个动作)"
        for name, sc in cfg.items()
    ]
    return ToolResult(
        success=True,
        content="\n".join(lines) if lines else "暂无可用场景",
        display=f"共 {len(cfg)} 个场景可用",
    )


ToolRegistry.register(
    ToolDef(
        name="activate_scenario",
        description="执行预定义场景宏（动作序列）。场景定义在 config.yaml。每个动作对应一个工具调用。",
        parameters={
            "name": {"type": "string", "description": "场景名称，如 work_mode/meeting_mode"},
        },
        required=["name"],
    ),
    _activate_scenario,
)

ToolRegistry.register(
    ToolDef(
        name="list_scenarios",
        description="列出所有可用的场景宏及其描述。",
        parameters={},
    ),
    _list_scenarios,
)
