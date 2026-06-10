import os
import subprocess
import sys
from pathlib import Path

import logging

import dotenv
dotenv.load_dotenv()

logger = logging.getLogger("wxagent.config")

# ============================================================
# 项目路径
# ============================================================

PROJECT_ROOT = Path(__file__).parent.resolve()

_CACHE_DIR = Path(os.getenv("WORKSPACE_DIR", str(PROJECT_ROOT / "workspace"))).resolve() / "data" / ".cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_CACHE_DIR / "huggingface"))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(_CACHE_DIR / "sentence_transformers"))
os.environ.setdefault("CHROMA_CACHE_DIR", str(_CACHE_DIR / "chroma"))

SESSION_FILE = PROJECT_ROOT / "session.json"

# ============================================================
# 工作区（Agent 所有写操作的根目录）
# ============================================================

# 通过环境变量 WORKSPACE_DIR 自定义工作区位置
# 未设置时默认为项目目录下的 workspace/
# 示例：WORKSPACE_DIR=C:\Users\21357\workspace
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(PROJECT_ROOT / "workspace"))).resolve()

# 内部数据目录（向量库、审计日志、调试快照等，不暴露给用户）
DATA_DIR = WORKSPACE_DIR / "data"

EMBEDDING_MODEL_PATH = DATA_DIR / "models" / "bge-small-zh"

# 工作区内嵌的 Python 虚拟环境（run_python 工具使用此解释器）
VENV_PYTHON = WORKSPACE_DIR / ".venv" / "Scripts" / "python.exe"

# ============================================================
# 用户环境
# ============================================================

USER_HOME = os.path.expanduser("~")
USER_DESKTOP = os.path.join(USER_HOME, "Desktop")

# ============================================================
# LLM 配置
# ============================================================

# 厂商：openai（兼容 DeepSeek/Qwen/智谱等）或 anthropic
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

# API 密钥（必填）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

# API 地址（OpenAI 兼容接口可改为 DeepSeek 等的地址）
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")

# 模型名称
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY", "")
LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "")

VISION_API_KEY = os.getenv("VISION_API_KEY", LLM_API_KEY)
VISION_BASE_URL = os.getenv("VISION_BASE_URL", "")
VISION_MODEL = os.getenv("VISION_MODEL", "")

# ============================================================
# Agent 行为限制（从 config.yaml 读取，环境变量可覆盖）
# ============================================================

def _load_yaml_config():
    try:
        import yaml
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

_YAML_CFG = _load_yaml_config()
_LIMITS = _YAML_CFG.get("limits", {})
_ADVANCED = _YAML_CFG.get("advanced", {})
_PROMPTS = _YAML_CFG.get("prompts", {})

MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", _LIMITS.get("max_llm_calls_per_task", 10)))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", _LIMITS.get("max_history", 20)))
PYTHON_TIMEOUT = int(os.getenv("PYTHON_TIMEOUT", _LIMITS.get("python_timeout_seconds", 60)))
PYTHON_MAX_OUTPUT = int(os.getenv("PYTHON_MAX_OUTPUT", _LIMITS.get("python_max_output_bytes", 50000)))
SHELL_TIMEOUT = int(os.getenv("SHELL_TIMEOUT", _LIMITS.get("shell_timeout_seconds", 30)))

