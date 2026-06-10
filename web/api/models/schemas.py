from typing import Optional

from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    fallback_api_key: str = ""
    fallback_base_url: str = ""
    fallback_model: str = ""
    vision_api_key: str = ""
    vision_base_url: str = ""
    vision_model: str = ""
    max_tokens: int = 2048
    agent_backend: str = "langgraph"


class ModelRouteConfig(BaseModel):
    model: str = ""
    provider: str = "openai"
    base_url: str = ""
    model_source: Optional[str] = None


class ModelRouterConfig(BaseModel):
    default: str = "deepseek-chat"
    routes: dict[str, ModelRouteConfig] = {}
    task_overrides: dict[str, ModelRouteConfig] = {}
    rates: dict[str, dict[str, float]] = {}


class RiskLevelsConfig(BaseModel):
    safe: list[str] = []
    caution: list[str] = []
    dangerous: list[str] = []


class PathSandboxConfig(BaseModel):
    write_roots: list[str] = []
    read_roots: list[str] = []
    denied_patterns: list[str] = []


class AIReviewerConfig(BaseModel):
    enabled: bool = True
    review_levels: list[str] = []
    model: str = "deepseek-chat"
    max_command_length: int = 500


class SecurityConfig(BaseModel):
    dev_mode: bool = False
    risk_levels: RiskLevelsConfig = RiskLevelsConfig()
    path_sandbox: PathSandboxConfig = PathSandboxConfig()
    ai_reviewer: AIReviewerConfig = AIReviewerConfig()


class LimitsConfig(BaseModel):
    max_llm_calls_per_task: int = 10
    max_history: int = 20
    max_retries_per_step: int = 3
    python_timeout_seconds: int = 60
    python_max_output_bytes: int = 50000
    shell_timeout_seconds: int = 30
    max_tokens: int = 2048
    max_chars: int = 480
    debounce_delay: float = 3.0
    max_sessions: int = 100
    session_ttl_seconds: int = 86400
    messages_window: int = 50
    short_term_max_messages: int = 50
    long_term_max_messages: int = 20
    llm_fallback_timeout: float = 30.0
    bubble_send_interval: float = 0.3


class WorkspaceConfig(BaseModel):
    dir: str = "workspace"
    subdirs: list[str] = []
    venv_packages: dict[str, list[str]] = {}


class IndexerConfig(BaseModel):
    enabled: bool = False
    watch_dirs: list[str] = []
    supported_types: list[str] = []
    idle_cpu_threshold: int = 20
    scan_interval_seconds: int = 300
    max_document_chars: int = 8000
    use_watchdog: bool = True


class RetrieverConfig(BaseModel):
    vector_weight: float = 0.5
    keyword_weight: float = 0.3
    time_decay_weight: float = 0.2
    time_decay_half_life_days: int = 30
    default_scope: list[str] = []
    default_top_k: int = 10
    embedding_model: str = "BAAI/bge-small-zh"


class Aria2Config(BaseModel):
    rpc_url: str = "http://localhost:6800/jsonrpc"
    rpc_timeout: int = 5


class WhisperConfig(BaseModel):
    model: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    cloud_model: str = "whisper-1"
    silk_decode_timeout: int = 30
    ffmpeg_audio_extract_timeout: int = 300
    ffmpeg_sample_rate: int = 24000


class OCRConfig(BaseModel):
    lang: str = "ch"
    fallback_model: str = "gpt-4o"


class WebConfig(BaseModel):
    search_max_results: int = 5
    fetch_max_chars: int = 8000
    fetch_timeout: int = 15
    github_mirrors: list[str] = []


class DownloadConfig(BaseModel):
    video_download_timeout: int = 3600
    http_download_timeout: int = 180
    file_size_limit_mb: int = 50
    cdn_download_timeout: int = 60
    image_download_timeout: int = 15


class FileConfig(BaseModel):
    file_size_limit_mb: int = 50
    file_read_max_chars: int = 100000


class CodeConfig(BaseModel):
    pip_install_timeout: int = 120
    total_output_limit: int = 100000


class TasksConfig(BaseModel):
    io_pool_max_workers: int = 8
    cpu_pool_max_workers: int = 2


class ToolsConfig(BaseModel):
    aria2: Aria2Config = Aria2Config()
    whisper: WhisperConfig = WhisperConfig()
    ocr: OCRConfig = OCRConfig()
    web: WebConfig = WebConfig()
    download: DownloadConfig = DownloadConfig()
    file: FileConfig = FileConfig()
    code: CodeConfig = CodeConfig()
    tasks: TasksConfig = TasksConfig()


