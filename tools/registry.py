import importlib
import logging
from pathlib import Path
from typing import Callable

from tools.base import ToolDef, ToolMeta, ToolResult, ToolType

logger = logging.getLogger("wxagent.tools")


class ToolRegistry:
    _tools: dict[str, tuple[ToolDef, Callable]] = {}
    _metas: dict[str, ToolMeta] = {}
    _discovered: bool = False
    _loaders: dict[ToolType, "ToolLoader"] = {}

    @classmethod
    def register(cls, tool: ToolDef, handler: Callable, meta: ToolMeta = None) -> None:
        cls._tools[tool.name] = (tool, handler)
        if meta is None:
            meta = ToolMeta(
                name=tool.name,
                type=ToolType.BUILTIN,
                description=tool.description,
            )
        cls._metas[tool.name] = meta
        logger.debug(f"Tool registered: {tool.name} ({meta.type.value})")

    @classmethod
    def register_with_meta(cls, tool: ToolDef, handler: Callable, meta: ToolMeta) -> None:
        cls._tools[tool.name] = (tool, handler)
        cls._metas[tool.name] = meta
        logger.debug(f"Tool registered with meta: {tool.name} ({meta.type.value})")

    @classmethod
    def unregister(cls, name: str) -> bool:
        if name in cls._tools:
            del cls._tools[name]
            del cls._metas[name]
            logger.debug(f"Tool unregistered: {name}")
            return True
        for key, m in cls._metas.items():
            if m.name == name:
                del cls._tools[key]
                del cls._metas[key]
                logger.debug(f"Tool unregistered: {key} (by meta.name={name})")
                return True
        return False

    @classmethod
    def execute(cls, name: str, args: dict, state, user_id: str) -> ToolResult:
        if name not in cls._tools:
            return ToolResult(success=False, error=f"未知工具: {name}")
        meta = cls._metas.get(name)
        if meta and not meta.enabled:
            return ToolResult(success=False, error=f"工具已禁用: {name}")
        tool_def, handler = cls._tools[name]
        try:
            output = handler(**args, state=state, user_id=user_id)
            if isinstance(output, ToolResult):
                return output
            return ToolResult(success=True, content=str(output))
        except Exception as e:
            logger.exception(f"Tool execution failed: {name}")
            return ToolResult(success=False, error=str(e))

    @classmethod
    def get_all_defs(cls, enabled_only: bool = False) -> list[ToolDef]:
        if enabled_only:
            return [td for name, (td, _) in cls._tools.items() if cls._metas.get(name, ToolMeta(name="", type=ToolType.BUILTIN)).enabled]
        return [td for td, _ in cls._tools.values()]

    @classmethod
    def get_meta(cls, name: str) -> ToolMeta | None:
        meta = cls._metas.get(name)
        if meta:
            return meta
        for m in cls._metas.values():
            if m.name == name:
                return m
        return None

    @classmethod
    def get_all_metas(cls, type: ToolType = None, enabled: bool = None) -> list[ToolMeta]:
        metas = list(cls._metas.values())
        if type is not None:
            metas = [m for m in metas if m.type == type]
        if enabled is not None:
            metas = [m for m in metas if m.enabled == enabled]
        return sorted(metas, key=lambda m: m.priority)

    @classmethod
    def set_enabled(cls, name: str, enabled: bool) -> bool:
        if name in cls._metas:
            cls._metas[name].enabled = enabled
            logger.info(f"Tool {name} {'enabled' if enabled else 'disabled'}")
            return True
        for key, m in cls._metas.items():
            if m.name == name:
                m.enabled = enabled
                logger.info(f"Tool {name} {'enabled' if enabled else 'disabled'}")
                return True
        return False

    @classmethod
    def is_enabled(cls, name: str) -> bool:
        meta = cls._metas.get(name)
        return meta.enabled if meta else False

    @classmethod
    def clear(cls) -> None:
        cls._tools.clear()
        cls._metas.clear()
        cls._discovered = False

    @classmethod
    def discover(cls, paths: list[str] = None) -> list[ToolMeta]:
        if cls._discovered:
            return list(cls._metas.values())

        if paths is None:
            paths = ["tools/builtin", "tools/skills"]

        discovered = []
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                logger.debug(f"Discovery path not found: {path}")
                continue

            if "builtin" in path_str:
                discovered.extend(cls._discover_builtin(path))
            elif "skills" in path_str:
                discovered.extend(cls._discover_skills(path))

        cls._discovered = True
        logger.info(f"Discovered {len(discovered)} tools")
        return discovered

    @classmethod
    def _discover_builtin(cls, path: Path) -> list[ToolMeta]:
        metas = []
        for py_file in path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = py_file.stem
            try:
                module = importlib.import_module(f"tools.builtin.{module_name}")
                if hasattr(module, "TOOL_META"):
                    meta = module.TOOL_META
                    metas.append(meta)
                    if hasattr(module, "TOOL_DEF") and hasattr(module, "TOOL_HANDLER"):
                        cls.register(module.TOOL_DEF, module.TOOL_HANDLER, meta)
                else:
                    meta = ToolMeta(
                        name=module_name,
                        type=ToolType.BUILTIN,
                        source_path=str(py_file),
                    )
                    metas.append(meta)
            except Exception as e:
                logger.warning(f"Failed to discover builtin tool {module_name}: {e}")
        return metas

    @classmethod
    def _discover_skills(cls, path: Path) -> list[ToolMeta]:
        metas = []
        for file in path.glob("*"):
            if file.suffix == ".py":
                metas.extend(cls._load_py_skill(file))
            elif file.suffix == ".md":
                metas.extend(cls._load_md_skill(file))
        return metas

    @classmethod
    def _load_py_skill(cls, file: Path) -> list[ToolMeta]:
        metas = []
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(file.stem, file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "TOOL_META"):
                    meta = module.TOOL_META
                    meta.type = ToolType.SKILL
                    meta.source_path = str(file)
                    metas.append(meta)
                    if hasattr(module, "TOOL_DEF") and hasattr(module, "TOOL_HANDLER"):
                        cls.register(module.TOOL_DEF, module.TOOL_HANDLER, meta)
        except Exception as e:
            logger.warning(f"Failed to load skill {file}: {e}")
        return metas

    @classmethod
    def _load_md_skill(cls, file: Path) -> list[ToolMeta]:
        metas = []
        try:
            content = file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml
                    frontmatter = yaml.safe_load(parts[1])
                    meta = ToolMeta(
                        name=frontmatter.get("name", file.stem),
                        type=ToolType.SKILL,
                        description=frontmatter.get("description", ""),
                        version=frontmatter.get("version", "1.0.0"),
                        author=frontmatter.get("author", ""),
                        tags=frontmatter.get("tags", []),
                        enabled=frontmatter.get("enabled", True),
                        triggers=frontmatter.get("triggers", []),
                        actions=frontmatter.get("actions", []),
                        source_path=str(file),
                    )
                    metas.append(meta)
                    cls._register_skill_as_tool(meta)
        except Exception as e:
            logger.warning(f"Failed to load md skill {file}: {e}")
        return metas

    @classmethod
    def _register_skill_as_tool(cls, meta: ToolMeta) -> None:
        if not meta.triggers:
            return

        def skill_handler(state=None, user_id: str = "", **kwargs) -> ToolResult:
            results = []
            has_error = False
            for action in meta.actions:
                tool_name = action.get("tool")
                tool_args = action.get("args", {})
                if tool_name and tool_name in cls._tools:
                    result = cls.execute(tool_name, tool_args, state, user_id)
                    if result.requires_confirmation:
                        return ToolResult(
                            success=False,
                            requires_confirmation=True,
                            confirmation_detail=result.confirmation_detail or {
                                "type": "skill_action",
                                "detail": f"Skill '{meta.name}' 中的动作 {tool_name} 需要确认",
                                "skill_name": meta.name,
                                "tool_name": tool_name,
                                "tool_args": tool_args,
                                "pending_actions": meta.actions[meta.actions.index(action) + 1:],
                            },
                            error=f"Skill '{meta.name}' 需要确认: {tool_name} - {result.confirmation_detail.get('detail', '') if result.confirmation_detail else '需要用户确认'}",
                            display=f"Skill '{meta.name}' 需要确认",
                        )
                    status = "✓" if result.success else "✗"
                    if result.success:
                        content = result.display or (result.content[:80] if result.content else "")
                    else:
                        has_error = True
                        if result.error and "白名单" in result.error:
                            content = result.error
                        else:
                            content = result.display or (result.error[:200] if result.error else "失败")
                    results.append(f"{status} {tool_name}: {content}")
            
            result_content = f"Skill '{meta.name}' executed:\n" + "\n".join(results)
            if has_error:
                result_content += "\n\n⚠️ 部分工具执行失败，请查看上述错误信息并检查配置。"
            
            return ToolResult(
                success=True,
                content=result_content,
                display=meta.description,
            )

        tool_def = ToolDef(
            name=f"skill_{meta.name}",
            description=f"[Skill] {meta.description}",
            parameters={},
        )
        cls.register(tool_def, skill_handler, meta)

    @classmethod
    def match_trigger(cls, text: str) -> ToolMeta | None:
        text_lower = text.lower().strip()
        for meta in cls._metas.values():
            if meta.type == ToolType.SKILL and meta.enabled:
                for trigger in meta.triggers:
                    if trigger.lower() in text_lower:
                        return meta
        return None

    @classmethod
    def reload(cls, paths: list[str] = None) -> list[ToolMeta]:
        cls.clear()
        return cls.discover(paths)

    @classmethod
    def get_stats(cls) -> dict:
        return {
            "total": len(cls._tools),
            "enabled": sum(1 for m in cls._metas.values() if m.enabled),
            "disabled": sum(1 for m in cls._metas.values() if not m.enabled),
            "by_type": {
                t.value: sum(1 for m in cls._metas.values() if m.type == t)
                for t in ToolType
            },
        }