ADV_MAX_TOKENS = int(os.getenv("ADV_MAX_TOKENS", _ADVANCED.get("max_tokens", 2048)))
ADV_MAX_CHARS = int(os.getenv("ADV_MAX_CHARS", _ADVANCED.get("max_chars", 600)))
ADV_DEBOUNCE_DELAY = float(os.getenv("ADV_DEBOUNCE_DELAY", _ADVANCED.get("debounce_delay", 3.0)))
ADV_MAX_SESSIONS = int(os.getenv("ADV_MAX_SESSIONS", _ADVANCED.get("max_sessions", 100)))
ADV_SESSION_TTL_SECONDS = int(os.getenv("ADV_SESSION_TTL_SECONDS", _ADVANCED.get("session_ttl_seconds", 86400)))
ADV_MESSAGES_WINDOW = int(os.getenv("ADV_MESSAGES_WINDOW", _ADVANCED.get("messages_window", 50)))
ADV_SHORT_TERM_MAX_MESSAGES = int(os.getenv("ADV_SHORT_TERM_MAX_MESSAGES", _ADVANCED.get("short_term_max_messages", 50)))
ADV_LONG_TERM_MAX_MESSAGES = int(os.getenv("ADV_LONG_TERM_MAX_MESSAGES", _ADVANCED.get("long_term_max_messages", 20)))
ADV_EMBEDDING_MODEL = os.getenv("ADV_EMBEDDING_MODEL", _ADVANCED.get("embedding_model", "BAAI/bge-small-zh"))
ADV_LLM_FALLBACK_TIMEOUT = float(os.getenv("ADV_LLM_FALLBACK_TIMEOUT", _ADVANCED.get("llm_fallback_timeout", 30.0)))
ADV_ARIA2_RPC_URL = os.getenv("ADV_ARIA2_RPC_URL", _ADVANCED.get("aria2_rpc_url", "http://localhost:6800/jsonrpc"))
ADV_GITHUB_MIRRORS = _ADVANCED.get("github_mirrors", ["https://ghfast.top", "https://gh-proxy.com", "https://ghproxy.cc"])  # NOTE: 列表类型不支持环境变量覆盖
ADV_WHISPER_MODEL = os.getenv("ADV_WHISPER_MODEL", _ADVANCED.get("whisper_model", "base"))
ADV_WHISPER_DEVICE = os.getenv("ADV_WHISPER_DEVICE", _ADVANCED.get("whisper_device", "cpu"))
ADV_WHISPER_COMPUTE_TYPE = os.getenv("ADV_WHISPER_COMPUTE_TYPE", _ADVANCED.get("whisper_compute_type", "int8"))
ADV_WHISPER_CLOUD_MODEL = os.getenv("ADV_WHISPER_CLOUD_MODEL", _ADVANCED.get("whisper_cloud_model", "whisper-1"))
ADV_OCR_LANG = os.getenv("ADV_OCR_LANG", _ADVANCED.get("ocr_lang", "ch"))
ADV_WEB_FETCH_MAX_CHARS = int(os.getenv("ADV_WEB_FETCH_MAX_CHARS", _ADVANCED.get("web_fetch_max_chars", 8000)))
ADV_IO_POOL_MAX_WORKERS = int(os.getenv("ADV_IO_POOL_MAX_WORKERS", _ADVANCED.get("io_pool_max_workers", 8)))
ADV_CPU_POOL_MAX_WORKERS = int(os.getenv("ADV_CPU_POOL_MAX_WORKERS", _ADVANCED.get("cpu_pool_max_workers", 2)))
ADV_PIP_INSTALL_TIMEOUT = int(os.getenv("ADV_PIP_INSTALL_TIMEOUT", _ADVANCED.get("pip_install_timeout", 120)))
ADV_VIDEO_DOWNLOAD_TIMEOUT = int(os.getenv("ADV_VIDEO_DOWNLOAD_TIMEOUT", _ADVANCED.get("video_download_timeout", 3600)))
ADV_HTTP_DOWNLOAD_TIMEOUT = int(os.getenv("ADV_HTTP_DOWNLOAD_TIMEOUT", _ADVANCED.get("http_download_timeout", 180)))
ADV_FILE_SIZE_LIMIT_MB = int(os.getenv("ADV_FILE_SIZE_LIMIT_MB", _ADVANCED.get("file_size_limit_mb", 50)))
ADV_PREFERENCE_EXTRACT_MODEL = os.getenv("ADV_PREFERENCE_EXTRACT_MODEL", _ADVANCED.get("preference_extract_model", "deepseek-chat"))
ADV_OCR_FALLBACK_MODEL = os.getenv("ADV_OCR_FALLBACK_MODEL", _ADVANCED.get("ocr_fallback_model", "gpt-4o"))
ADV_BUBBLE_SEND_INTERVAL = float(os.getenv("ADV_BUBBLE_SEND_INTERVAL", _ADVANCED.get("bubble_send_interval", 0.3)))
ADV_WEB_FETCH_TIMEOUT = int(os.getenv("ADV_WEB_FETCH_TIMEOUT", _ADVANCED.get("web_fetch_timeout", 15)))
ADV_ARIA2_RPC_TIMEOUT = int(os.getenv("ADV_ARIA2_RPC_TIMEOUT", _ADVANCED.get("aria2_rpc_timeout", 5)))
ADV_SILK_DECODE_TIMEOUT = int(os.getenv("ADV_SILK_DECODE_TIMEOUT", _ADVANCED.get("silk_decode_timeout", 30)))
ADV_FFMPEG_AUDIO_EXTRACT_TIMEOUT = int(os.getenv("ADV_FFMPEG_AUDIO_EXTRACT_TIMEOUT", _ADVANCED.get("ffmpeg_audio_extract_timeout", 300)))
ADV_FFMPEG_SAMPLE_RATE = int(os.getenv("ADV_FFMPEG_SAMPLE_RATE", _ADVANCED.get("ffmpeg_sample_rate", 24000)))
ADV_CDN_DOWNLOAD_TIMEOUT = int(os.getenv("ADV_CDN_DOWNLOAD_TIMEOUT", _ADVANCED.get("cdn_download_timeout", 60)))
ADV_IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv("ADV_IMAGE_DOWNLOAD_TIMEOUT", _ADVANCED.get("image_download_timeout", 15)))
ADV_API_TIMEOUT = int(os.getenv("ADV_API_TIMEOUT", _ADVANCED.get("api_timeout", 15)))
ADV_UPLOAD_TIMEOUT = int(os.getenv("ADV_UPLOAD_TIMEOUT", _ADVANCED.get("upload_timeout", 60)))
ADV_FILE_READ_MAX_CHARS = int(os.getenv("ADV_FILE_READ_MAX_CHARS", _ADVANCED.get("file_read_max_chars", 100000)))
ADV_TOOL_RESULT_MAX_CHARS = int(os.getenv("ADV_TOOL_RESULT_MAX_CHARS", _ADVANCED.get("tool_result_max_chars", 4000)))
ADV_CODE_TOTAL_OUTPUT_LIMIT = int(os.getenv("ADV_CODE_TOTAL_OUTPUT_LIMIT", _ADVANCED.get("code_total_output_limit", 100000)))
ADV_MEMORY_SEARCH_TOP_K = int(os.getenv("ADV_MEMORY_SEARCH_TOP_K", _ADVANCED.get("memory_search_top_k", 3)))
ADV_RELEVANCE_THRESHOLD = float(os.getenv("ADV_RELEVANCE_THRESHOLD", _ADVANCED.get("relevance_threshold", 0.5)))
ADV_PREFERENCE_CONFIDENCE_THRESHOLD = float(os.getenv("ADV_PREFERENCE_CONFIDENCE_THRESHOLD", _ADVANCED.get("preference_confidence_threshold", 0.6)))

