import json
import os
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import PROJECT_ROOT
from tools.registry import ToolRegistry
from tools.base import ToolType, ToolMeta
from web.api.models.schemas import ToolMetaResponse, ToolStatsResponse
from web.api.services import config_service

router = APIRouter(prefix="/api/tools", tags=["tools"])


class SkillCreateRequest(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    enabled: bool = True
    triggers: list[str] = []
    actions: list[dict] = []


class SkillGenerateRequest(BaseModel):
    description: str
    save_path: str = ""


@router.get("")
def list_tools(type: str = None, enabled: bool = None):
    tool_type = ToolType(type) if type else None
    metas = ToolRegistry.get_all_metas(type=tool_type, enabled=enabled)
    return [
        ToolMetaResponse(
            name=m.name,
            type=m.type.value,
            description=m.description,
            version=m.version,
            author=m.author,
            tags=m.tags,
            enabled=m.enabled,
            priority=m.priority,
            source_path=m.source_path,
            triggers=m.triggers,
        )
        for m in metas
    ]


@router.get("/stats")
def get_tool_stats():
    stats = ToolRegistry.get_stats()
    return ToolStatsResponse(**stats)


@router.get("/types")
def get_tool_types():
    return [t.value for t in ToolType]


@router.get("/{name}")
def get_tool(name: str):
    meta = ToolRegistry.get_meta(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    return ToolMetaResponse(
        name=meta.name,
        type=meta.type.value,
        description=meta.description,
        version=meta.version,
        author=meta.author,
        tags=meta.tags,
        enabled=meta.enabled,
        priority=meta.priority,
        source_path=meta.source_path,
        triggers=meta.triggers,
    )


@router.put("/{name}/enable")
def set_tool_enabled(name: str, enabled: bool = True):
    if not ToolRegistry.set_enabled(name, enabled):
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    return {"success": True, "name": name, "enabled": enabled}


@router.post("/reload")
def reload_tools():
    stats = ToolRegistry.reload()
    return ToolStatsResponse(**stats)


@router.post("/{name}/reload")
def reload_tool(name: str):
    meta = ToolRegistry.get_meta(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    return {"success": True, "message": f"Tool {name} reload requested"}


skills_router = APIRouter(prefix="/api/skills", tags=["skills"])


def _get_skills_dir() -> Path:
    return PROJECT_ROOT / "tools" / "skills"


_SKILL_GENERATE_SYSTEM_PROMPT = (
    "你是一个 Skill 模板生成器。根据用户描述，生成一个 Skill 配置。"
    "返回纯 JSON，不要 markdown 代码块。格式如下："
    '{"name": "skill_name", "description": "描述", "triggers": ["触发词1", "触发词2"], '
    '"actions": [{"tool": "工具名", "args": {参数}}]}。'
    "可选工具：open_app(参数: app_name), system_action(参数: action), "
    "run_shell(参数: command), web_search(参数: query), send_file(参数: file_path)。"
    "name 使用英文下划线命名。"
)


@skills_router.post("/generate")
async def generate_skill(req: SkillGenerateRequest):
    env = config_service.read_env()
    provider = env.get("LLM_PROVIDER", "openai")
    api_key = env.get("LLM_API_KEY", "")
    base_url = env.get("LLM_BASE_URL", "https://api.openai.com/v1")
    model = env.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        raise HTTPException(status_code=500, detail="LLM_API_KEY not configured")

    chat_url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SKILL_GENERATE_SYSTEM_PROMPT},
            {"role": "user", "content": req.description},
        ],
        "temperature": 0.3,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(chat_url, headers=headers, json=payload)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

    try:
        resp_data = resp.json()
        content = resp_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail=f"Unexpected LLM response format: {e}")

    try:
        skill_config = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"LLM did not return valid JSON: {e}")

    if req.save_path is not None and req.save_path != "":
        save_dir = PROJECT_ROOT / req.save_path
    else:
        save_dir = _get_skills_dir()
    save_dir.mkdir(parents=True, exist_ok=True)

    skill_name = skill_config.get("name", "unnamed_skill")
    skill_path = save_dir / f"{skill_name}.md"

    frontmatter = {
        "name": skill_name,
        "type": "skill",
        "description": skill_config.get("description", ""),
        "version": "1.0.0",
        "author": "",
        "enabled": True,
        "triggers": skill_config.get("triggers", []),
        "actions": skill_config.get("actions", []),
    }

    file_content = (
        "---\n"
        + yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n# "
        + skill_name
        + "\n\n"
        + (skill_config.get("description", "") or "")
        + "\n"
    )
    skill_path.write_text(file_content, encoding="utf-8")

    meta = ToolMeta(
        name=skill_name,
        type=ToolType.SKILL,
        description=skill_config.get("description", ""),
        version="1.0.0",
        author="",
        enabled=True,
        triggers=skill_config.get("triggers", []),
        actions=skill_config.get("actions", []),
        source_path=str(skill_path),
    )
    ToolRegistry._register_skill_as_tool(meta)

    return {"success": True, "skill": skill_config, "path": str(skill_path)}


