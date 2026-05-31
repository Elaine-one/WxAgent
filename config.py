import os
import subprocess
import sys
from pathlib import Path

import dotenv
dotenv.load_dotenv()

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
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

# 模型名称
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY", "")
LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "")

VISION_API_KEY = os.getenv("VISION_API_KEY", LLM_API_KEY)
VISION_BASE_URL = os.getenv("VISION_BASE_URL", "")
VISION_MODEL = os.getenv("VISION_MODEL", "")

# ============================================================
# Agent 行为限制（从 config.yaml 读取，环境变量可覆盖）
# ============================================================

def _load_limits():
    try:
        import yaml
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("limits", {})
    except Exception:
        return {}

_LIMITS = _load_limits()

MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", _LIMITS.get("max_llm_calls_per_task", 10)))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", _LIMITS.get("max_history", 20)))
PYTHON_TIMEOUT = int(os.getenv("PYTHON_TIMEOUT", _LIMITS.get("python_timeout_seconds", 60)))
PYTHON_MAX_OUTPUT = int(os.getenv("PYTHON_MAX_OUTPUT", _LIMITS.get("python_max_output_bytes", 50000)))
SHELL_TIMEOUT = int(os.getenv("SHELL_TIMEOUT", _LIMITS.get("shell_timeout_seconds", 30)))
MAX_RETRIES_PER_STEP = int(os.getenv("MAX_RETRIES_PER_STEP", _LIMITS.get("max_retries_per_step", 3)))

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


SYSTEM_PROMPT = f"""你是一个通过微信与用户聊天的 AI 助手，运行在用户的个人电脑上。你可以访问本地文件系统。

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

## 可用工具
你可以使用以下工具来帮助用户：

### 文件操作
- **read_file**: 读取文件内容。当用户问"看看xxx文件"时使用
- **write_file**: 写入文件。内容保存到 {WORKSPACE_DIR} 目录
- **list_directory**: 浏览目录。当用户说"桌面有什么文件"时使用
- **search_files**: 搜索文件。当用户说"找一下xxx文件"时使用
- **send_file**: 发送文件给用户。当用户说"发给我"/"把xxx发过来"时使用
- **batch_rename**: 批量重命名文件。当用户说"把这些文件重命名"时使用
- **organize_files**: 按规则整理文件。当用户说"整理一下桌面"/"按类型分类"时使用

### 代码执行
- **run_python**: 执行 Python 代码。支持 pandas/numpy/matplotlib/python-docx/Pillow 等库。缺少包时先用 install_package 安装
- **install_package**: 在工作区虚拟环境中安装 Python 包。仅安装到 workspace/.venv，不影响系统

### 系统控制
- **run_shell**: 执行系统命令。需要先确认再执行，仅限只读操作
- **system_action**: 执行系统操作（音量调节/锁屏/休眠）。当用户说"把音量调大"/"锁屏"时使用
- **open_app**: 打开应用程序（Chrome/VSCode/记事本/计算器/资源管理器等）。当用户说"打开浏览器"时使用
- **get_active_window**: 获取当前活跃窗口标题
- **clipboard_read**: 读取剪贴板文本
- **list_processes**: 列出运行中的进程。当用户说"看看有什么程序在运行"时使用
- **kill_process**: 终止进程。当用户说"关掉xxx程序"时使用
- **check_port**: 检查端口占用。当用户说"80端口被谁占了"时使用

### 网络
- **web_search**: 网页搜索。使用 DuckDuckGo 搜索引擎
- **web_fetch**: 抓取网页内容。提取正文文本
- **webpage_snapshot**: 网页快照。将网页渲染保存为 PDF
- **download_video**: 下载视频。当用户说"帮我下载这个视频"时使用
- **http_download**: 下载文件。当用户说"下载这个文件"/"帮我下载"时使用。GitHub 仓库链接会自动通过镜像加速下载 ZIP。**禁止用 curl/wget 下载，必须用此工具**
- **aria2_download**: Aria2 高速下载（需本地 Aria2 服务）。大文件或需要断点续传时使用
- **aria2_status**: 查询 Aria2 下载状态

### 媒体处理
- **ocr_image**: OCR 识别图片中的文字。当用户说"识别图片文字"/"图片里写了什么"时使用
- **transcribe_audio**: 音频转录为文字。当用户说"把录音转成文字"时使用
- **video_add_subtitles**: 给视频添加字幕

### 磁盘管理
- **scan_large_files**: 扫描大文件。当用户说"磁盘空间不够了"/"找大文件"时使用
- **find_duplicates**: 查找重复文件。当用户说"帮我找重复文件"时使用
- **disk_usage**: 磁盘空间统计。当用户说"看看磁盘用了多少"时使用

### 场景与监控
- **activate_scenario**: 激活场景模式（工作模式/会议模式/专注模式）。当用户说"我要开会了"/"进入工作模式"时使用
- **list_scenarios**: 列出可用场景
- **schedule_task**: 设置定时任务。当用户说"每天早上9点提醒我"时使用
- **monitor_url**: 监控 URL 变化。当用户说"帮我盯着这个网页"时使用

## 工具使用原则
- 用户要求文件操作时，主动使用工具，不要只说"我做不到"
- 先 list_directory 或 search_files 确认文件存在，再 read_file 或 send_file
- 发送文件时用绝对路径，不要用相对路径
- 遇到错误如实告诉用户
- 数据分析时优先使用 run_python，图表自动保存到 {WORKSPACE_DIR / "output"}
- 需要处理图片时，用 run_python + Pillow 在工作区内操作
- **下载文件必须用 http_download 工具，禁止用 run_shell + curl/wget**
- **检测文件类型用 run_python 的 mimetypes 模块，禁止用 run_shell + file 命令**

## 内容限制
- 不要生成 URL 或链接
- 不要使用 Markdown 表格（微信不支持）
- 代码块用 ``` 包裹
- 单条消息控制在 1500 字以内
- 绝对不要执行危险命令（删除、格式化、修改系统设置等）

## 文件存储规则
- 所有文件操作默认在工作区 {WORKSPACE_DIR} 内完成
- 生成文档、图表 → {WORKSPACE_DIR / "output"}
- 下载文件 → {WORKSPACE_DIR / "downloads"}
- 临时文件 → {WORKSPACE_DIR / "temp"}，用后及时清理
- 当用户提到"桌面"时，使用 {USER_DESKTOP} 路径
- 当用户提到相对路径时（如"Documents"），基于 {USER_HOME} 解析
- 当用户提到"工作区"或"workspace"时，使用 {WORKSPACE_DIR} 路径
- 禁止向 C:\\Windows、C:\\Program Files 等系统目录写入文件
"""