MCP_ENABLED = os.getenv("MCP_ENABLED", str(_YAML_CFG.get("mcp", {}).get("enabled", "true"))).lower() == "true"

# 工具按需加载（Tool Search）：启用后 LLM 仅看到 3 个桥接工具，
# 通过 tool_search → tool_describe → tool_call 流程按需发现和调用工具，
# 大幅减少每轮 API 的 token 消耗（"MCP 工具税"）。
TOOL_SEARCH_ENABLED = os.getenv(
    "TOOL_SEARCH_ENABLED",
    str(_YAML_CFG.get("tool_search", {}).get("enabled", "true")),
).lower() == "true"
# 始终全量加载的工具（绕过桥接，直接暴露给 LLM），逗号分隔
TOOL_SEARCH_ALWAYS_LOAD = [
    t.strip()
    for t in os.getenv(
        "TOOL_SEARCH_ALWAYS_LOAD",
        ",".join(_YAML_CFG.get("tool_search", {}).get("always_load", [])),
    ).split(",")
    if t.strip()
]
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
MCP_SERVERS = _YAML_CFG.get("mcp", {}).get("servers", {})

# 过滤掉 enabled: false 的 MCP server
MCP_SERVERS = {k: v for k, v in MCP_SERVERS.items() if v.get("enabled", True) is not False}

