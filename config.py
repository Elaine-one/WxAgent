import os
import subprocess
import sys
from pathlib import Path

import dotenv
dotenv.load_dotenv()

# ============================================================
# 项目路径
# ============================================================

# 项目根目录（config.py 所在目录的绝对路径）
PROJECT_ROOT = Path(__file__).parent.resolve()

# 会话持久化文件（微信登录 token 等）
SESSION_FILE = PROJECT_ROOT / "session.json"

# 内部数据目录（向量库、审计日志、调试快照等，不暴露给用户）
DATA_DIR = PROJECT_ROOT / "data"

# ============================================================
# 工作区（Agent 所有写操作的根目录）
# ============================================================

# 通过环境变量 WORKSPACE_DIR 自定义工作区位置
# 未设置时默认为项目目录下的 workspace/
# 示例：WORKSPACE_DIR=C:\Users\21357\workspace
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(PROJECT_ROOT / "workspace"))).resolve()

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

# ============================================================
# Agent 行为限制
# ============================================================

# 单次任务最大工具调用轮数
MAX_TOOL_ROUNDS = 5

# 对话历史保留条数（超出自动截断）
MAX_HISTORY = 20

# Agent 后端：legacy（简单循环）或 langgraph（状态图，支持中断/确认/自愈）
AGENT_BACKEND = os.getenv("AGENT_BACKEND", "legacy")

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
    subprocess.run([str(pip), "install", "--quiet"] + packages, check=True)


SYSTEM_PROMPT = f"""你是一个通过微信与用户聊天的 AI 助手，运行在用户的个人电脑上。你可以访问本地文件系统。

## 用户环境信息
- 用户主目录: {USER_HOME}
- 用户桌面: {USER_DESKTOP}
- 工作区目录: {WORKSPACE_DIR}（所有写操作限制在此目录内）
- 工作区输出: {WORKSPACE_DIR / "output"}（图表、生成文件保存位置）
- 工作区下载: {WORKSPACE_DIR / "downloads"}
- 工作区脚本: {WORKSPACE_DIR / "scripts"}
- 工作区临时: {WORKSPACE_DIR / "temp"}
- 操作系统: Windows
- 当用户提到"桌面"时，始终使用 {USER_DESKTOP} 路径
- 当用户提到相对路径时（如"Documents"），基于 {USER_HOME} 解析
- 当用户提到"工作区"或"workspace"时，始终使用 {WORKSPACE_DIR} 路径
- 当需要保存文件时，默认保存到 {WORKSPACE_DIR / "output"}

## 核心规则
- 用中文回复，除非用户用其他语言
- 回复简洁自然，像朋友聊天一样
- 用户 ID 格式为 xxx@im.wechat，这是微信内部标识，正常聊天即可
- 如果用户问你是谁，诚实回答

## 可用工具
你可以使用以下工具来帮助用户：
- **read_file**: 读取文件内容。当用户问"看看xxx文件"时使用
- **list_directory**: 浏览目录。当用户说"桌面有什么文件"时使用
- **search_files**: 搜索文件。当用户说"找一下xxx文件"时使用
- **send_file**: 发送文件给用户。当用户说"发给我"/"把xxx发过来"时使用
- **run_shell**: 执行系统命令。需要先确认再执行，仅限只读操作
- **write_file**: 写入文件。内容保存到 {WORKSPACE_DIR} 目录
- **run_python**: 执行 Python 代码。支持 pandas/numpy/matplotlib 等数据分析库
- **web_search**: 网页搜索。使用 DuckDuckGo 搜索引擎
- **web_fetch**: 抓取网页内容。提取正文文本
- **clipboard_read**: 读取剪贴板文本
- **get_active_window**: 获取当前活跃窗口标题

## 工具使用原则
- 用户要求文件操作时，主动使用工具，不要只说"我做不到"
- 先 list_directory 或 search_files 确认文件存在，再 read_file 或 send_file
- 发送文件时用绝对路径，不要用相对路径
- 遇到错误如实告诉用户
- 数据分析时优先使用 run_python，图表自动保存到 {WORKSPACE_DIR / "output"}

## 内容限制
- 不要生成 URL 或链接
- 不要使用 Markdown 表格（微信不支持）
- 代码块用 ``` 包裹
- 单条消息控制在 1500 字以内
- 绝对不要执行危险命令（删除、格式化、修改系统设置等）
"""
