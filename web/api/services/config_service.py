import threading
from pathlib import Path
from typing import Any, Optional

import yaml

import config as _config_module

from web.api.models.schemas import (
    AdvancedConfig,
    AIReviewerConfig,
    Aria2Config,
    CodeConfig,
    ConfigResponse,
    DownloadConfig,
    FileConfig,
    FileOrganizeConfig,
    FileOrganizeRuleConfig,
    IndexerConfig,
    LLMConfig,
    LimitsConfig,
    MemoryConfig,
    ModelRouteConfig,
    ModelRouterConfig,
    OCRConfig,
    PathSandboxConfig,
    PromptsConfig,
    RetrieverConfig,
    RiskLevelsConfig,
    SecurityConfig,
    SystemControlAction,
    SystemControlConfig,
    TasksConfig,
    ToolsConfig,
    WebConfig,
    WhisperConfig,
    WorkspaceConfig,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
YAML_PATH = PROJECT_ROOT / "config.yaml"

_lock = threading.Lock()

ENV_KEYS = [
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_FALLBACK_API_KEY",
    "LLM_FALLBACK_BASE_URL",
    "LLM_FALLBACK_MODEL",
    "VISION_API_KEY",
    "VISION_BASE_URL",
    "VISION_MODEL",
    "WORKSPACE_DIR",
    "AGENT_BACKEND",
]

API_KEY_FIELDS = {
    "api_key", "fallback_api_key", "vision_api_key",
}

MASK_PATTERN = "****"


def mask_value(value: str) -> str:
    if not value or not value.strip():
        return ""
    if len(value) > 8:
        return value[:4] + MASK_PATTERN + value[-4:]
    return MASK_PATTERN


def is_masked(value: str) -> bool:
    return MASK_PATTERN in value


def read_env() -> dict[str, str]:
    result = {}
    if not ENV_PATH.exists():
        return {k: "" for k in ENV_KEYS}
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                key = key.strip()
                val = val.strip()
                if key in ENV_KEYS:
                    result[key] = val
    for k in ENV_KEYS:
        result.setdefault(k, "")
    return result


def write_env(data: dict[str, str]) -> None:
    existing_lines: list[str] = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            key = key.strip()
            if key in data:
                new_val = data[key]
                if is_masked(new_val):
                    new_lines.append(line)
                else:
                    new_lines.append(f"{key}={new_val}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key in ENV_KEYS:
        if key not in updated_keys and key in data:
            val = data[key]
            if not is_masked(val):
                new_lines.append(f"{key}={val}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def read_yaml() -> dict[str, Any]:
    if not YAML_PATH.exists():
        return {}
    with open(YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(data: dict[str, Any], replace_keys: set[str] | None = None) -> None:
    existing = read_yaml()
    if replace_keys:
        merged = dict(existing)
        for key, val in data.items():
            if key in replace_keys:
                merged[key] = val
            elif key in existing and isinstance(existing[key], dict) and isinstance(val, dict):
                merged[key] = _deep_merge(existing[key], val)
            else:
                merged[key] = val
    else:
        merged = _deep_merge(existing, data)
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        yaml.dump(merged, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def get_llm_config() -> LLMConfig:
    env = read_env()
    return LLMConfig(
        provider=env.get("LLM_PROVIDER", "openai"),
        api_key=mask_value(env.get("LLM_API_KEY", "")),
        base_url=env.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        model=env.get("LLM_MODEL", "gpt-4o"),
        fallback_api_key=mask_value(env.get("LLM_FALLBACK_API_KEY", "")),
        fallback_base_url=env.get("LLM_FALLBACK_BASE_URL", ""),
        fallback_model=env.get("LLM_FALLBACK_MODEL", ""),
        vision_api_key=mask_value(env.get("VISION_API_KEY", "")),
        vision_base_url=env.get("VISION_BASE_URL", ""),
        vision_model=env.get("VISION_MODEL", ""),
        max_tokens=2048,
        agent_backend=env.get("AGENT_BACKEND", "langgraph"),
    )


def update_llm_config(config: LLMConfig) -> None:
    env = read_env()
    mapping = {
        "provider": "LLM_PROVIDER",
        "api_key": "LLM_API_KEY",
        "base_url": "LLM_BASE_URL",
        "model": "LLM_MODEL",
        "fallback_api_key": "LLM_FALLBACK_API_KEY",
        "fallback_base_url": "LLM_FALLBACK_BASE_URL",
        "fallback_model": "LLM_FALLBACK_MODEL",
        "vision_api_key": "VISION_API_KEY",
        "vision_base_url": "VISION_BASE_URL",
        "vision_model": "VISION_MODEL",
        "agent_backend": "AGENT_BACKEND",
    }
    data = {}
    for field, env_key in mapping.items():
        val = getattr(config, field, None)
        if val is None:
            continue
        if field in API_KEY_FIELDS and is_masked(str(val)):
            continue
        if field == "agent_backend" and env_key == "AGENT_BACKEND":
            data[env_key] = str(val)
        elif field in API_KEY_FIELDS:
            data[env_key] = str(val)
        else:
            data[env_key] = str(val)
    write_env(data)


def get_router_config() -> ModelRouterConfig:
    yaml_cfg = read_yaml().get("model_router", {})
    routes = {}
    for name, route_data in yaml_cfg.get("routes", {}).items():
        route = ModelRouteConfig(**route_data)
        if name == "vision":
            vision_model = _config_module.VISION_MODEL or route.model
            vision_base_url = _config_module.VISION_BASE_URL or route.base_url
            vision_source = ".env" if _config_module.VISION_MODEL else "yaml"
            routes[name] = ModelRouteConfig(
                model=vision_model,
                provider=route.provider,
                base_url=vision_base_url,
            )
            routes[name].model_source = vision_source
        else:
            routes[name] = route
    task_overrides = {}
    for name, override_data in yaml_cfg.get("task_overrides", {}).items():
        task_overrides[name] = ModelRouteConfig(**override_data)
    return ModelRouterConfig(
        default=yaml_cfg.get("default", "deepseek-chat"),
        routes=routes,
        task_overrides=task_overrides,
        rates=yaml_cfg.get("rates", {}),
    )


def update_router_config(config: ModelRouterConfig) -> None:
    data = {
        "model_router": {
            "default": config.default,
            "routes": {k: v.model_dump() for k, v in config.routes.items()},
            "task_overrides": {k: v.model_dump() for k, v in config.task_overrides.items()},
            "rates": config.rates,
        }
    }
    write_yaml(data, replace_keys={"model_router"})


def get_security_config() -> SecurityConfig:
    yaml_data = read_yaml().get("security", {})
    risk_data = yaml_data.get("risk_levels", {})
    risk_levels = RiskLevelsConfig(
        safe=risk_data.get("safe", []),
        caution=risk_data.get("caution", []),
        dangerous=risk_data.get("dangerous", []),
    )
    ps_data = yaml_data.get("path_sandbox", {})
    path_sandbox = PathSandboxConfig(
        write_roots=ps_data.get("write_roots", []),
        read_roots=ps_data.get("read_roots", []),
        denied_patterns=ps_data.get("denied_patterns", []),
    )
    ai_data = yaml_data.get("ai_reviewer", {})
    ai_reviewer = AIReviewerConfig(
        enabled=ai_data.get("enabled", True),
        review_levels=ai_data.get("review_levels", []),
        model=ai_data.get("model", "deepseek-chat"),
        max_command_length=ai_data.get("max_command_length", 500),
    )
    return SecurityConfig(
        dev_mode=yaml_data.get("dev_mode", False),
        risk_levels=risk_levels,
        path_sandbox=path_sandbox,
        ai_reviewer=ai_reviewer,
    )


def update_security_config(config: SecurityConfig) -> None:
    data = {
        "security": {
            "dev_mode": config.dev_mode,
            "risk_levels": config.risk_levels.model_dump(),
            "path_sandbox": config.path_sandbox.model_dump(),
            "ai_reviewer": config.ai_reviewer.model_dump(),
        }
    }
    write_yaml(data, replace_keys={"security"})


def get_limits_config() -> LimitsConfig:
    yaml_data = read_yaml()
    limits = yaml_data.get("limits", {})
    adv = yaml_data.get("advanced", {})
    return LimitsConfig(
        max_llm_calls_per_task=limits.get("max_llm_calls_per_task", 10),
        max_history=limits.get("max_history", 20),
        max_retries_per_step=limits.get("max_retries_per_step", 3),
        python_timeout_seconds=limits.get("python_timeout_seconds", 60),
        python_max_output_bytes=limits.get("python_max_output_bytes", 50000),
        shell_timeout_seconds=limits.get("shell_timeout_seconds", 30),
        max_tokens=adv.get("max_tokens", 2048),
        max_chars=adv.get("max_chars", 480),
        debounce_delay=adv.get("debounce_delay", 3.0),
        max_sessions=adv.get("max_sessions", 100),
        session_ttl_seconds=adv.get("session_ttl_seconds", 86400),
        messages_window=adv.get("messages_window", 50),
        short_term_max_messages=adv.get("short_term_max_messages", 50),
        long_term_max_messages=adv.get("long_term_max_messages", 20),
        llm_fallback_timeout=adv.get("llm_fallback_timeout", 30.0),
        bubble_send_interval=adv.get("bubble_send_interval", 0.3),
    )


def update_limits_config(config: LimitsConfig) -> None:
    advanced_keys = {
        "max_tokens", "max_chars", "debounce_delay", "max_sessions",
        "session_ttl_seconds", "messages_window", "short_term_max_messages",
        "long_term_max_messages", "llm_fallback_timeout", "bubble_send_interval",
    }
    limits_data = {k: v for k, v in config.model_dump().items() if k not in advanced_keys}
    advanced_data = {k: v for k, v in config.model_dump().items() if k in advanced_keys}
    write_yaml({"limits": limits_data, "advanced": advanced_data}, replace_keys={"limits"})


def get_workspace_config() -> WorkspaceConfig:
    env = read_env()
    yaml_data = read_yaml().get("workspace", {})
    return WorkspaceConfig(
        dir=env.get("WORKSPACE_DIR", yaml_data.get("dir", "workspace")),
        subdirs=yaml_data.get("subdirs", []),
        venv_packages=yaml_data.get("venv_packages", {}),
    )


def update_workspace_config(config: WorkspaceConfig) -> None:
    env_data = {}
    if not is_masked(config.dir):
        env_data["WORKSPACE_DIR"] = config.dir
    write_env(env_data)
    data = {
        "workspace": {
            "dir": config.dir,
            "subdirs": config.subdirs,
            "venv_packages": config.venv_packages,
        }
    }
    write_yaml(data, replace_keys={"workspace"})


def get_indexer_config() -> IndexerConfig:
    yaml_data = read_yaml().get("indexer", {})
    return IndexerConfig(
        enabled=yaml_data.get("enabled", False),
        watch_dirs=yaml_data.get("watch_dirs", []),
        supported_types=yaml_data.get("supported_types", []),
        idle_cpu_threshold=yaml_data.get("idle_cpu_threshold", 20),
        scan_interval_seconds=yaml_data.get("scan_interval_seconds", 300),
        max_document_chars=yaml_data.get("max_document_chars", 8000),
        use_watchdog=yaml_data.get("use_watchdog", True),
    )


def update_indexer_config(config: IndexerConfig) -> None:
    data = {"indexer": config.model_dump()}
    write_yaml(data, replace_keys={"indexer"})


def get_retriever_config() -> RetrieverConfig:
    yaml_data = read_yaml().get("retriever", {})
    return RetrieverConfig(
        vector_weight=yaml_data.get("vector_weight", 0.5),
        keyword_weight=yaml_data.get("keyword_weight", 0.3),
        time_decay_weight=yaml_data.get("time_decay_weight", 0.2),
        time_decay_half_life_days=yaml_data.get("time_decay_half_life_days", 30),
        default_scope=yaml_data.get("default_scope", []),
        default_top_k=yaml_data.get("default_top_k", 10),
        embedding_model=yaml_data.get("embedding_model", "BAAI/bge-small-zh"),
    )


def update_retriever_config(config: RetrieverConfig) -> None:
    data = {"retriever": config.model_dump()}
    write_yaml(data, replace_keys={"retriever"})


def get_memory_config() -> MemoryConfig:
    yaml_data = read_yaml()
    adv = yaml_data.get("advanced", {})
    return MemoryConfig(
        indexer=get_indexer_config(),
        retriever=get_retriever_config(),
        embedding_model=adv.get("embedding_model", "BAAI/bge-small-zh"),
        search_top_k=adv.get("memory_search_top_k", 3),
        relevance_threshold=adv.get("relevance_threshold", 0.5),
        preference_confidence_threshold=adv.get("preference_confidence_threshold", 0.6),
    )


def update_memory_config(config: MemoryConfig) -> None:
    write_yaml({
        "indexer": config.indexer.model_dump(),
        "retriever": config.retriever.model_dump(),
        "advanced": {
            "embedding_model": config.embedding_model,
            "memory_search_top_k": config.search_top_k,
            "relevance_threshold": config.relevance_threshold,
            "preference_confidence_threshold": config.preference_confidence_threshold,
        },
    }, replace_keys={"indexer", "retriever"})


def get_tools_config() -> ToolsConfig:
    yaml_data = read_yaml().get("advanced", {})
    return ToolsConfig(
        aria2=Aria2Config(
            rpc_url=yaml_data.get("aria2_rpc_url", "http://localhost:6800/jsonrpc"),
            rpc_timeout=yaml_data.get("aria2_rpc_timeout", 5),
        ),
        whisper=WhisperConfig(
            model=yaml_data.get("whisper_model", "base"),
            device=yaml_data.get("whisper_device", "cpu"),
            compute_type=yaml_data.get("whisper_compute_type", "int8"),
            cloud_model=yaml_data.get("whisper_cloud_model", "whisper-1"),
            silk_decode_timeout=yaml_data.get("silk_decode_timeout", 30),
            ffmpeg_audio_extract_timeout=yaml_data.get("ffmpeg_audio_extract_timeout", 300),
            ffmpeg_sample_rate=yaml_data.get("ffmpeg_sample_rate", 24000),
        ),
        ocr=OCRConfig(
            lang=yaml_data.get("ocr_lang", "ch"),
            fallback_model=yaml_data.get("ocr_fallback_model", "gpt-4o"),
        ),
        web=WebConfig(
            search_max_results=yaml_data.get("search_max_results", 5),
            fetch_max_chars=yaml_data.get("web_fetch_max_chars", 8000),
            fetch_timeout=yaml_data.get("web_fetch_timeout", 15),
            github_mirrors=yaml_data.get("github_mirrors", ["https://ghfast.top", "https://gh-proxy.com", "https://ghproxy.cc"]),
        ),
        download=DownloadConfig(
            video_download_timeout=yaml_data.get("video_download_timeout", 3600),
            http_download_timeout=yaml_data.get("http_download_timeout", 180),
            file_size_limit_mb=yaml_data.get("file_size_limit_mb", 50),
            cdn_download_timeout=yaml_data.get("cdn_download_timeout", 60),
            image_download_timeout=yaml_data.get("image_download_timeout", 15),
        ),
        file=FileConfig(
            file_size_limit_mb=yaml_data.get("file_size_limit_mb", 50),
            file_read_max_chars=yaml_data.get("file_read_max_chars", 100000),
        ),
        code=CodeConfig(
            pip_install_timeout=yaml_data.get("pip_install_timeout", 120),
            total_output_limit=yaml_data.get("code_total_output_limit", 100000),
        ),
        tasks=TasksConfig(
            io_pool_max_workers=yaml_data.get("io_pool_max_workers", 8),
            cpu_pool_max_workers=yaml_data.get("cpu_pool_max_workers", 2),
        ),
    )


def update_tools_config(config: ToolsConfig) -> None:
    data = {
        "advanced": {
            "aria2_rpc_url": config.aria2.rpc_url,
            "aria2_rpc_timeout": config.aria2.rpc_timeout,
            "whisper_model": config.whisper.model,
            "whisper_device": config.whisper.device,
            "whisper_compute_type": config.whisper.compute_type,
            "whisper_cloud_model": config.whisper.cloud_model,
            "silk_decode_timeout": config.whisper.silk_decode_timeout,
            "ffmpeg_audio_extract_timeout": config.whisper.ffmpeg_audio_extract_timeout,
            "ffmpeg_sample_rate": config.whisper.ffmpeg_sample_rate,
            "ocr_lang": config.ocr.lang,
            "ocr_fallback_model": config.ocr.fallback_model,
            "search_max_results": config.web.search_max_results,
            "web_fetch_max_chars": config.web.fetch_max_chars,
            "web_fetch_timeout": config.web.fetch_timeout,
            "github_mirrors": config.web.github_mirrors,
            "video_download_timeout": config.download.video_download_timeout,
            "http_download_timeout": config.download.http_download_timeout,
            "file_size_limit_mb": config.download.file_size_limit_mb,
            "cdn_download_timeout": config.download.cdn_download_timeout,
            "image_download_timeout": config.download.image_download_timeout,
            "file_read_max_chars": config.file.file_read_max_chars,
            "pip_install_timeout": config.code.pip_install_timeout,
            "code_total_output_limit": config.code.total_output_limit,
            "io_pool_max_workers": config.tasks.io_pool_max_workers,
            "cpu_pool_max_workers": config.tasks.cpu_pool_max_workers,
        }
    }
    write_yaml(data)


_DEFAULT_SYSTEM_PROMPT = "你是一个通过微信与用户聊天的 AI 助手，运行在用户的个人电脑上。你可以访问本地文件系统。"

_DEFAULT_CLASSIFY_PROMPT = '判断用户消息的类型，回复 JSON:\n{{"type": "meta"|"confirm"|"new_task"|"interrupt"}}\n- meta: 元命令（/reset、/help、/status、/tasks、/usage）\n- confirm: 对确认请求的回复（Y/N/是/否/确认/取消等）\n- interrupt: 当前有任务在执行，用户想打断/纠正/放弃\n- new_task: 其他一切新请求\n当前是否有正在执行的任务: {has_active_task}\n用户消息: {user_input}'

_DEFAULT_VISION_PROMPT = "请详细描述这张图片的内容，包括文字、物体、场景等所有可见信息。"

_DEFAULT_PREFERENCE_EXTRACT_PROMPT = '从以下用户消息中提取偏好信息。如果用户表达了明确的偏好，返回 JSON：\n{{"preference_key": "...", "preference_value": "...", "confidence": 0.0~1.0}}\n\n偏好可以是任何类型：回复风格、常用目录、文件命名习惯、语言偏好等。\n如果没有明显偏好，返回空 JSON {{}}。\n\n用户消息: {message}\n助手回复: {response}'

_DEFAULT_AI_SAFETY_PROMPT = '判断以下命令是否有恶意意图。只回复JSON。\n{{"verdict":"allow"|"deny"|"ask_user","reason":"...","risk_score":0.0~1.0}}\n\n判断依据:\n- allow: 正常操作，无安全风险\n- deny: 明确恶意（数据窃取、系统破坏、持久化后门）\n- ask_user: 无法确定，升级人工判断\n\n上下文: {context}'


def get_prompts_config() -> PromptsConfig:
    yaml_data = read_yaml().get("prompts", {})
    return PromptsConfig(
        system_prompt=yaml_data.get("system_prompt", _DEFAULT_SYSTEM_PROMPT),
        classify_prompt=yaml_data.get("classify_prompt", _DEFAULT_CLASSIFY_PROMPT),
        vision_prompt=yaml_data.get("vision_prompt", _DEFAULT_VISION_PROMPT),
        preference_extract_prompt=yaml_data.get("preference_extract_prompt", _DEFAULT_PREFERENCE_EXTRACT_PROMPT),
        ai_safety_prompt=yaml_data.get("ai_safety_prompt", _DEFAULT_AI_SAFETY_PROMPT),
    )


def update_prompts_config(config: PromptsConfig) -> None:
    write_yaml({"prompts": config.model_dump()}, replace_keys={"prompts"})


def get_system_control_config() -> SystemControlConfig:
    yaml_data = read_yaml().get("system_control", {})
    actions = {}
    for name, a_data in yaml_data.get("actions", {}).items():
        actions[name] = SystemControlAction(
            command=a_data.get("command", ""),
            risk=a_data.get("risk", "safe"),
            description=a_data.get("description", ""),
            shell=a_data.get("shell"),
        )
    return SystemControlConfig(
        actions=actions,
        app_whitelist=yaml_data.get("app_whitelist", {}),
    )


def update_system_control_config(config: SystemControlConfig) -> None:
    actions_data = {}
    for name, action in config.actions.items():
        a = {"command": action.command, "risk": action.risk, "description": action.description}
        if action.shell:
            a["shell"] = action.shell
        actions_data[name] = a
    data = {
        "system_control": {
            "actions": actions_data,
            "app_whitelist": config.app_whitelist,
        }
    }
    write_yaml(data, replace_keys={"system_control"})


def get_file_organize_config() -> FileOrganizeConfig:
    yaml_data = read_yaml().get("file_organize", {})
    rules_data = yaml_data.get("rules", {})
    rules = FileOrganizeRuleConfig(
        by_type=rules_data.get("by_type", {}),
        by_date=rules_data.get("by_date", {}),
        by_ext=rules_data.get("by_ext", {}),
    )
    return FileOrganizeConfig(rules=rules)


def update_file_organize_config(config: FileOrganizeConfig) -> None:
    data = {"file_organize": {"rules": config.rules.model_dump()}}
    write_yaml(data, replace_keys={"file_organize"})


def get_advanced_config() -> AdvancedConfig:
    yaml_data = read_yaml().get("advanced", {})
    return AdvancedConfig(
        max_tokens=yaml_data.get("max_tokens", 2048),
        max_chars=yaml_data.get("max_chars", 480),
        debounce_delay=yaml_data.get("debounce_delay", 3.0),
        max_sessions=yaml_data.get("max_sessions", 100),
        session_ttl_seconds=yaml_data.get("session_ttl_seconds", 86400),
        messages_window=yaml_data.get("messages_window", 50),
        short_term_max_messages=yaml_data.get("short_term_max_messages", 50),
        long_term_max_messages=yaml_data.get("long_term_max_messages", 20),
        embedding_model=yaml_data.get("embedding_model", "BAAI/bge-small-zh"),
        llm_fallback_timeout=yaml_data.get("llm_fallback_timeout", 30.0),
        aria2_rpc_url=yaml_data.get("aria2_rpc_url", "http://localhost:6800/jsonrpc"),
        github_mirrors=yaml_data.get("github_mirrors", ["https://ghfast.top", "https://gh-proxy.com", "https://ghproxy.cc"]),
        whisper_model=yaml_data.get("whisper_model", "base"),
        whisper_device=yaml_data.get("whisper_device", "cpu"),
        whisper_compute_type=yaml_data.get("whisper_compute_type", "int8"),
        whisper_cloud_model=yaml_data.get("whisper_cloud_model", "whisper-1"),
        ocr_lang=yaml_data.get("ocr_lang", "ch"),
        search_max_results=yaml_data.get("search_max_results", 5),
        web_fetch_max_chars=yaml_data.get("web_fetch_max_chars", 8000),
        io_pool_max_workers=yaml_data.get("io_pool_max_workers", 8),
        cpu_pool_max_workers=yaml_data.get("cpu_pool_max_workers", 2),
        pip_install_timeout=yaml_data.get("pip_install_timeout", 120),
        video_download_timeout=yaml_data.get("video_download_timeout", 3600),
        http_download_timeout=yaml_data.get("http_download_timeout", 180),
        file_size_limit_mb=yaml_data.get("file_size_limit_mb", 50),
        preference_extract_model=yaml_data.get("preference_extract_model", "deepseek-chat"),
        ocr_fallback_model=yaml_data.get("ocr_fallback_model", "gpt-4o"),
        bubble_send_interval=yaml_data.get("bubble_send_interval", 0.3),
        web_fetch_timeout=yaml_data.get("web_fetch_timeout", 15),
        aria2_rpc_timeout=yaml_data.get("aria2_rpc_timeout", 5),
        silk_decode_timeout=yaml_data.get("silk_decode_timeout", 30),
        ffmpeg_audio_extract_timeout=yaml_data.get("ffmpeg_audio_extract_timeout", 300),
        ffmpeg_sample_rate=yaml_data.get("ffmpeg_sample_rate", 24000),
        cdn_download_timeout=yaml_data.get("cdn_download_timeout", 60),
        image_download_timeout=yaml_data.get("image_download_timeout", 15),
        api_timeout=yaml_data.get("api_timeout", 15),
        upload_timeout=yaml_data.get("upload_timeout", 60),
        file_read_max_chars=yaml_data.get("file_read_max_chars", 100000),
        tool_result_max_chars=yaml_data.get("tool_result_max_chars", 4000),
        code_total_output_limit=yaml_data.get("code_total_output_limit", 100000),
        memory_search_top_k=yaml_data.get("memory_search_top_k", 3),
        relevance_threshold=yaml_data.get("relevance_threshold", 0.5),
        preference_confidence_threshold=yaml_data.get("preference_confidence_threshold", 0.6),
    )


def update_advanced_config(config: AdvancedConfig) -> None:
    data = {"advanced": config.model_dump()}
    write_yaml(data, replace_keys={"advanced"})


_MODULE_MAP = {
    "llm": (get_llm_config, update_llm_config, LLMConfig),
    "router": (get_router_config, update_router_config, ModelRouterConfig),
    "security": (get_security_config, update_security_config, SecurityConfig),
    "limits": (get_limits_config, update_limits_config, LimitsConfig),
    "workspace": (get_workspace_config, update_workspace_config, WorkspaceConfig),
    "indexer": (get_indexer_config, update_indexer_config, IndexerConfig),
    "retriever": (get_retriever_config, update_retriever_config, RetrieverConfig),
    "memory": (get_memory_config, update_memory_config, MemoryConfig),
    "tools": (get_tools_config, update_tools_config, ToolsConfig),
    "prompts": (get_prompts_config, update_prompts_config, PromptsConfig),
    "system_control": (get_system_control_config, update_system_control_config, SystemControlConfig),
    "file_organize": (get_file_organize_config, update_file_organize_config, FileOrganizeConfig),
    "advanced": (get_advanced_config, update_advanced_config, AdvancedConfig),
}


def get_all_config() -> ConfigResponse:
    with _lock:
        return ConfigResponse(
            llm=get_llm_config(),
            router=get_router_config(),
            security=get_security_config(),
            limits=get_limits_config(),
            workspace=get_workspace_config(),
            indexer=get_indexer_config(),
            retriever=get_retriever_config(),
            tools=get_tools_config(),
            prompts=get_prompts_config(),
            system_control=get_system_control_config(),
            file_organize=get_file_organize_config(),
            advanced=get_advanced_config(),
        )


def get_module_config(module: str) -> Optional[Any]:
    with _lock:
        entry = _MODULE_MAP.get(module)
        if entry is None:
            return None
        getter, _, _ = entry
        return getter()


def update_module_config(module: str, data: dict) -> Optional[Any]:
    with _lock:
        entry = _MODULE_MAP.get(module)
        if entry is None:
            return None
        _, updater, schema_cls = entry
        config_obj = schema_cls(**data)
        updater(config_obj)
        return config_obj


def validate_config(module: str, data: dict) -> list[str]:
    entry = _MODULE_MAP.get(module)
    if entry is None:
        return [f"Unknown module: {module}"]
    _, _, schema_cls = entry
    errors = []
    try:
        schema_cls(**data)
    except Exception as e:
        errors.append(str(e))
    return errors


def reload():
    """重新加载配置文件到 Python config 模块。"""
    import importlib
    import config
    importlib.reload(config)