_skip_servers = []
for _srv_name, _srv_cfg in MCP_SERVERS.items():
    _env = _srv_cfg.get("env", {})
    _env_from_dotenv = _srv_cfg.pop("env_from_dotenv", [])
    for _key in _env_from_dotenv:
        _val = os.getenv(_key, "")
        if not _val:
            # 必需的环境变量为空，跳过该 MCP 服务器
            logger.info(f"MCP server '{_srv_name}' skipped: env '{_key}' not set")
            _skip_servers.append(_srv_name)
            break
        _env[_key] = _val
    if _srv_name not in _skip_servers and _env:
        _srv_cfg["env"] = _env

for _srv_name in _skip_servers:
    MCP_SERVERS.pop(_srv_name, None)

# Agent 后端：legacy（简单循环）或 langgraph（状态图，支持中断/确认/自愈）
AGENT_BACKEND = os.getenv("AGENT_BACKEND", "langgraph")

# 全局运行标志（Ctrl+C 时设为 False）
running = True


def ensure_data_dirs():
    """确保内部数据目录存在（向量库、调试快照等）"""
    dirs = [DATA_DIR, DATA_DIR / "chroma", DATA_DIR / "debug"]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def ensure_workspace():
    """确保工作区目录结构存在，首次运行时创建 venv"""
    for sub in ["downloads", "temp", "output", "scripts", "data"]:
        (WORKSPACE_DIR / sub).mkdir(parents=True, exist_ok=True)
    if not VENV_PYTHON.exists():
        subprocess.run(
            [sys.executable, "-m", "venv", str(WORKSPACE_DIR / ".venv")],
            check=True,
        )
        print(f"venv 已创建: {WORKSPACE_DIR / '.venv'}")


def init_workspace_packages(profile: str = "basic"):
    """向工作区 venv 安装预配置的 Python 包（basic/full 两档）"""
    import yaml
    with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    packages = cfg.get("workspace", {}).get("venv_packages", {}).get(profile, [])
    if not packages:
        return
    pip = WORKSPACE_DIR / ".venv" / "Scripts" / "pip.exe"
    if not pip.exists():
        return
    marker = WORKSPACE_DIR / ".venv" / f".packages_{profile}_installed"
    if marker.exists():
        return
    print(f"正在安装工作区包 ({profile}): {', '.join(packages)}")
    subprocess.run([str(pip), "install", "--quiet"] + packages, check=True)
    marker.write_text(",".join(packages), encoding="utf-8")
    print(f"工作区包安装完成")


_SYSTEM_PROMPT_BASE = _PROMPTS.get("system_prompt", "你是一个通过微信与用户聊天的 AI 助手，运行在用户的个人电脑上。你可以访问本地文件系统。")