class PromptsConfig(BaseModel):
    system_prompt: str = ""
    classify_prompt: str = ""
    vision_prompt: str = ""
    preference_extract_prompt: str = ""
    ai_safety_prompt: str = ""


class MemoryConfig(BaseModel):
    indexer: IndexerConfig = IndexerConfig()
    retriever: RetrieverConfig = RetrieverConfig()
    embedding_model: str = "BAAI/bge-small-zh"
    search_top_k: int = 3
    relevance_threshold: float = 0.5
    preference_confidence_threshold: float = 0.6


class SystemControlAction(BaseModel):
    command: str = ""
    risk: str = "safe"
    description: str = ""
    shell: Optional[str] = None


class SystemControlConfig(BaseModel):
    actions: dict[str, SystemControlAction] = {}
    app_whitelist: dict[str, str] = {}


class FileOrganizeRuleConfig(BaseModel):
    by_type: dict[str, list[str]] = {}
    by_date: dict[str, str] = {}
    by_ext: dict[str, str] = {}


class FileOrganizeConfig(BaseModel):
    rules: FileOrganizeRuleConfig = FileOrganizeRuleConfig()


class AdvancedConfig(BaseModel):
    max_tokens: int = 2048
    max_chars: int = 480
    debounce_delay: float = 3.0
    max_sessions: int = 100
    session_ttl_seconds: int = 86400
    messages_window: int = 50
    short_term_max_messages: int = 50
    long_term_max_messages: int = 20
    embedding_model: str = "BAAI/bge-small-zh"
    llm_fallback_timeout: float = 30.0
    aria2_rpc_url: str = "http://localhost:6800/jsonrpc"
    github_mirrors: list[str] = ["https://ghfast.top", "https://gh-proxy.com", "https://ghproxy.cc"]
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_cloud_model: str = "whisper-1"
    ocr_lang: str = "ch"
    search_max_results: int = 5
    web_fetch_max_chars: int = 8000
    io_pool_max_workers: int = 8
    cpu_pool_max_workers: int = 2
    pip_install_timeout: int = 120
    video_download_timeout: int = 3600
    http_download_timeout: int = 180
    file_size_limit_mb: int = 50
    preference_extract_model: str = "deepseek-chat"
    ocr_fallback_model: str = "gpt-4o"
    bubble_send_interval: float = 0.3
    web_fetch_timeout: int = 15
    aria2_rpc_timeout: int = 5
    silk_decode_timeout: int = 30
    ffmpeg_audio_extract_timeout: int = 300
    ffmpeg_sample_rate: int = 24000
    cdn_download_timeout: int = 60
    image_download_timeout: int = 15
    api_timeout: int = 15
    upload_timeout: int = 60
    file_read_max_chars: int = 100000
    tool_result_max_chars: int = 4000
    code_total_output_limit: int = 100000
    memory_search_top_k: int = 3
    relevance_threshold: float = 0.5
    preference_confidence_threshold: float = 0.6


class ConfigResponse(BaseModel):
    llm: LLMConfig = LLMConfig()
    router: ModelRouterConfig = ModelRouterConfig()
    security: SecurityConfig = SecurityConfig()
    limits: LimitsConfig = LimitsConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    indexer: IndexerConfig = IndexerConfig()
    retriever: RetrieverConfig = RetrieverConfig()
    tools: ToolsConfig = ToolsConfig()
    prompts: PromptsConfig = PromptsConfig()
    system_control: SystemControlConfig = SystemControlConfig()
    file_organize: FileOrganizeConfig = FileOrganizeConfig()
    advanced: AdvancedConfig = AdvancedConfig()


class ServiceStatus(BaseModel):
    running: bool = False
    pid: Optional[int] = None
    uptime: Optional[float] = None
    ready: bool = False


class TestLLMRequest(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    prompt: str = "Hello, respond with 'OK' if you can read this."


class TestLLMResponse(BaseModel):
    success: bool = False
    message: str = ""
    model: str = ""
    latency_ms: float = 0.0


class ToolMetaResponse(BaseModel):
    name: str
    type: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = []
    enabled: bool = True
    priority: int = 100
    source_path: str = ""
    triggers: list[str] = []


class ToolStatsResponse(BaseModel):
    total: int = 0
    enabled: int = 0
    disabled: int = 0
    by_type: dict[str, int] = {}