@skills_router.get("")
def list_skills():
    metas = ToolRegistry.get_all_metas(type=ToolType.SKILL)
    return [
        {
            "name": m.name,
            "type": m.type.value,
            "description": m.description,
            "version": m.version,
            "author": m.author,
            "enabled": m.enabled,
            "triggers": m.triggers,
            "actions": m.actions,
            "source_path": m.source_path,
        }
        for m in metas
    ]


@skills_router.post("")
def create_skill(req: SkillCreateRequest):
    skills_dir = _get_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_path = skills_dir / f"{req.name}.md"
    if skill_path.exists():
        raise HTTPException(status_code=400, detail=f"Skill already exists: {req.name}")

    frontmatter = {
        "name": req.name,
        "type": "skill",
        "description": req.description,
        "version": req.version,
        "author": req.author,
        "enabled": req.enabled,
        "triggers": req.triggers,
        "actions": req.actions,
    }

    content = "---\n" + yaml.dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n\n# " + req.name + "\n\n" + (req.description or "") + "\n"

    skill_path.write_text(content, encoding="utf-8")

    meta = ToolMeta(
        name=req.name,
        type=ToolType.SKILL,
        description=req.description,
        version=req.version,
        author=req.author,
        enabled=req.enabled,
        triggers=req.triggers,
        actions=req.actions,
        source_path=str(skill_path),
    )
    ToolRegistry._register_skill_as_tool(meta)

    return {"success": True, "name": req.name, "path": str(skill_path)}


@skills_router.put("/{name}")
def update_skill(name: str, req: SkillCreateRequest):
    meta = ToolRegistry.get_meta(name)
    if not meta:
        meta = ToolRegistry.get_meta(f"skill_{name}")
    if not meta:
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")

    skill_path = Path(meta.source_path) if meta.source_path else _get_skills_dir() / f"{name}.md"

    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill file not found: {name}")

    frontmatter = {
        "name": req.name,
        "type": "skill",
        "description": req.description,
        "version": req.version,
        "author": req.author,
        "enabled": req.enabled,
        "triggers": req.triggers,
        "actions": req.actions,
    }

    content = "---\n" + yaml.dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n\n# " + req.name + "\n\n" + (req.description or "") + "\n"

    skill_path.write_text(content, encoding="utf-8")

    new_meta = ToolMeta(
        name=req.name,
        type=ToolType.SKILL,
        description=req.description,
        version=req.version,
        author=req.author,
        enabled=req.enabled,
        triggers=req.triggers,
        actions=req.actions,
        source_path=str(skill_path),
    )

    if name != req.name:
        ToolRegistry.unregister(f"skill_{name}")
        ToolRegistry.unregister(name)
    ToolRegistry._register_skill_as_tool(new_meta)

    return {"success": True, "name": req.name}


@skills_router.delete("/{name}")
def delete_skill(name: str):
    meta = ToolRegistry.get_meta(name)
    if not meta:
        meta = ToolRegistry.get_meta(f"skill_{name}")
    if not meta:
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")

    if meta.source_path:
        skill_path = Path(meta.source_path)
        if skill_path.exists():
            skill_path.unlink()

    ToolRegistry.unregister(f"skill_{meta.name}")
    ToolRegistry.unregister(meta.name)

    return {"success": True, "name": name}