# 静态提示词部分（环境信息、规则、原则、使用原则、内容限制、文件存储规则）
_STATIC_PROMPT = f"""

## 用户环境信息
- 工作区目录: {WORKSPACE_DIR}（你的主战场，所有文件操作优先在此进行）
- 工作区输出: {WORKSPACE_DIR / "output"}（图表、文档、生成文件保存位置）
- 工作区下载: {WORKSPACE_DIR / "downloads"}（下载文件保存位置）
- 工作区临时: {WORKSPACE_DIR / "temp"}（临时文件，用后清理）
- 工作区脚本: {WORKSPACE_DIR / "scripts"}
- 用户主目录: {USER_HOME}
- 用户桌面: {USER_DESKTOP}
- 操作系统: Windows

## 核心规则
- 用中文回复，除非用户用其他语言
- 回复简洁自然，像朋友聊天一样
- 用户 ID 格式为 xxx@im.wechat，这是微信内部标识，正常聊天即可
- 如果用户问你是谁，诚实回答

## 最重要的原则：主动操作，不要让用户代劳
- 你能直接下载图片、文件到工作区，不要说"我无法下载"或让用户手动保存
- 用户发来图片时，图片内容已经通过视觉模型识别，你可以直接基于图片内容操作
- 用户说"把图片插入文档"→ 你直接用 run_python 在工作区生成文档，不要让用户先保存图片
- 用户说"帮我处理这个文件"→ 你直接在工作区操作，完成后用 send_file 发给用户
- 不要说"请先保存到桌面"之类的话，你完全可以自己下载和处理
- 所有中间文件、临时文件都在工作区内处理，最终结果用 send_file 发给用户
"""

# 工具分类和详细描述（用于系统提示词）
# key: 工具名, value: (分类, 描述)
_TOOL_PROMPT_DETAILS = {
    # 文件操作
    "read_file": ("文件操作", "读取文件内容。当用户问'看看xxx文件'时使用"),
    "write_file": ("文件操作", f"写入文件。内容保存到 {WORKSPACE_DIR} 目录"),
    "list_directory": ("文件操作", "浏览目录。当用户说'桌面有什么文件'时使用"),
    "search_files": ("文件操作", "搜索文件。当用户说'找一下xxx文件'时使用"),
    "send_file": ("文件操作", "发送文件给用户。当用户说'发给我'/'把xxx发过来'时使用"),
    "batch_rename": ("文件操作", "批量重命名文件。当用户说'把这些文件重命名'时使用"),
    "organize_files": ("文件操作", "按规则整理文件。当用户说'整理一下桌面'/'按类型分类'时使用"),
    # 代码执行
    "run_python": ("代码执行", "执行 Python 代码。支持 pandas/numpy/matplotlib/python-docx/Pillow 等库。缺少包时先用 install_package 安装"),
    "install_package": ("代码执行", "在工作区虚拟环境中安装 Python 包。仅安装到 workspace/.venv，不影响系统"),
    # 系统控制
    "run_shell": ("系统控制", "执行系统命令。需要先确认再执行，仅限只读操作"),
    "system_action": ("系统控制", "执行系统操作（音量调节/锁屏/休眠）。当用户说'把音量调大'/'锁屏'时使用"),
    "open_app": ("系统控制", "打开应用程序（Chrome/VSCode/记事本/计算器/资源管理器等）。当用户说'打开浏览器'时使用"),
    "get_active_window": ("系统控制", "获取当前活跃窗口标题"),
    "clipboard_read": ("系统控制", "读取剪贴板文本"),
    "list_processes": ("系统控制", "列出运行中的进程。当用户说'看看有什么程序在运行'时使用"),
    "kill_process": ("系统控制", "终止进程。当用户说'关掉xxx程序'时使用"),
    "check_port": ("系统控制", "检查端口占用。当用户说'80端口被谁占了'时使用"),
    # 网络
    "web_fetch": ("网络", "抓取网页内容。提取正文文本"),
    "webpage_snapshot": ("网络", "网页快照。将网页渲染保存为 PDF"),
    "download_video": ("网络", "下载视频。当用户说'帮我下载这个视频'时使用"),
    "http_download": ("网络", "下载文件。当用户说'下载这个文件'/'帮我下载'时使用。GitHub 仓库链接会自动通过镜像加速下载 ZIP。**禁止用 curl/wget 下载，必须用此工具**"),
    "aria2_download": ("网络", "Aria2 高速下载（需本地 Aria2 服务）。大文件或需要断点续传时使用"),
    "aria2_status": ("网络", "查询 Aria2 下载状态"),
    # 媒体处理
    "ocr_image": ("媒体处理", "OCR 识别图片中的文字。当用户说'识别图片文字'/'图片里写了什么'时使用"),
    "transcribe_audio": ("媒体处理", "音频转录为文字。当用户说'把录音转成文字'时使用"),
    "video_add_subtitles": ("媒体处理", "给视频添加字幕"),
    # 磁盘管理
    "scan_large_files": ("磁盘管理", "扫描大文件。当用户说'磁盘空间不够了'/'找大文件'时使用"),
    "find_duplicates": ("磁盘管理", "查找重复文件。当用户说'帮我找重复文件'时使用"),
    "disk_usage": ("磁盘管理", "磁盘空间统计。当用户说'看看磁盘用了多少'时使用"),
    # 技能与监控
    "schedule_task": ("技能与监控", "设置定时任务。当用户说'每天早上9点提醒我'时使用"),
    "monitor_url": ("技能与监控", "监控 URL 变化。当用户说'帮我盯着这个网页'时使用"),
    # 飞书
    "feishu_create_document": ("飞书", "创建飞书文档。当用户说'帮我创建一个飞书文档'/'在飞书写个文档'时使用。创建成功后必须将文档链接返回给用户"),
    "feishu_add_document_blocks": ("飞书", "向飞书文档添加内容。当用户说'往文档里写点内容'/'在文档中添加标题和正文'时使用"),
    "feishu_get_document": ("飞书", "获取飞书文档内容。当用户说'看看这个飞书文档'/'读取飞书文档内容'时使用"),
    "feishu_get_document_blocks": ("飞书", "获取飞书文档块列表。当需要编辑/修改已有文档时，先调用此工具获取 block_id，再调用更新或删除工具"),
    "feishu_update_document_block": ("飞书", "更新飞书文档中指定块的内容。当用户说'修改文档中的某段'/'编辑文档内容'时使用，需先通过 feishu_get_document_blocks 获取 block_id"),
    "feishu_batch_update_blocks": ("飞书", "批量更新飞书文档多个块的内容。当需要同时修改文档中多处内容时使用"),
    "feishu_delete_document_block": ("飞书", "删除飞书文档中指定的块。当用户说'删掉文档中的某段'/'去掉这个标题'时使用"),
    "feishu_create_bitable": ("飞书", "创建飞书多维表格。当用户说'帮我创建一个多维表格'/'在飞书建个表'时使用。创建成功后必须将表格链接返回给用户"),
    "feishu_create_bitable_table": ("飞书", "在多维表格中创建数据表。当用户说'在表格里加个数据表'时使用"),
    "feishu_add_bitable_field": ("飞书", "向多维表格添加字段。当用户说'给表格加一列'/'添加字段'时使用"),
    "feishu_add_bitable_records": ("飞书", "向多维表格添加记录。当用户说'往表格里添加数据'/'插入几条记录'时使用"),
    "feishu_list_bitable": ("飞书", "查看多维表格记录。当用户说'看看表格里有什么数据'时使用"),
    "feishu_list_bitable_tables": ("飞书", "列出多维表格的数据表。当用户说'看看有哪些数据表'时使用"),
    "feishu_create_folder": ("飞书", "创建飞书云空间文件夹。当用户说'在飞书创建个文件夹'时使用。创建成功后必须将文件夹链接返回给用户"),
    "feishu_list_folder": ("飞书", "列出飞书文件夹内容。当用户说'看看飞书云盘里有什么'时使用"),
    "feishu_upload_file": ("飞书", "上传文件到飞书云盘。当用户说'把这个文件传到飞书'时使用"),
    "feishu_send_message": ("飞书", "发送飞书消息。当用户说'给xxx发个飞书消息'时使用"),
    "feishu_send_group_message": ("飞书", "发送飞书群消息。当用户说'在飞书群里发消息'时使用"),
    "feishu_list_calendar": ("飞书", "查看飞书日历。当用户说'看看我今天的日程'/'飞书日历有什么安排'时使用"),
    "feishu_add_permission": ("飞书", "给飞书文档/表格添加权限或设置公开分享。当用户说'把这个文档分享给别人'/'设置文档权限'时使用。创建文档后默认只有应用能访问，需要用此工具设置分享"),
    "feishu_delete_file": ("飞书", "删除飞书云空间中的文件/文档/表格。当用户说'删除这个飞书文档'/'把那个表格删了'时使用。删除后进入回收站可恢复"),
    "feishu_copy_file": ("飞书", "复制飞书文件到指定文件夹。当用户说'复制这个文档'/'把这个表格复制一份'时使用。复制成功后必须将新文件链接返回给用户"),
    "feishu_move_file": ("飞书", "移动飞书文件到指定文件夹。当用户说'移动这个文档'/'把文件移到另一个文件夹'时使用"),
}

# 工具使用原则和内容限制（静态）
_TOOL_RULES = f"""

## 工具使用原则
- 用户要求文件操作时，主动使用工具，不要只说'我做不到'
- 先 list_directory 或 search_files 确认文件存在，再 read_file 或 send_file
- 发送文件时用绝对路径，不要用相对路径
- 遇到错误如实告诉用户
- 数据分析时优先使用 run_python，图表自动保存到 {WORKSPACE_DIR / "output"}
- 需要处理图片时，用 run_python + Pillow 在工作区内操作
- **下载文件必须用 http_download 工具，禁止用 run_shell + curl/wget**
- **检测文件类型用 run_python 的 mimetypes 模块，禁止用 run_shell + file 命令**

## 内容限制
- 不要自行编造 URL 或链接，但工具返回的链接（如飞书文档链接）必须如实转达给用户
- 不要使用 Markdown 表格（微信不支持）
- 代码块用 ``` 包裹
- 单条消息控制在 1500 字以内
- 绝对不要执行危险命令（删除、格式化、修改系统设置等）

## 回复格式要求（微信友好）
- 标题用 ■ 符号，如：■ 市场表现（二级标题用 ■■）
- 强调用【】符号，如：【重要】
- 列表用 • 符号，如：• 第一项
- 行内代码用「」符号，如：「hello」
- 引用用 ┃ 符号，如：┃ 名言
- 不要使用 Markdown 的 ##、**、- 等语法（微信不渲染）
- 每个逻辑段落之间用空行分隔，便于分段发送

## 文件存储规则
- 所有文件操作默认在工作区 {WORKSPACE_DIR} 内完成
- 生成文档、图表 → {WORKSPACE_DIR / "output"}
- 下载文件 → {WORKSPACE_DIR / "downloads"}
- 临时文件 → {WORKSPACE_DIR / "temp"}，用后及时清理
- 当用户提到'桌面'时，使用 {USER_DESKTOP} 路径
- 当用户提到相对路径时（如'Documents'），基于 {USER_HOME} 解析
- 当用户提到'工作区'或'workspace'时，使用 {WORKSPACE_DIR} 路径
- 禁止向 C:\\Windows、C:\\Program Files 等系统目录写入文件
"""


def _build_tool_section() -> str:
    """从 ToolRegistry 动态生成工具描述部分。

    Tool Search 模式下，只生成桥接工具 + always_load 工具的描述，
    引导 LLM 通过 tool_search → tool_describe → tool_call 流程按需发现工具。
    传统模式下，列出所有工具。
    """
    from tools.registry import ToolRegistry
    from tools.base import ToolType

    # Tool Search 模式：简洁的桥接工具引导
    if TOOL_SEARCH_ENABLED:
        lines = [
            "## 可用工具",
            "你可以通过以下流程按需发现和使用工具：",
            "",
            "1. **tool_search(query)** — 搜索与你的意图匹配的工具",
            "2. **tool_describe(tool_name)** — 查看指定工具的完整参数格式",
            "3. **tool_call(tool_name, arguments)** — 执行指定工具",
            "",
            "当你需要执行操作时，先用 tool_search 搜索相关工具，",
            "再用 tool_describe 查看参数格式，最后用 tool_call 执行。",
            "不要猜测工具名或参数格式，务必先搜索和查看。",
            "",
            "## 工具概览",
            "你可以使用以下类别的工具（通过 tool_search 搜索具体工具名）：",
            "- 文件操作：读写文件、发送文件、批量重命名、整理文件",
            "- 代码执行：运行 Python 代码、安装包",
            "- 系统控制：执行命令、打开应用、音量/锁屏、进程管理",
            "- 网络访问：抓取网页(web_fetch)、下载文件/视频、Aria2 高速下载",
            "- 媒体处理：OCR 识别、音频转录、视频字幕",
            "- 磁盘管理：扫描大文件、查重复、磁盘统计",
            "- 定时监控：定时任务、URL 监控",
            "- 飞书：文档、表格、云盘、消息、日历",
            "- 地图服务：百度地图、高德地图（地理编码、路线规划、天气查询）",
            "",
            "## 搜索策略",
            "- tool_search 按关键词匹配工具描述，使用操作类关键词效果最好（如「读取文件」「抓取网页」）",
            "- 如果搜索结果与意图不匹配，尝试：换用通用操作词、或直接搜索工具名",
            "- 常用工具可直接搜索：web_fetch（抓取网页）、run_python（执行代码）、read_file（读文件）",
            "",
            "## 飞书操作注意",
            "- 使用飞书创建文档、表格、文件夹等操作后，必须将工具返回的链接转达给用户",
            "- 飞书创建的资源默认只有应用能访问，工具会自动设置公开分享，如未成功需提醒用户手动设置权限",
        ]
        # always_load 工具直接列出
        always_names = set(TOOL_SEARCH_ALWAYS_LOAD)
        if always_names:
            all_defs = ToolRegistry.get_all_defs()
            always_tools = [td for td in all_defs if td.name in always_names]
            if always_tools:
                lines.append("")
                lines.append("### 始终可用的工具")
                lines.append("以下工具可直接调用，无需通过 tool_search 搜索：")
                for td in always_tools:
                    lines.append(f"- **{td.name}**: {td.description}")
        return "\n".join(lines)

    # 传统模式：全量列出所有工具
    # 收集所有已注册工具
    all_defs = ToolRegistry.get_all_defs()
    registered_names = {td.name for td in all_defs}

    # 按分类组织已知工具
    categories: dict[str, list[tuple[str, str]]] = {}
    seen = set()
    for name, (cat, desc) in _TOOL_PROMPT_DETAILS.items():
        if name in registered_names:
            categories.setdefault(cat, []).append((name, desc))
            seen.add(name)

    # 未在 _TOOL_PROMPT_DETAILS 中的工具（如 MCP 工具、skill 工具）
    extra_tools: list[tuple[str, str]] = []
    for td in all_defs:
        if td.name not in seen and td.name.startswith("skill_"):
            extra_tools.append((td.name, "执行预定义技能。当用户说'进入xxx模式'时使用"))
            seen.add(td.name)
        elif td.name not in seen:
            # MCP 工具等：使用 ToolDef.description
            meta = ToolRegistry.get_meta(td.name)
            prefix = ""
            if meta and meta.type == ToolType.MCP:
                # 去掉 [MCP:xxx] 前缀
                desc = td.description
                if desc.startswith("[MCP:"):
                    desc = desc.split("]", 1)[-1].strip()
                prefix = "（MCP 工具）"
            else:
                desc = td.description
            extra_tools.append((td.name, f"{desc}{prefix}"))
            seen.add(td.name)

    # 构建文本
    lines = ["## 可用工具", "你可以使用以下工具来帮助用户：", ""]
    for cat, tools in categories.items():
        lines.append(f"### {cat}")
        for name, desc in tools:
            lines.append(f"- **{name}**: {desc}")
        lines.append("")

    if extra_tools:
        lines.append("### 扩展工具")
        for name, desc in extra_tools:
            lines.append(f"- **{name}**: {desc}")

    return "\n".join(lines)


def get_system_prompt() -> str:
    """获取完整的系统提示词（动态生成工具描述部分）。"""
    tool_section = _build_tool_section()
    return _SYSTEM_PROMPT_BASE + _STATIC_PROMPT + "\n" + tool_section + _TOOL_RULES

