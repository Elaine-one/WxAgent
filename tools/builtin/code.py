import ast
import subprocess
import time
from pathlib import Path

import config
from config import WORKSPACE_DIR, VENV_PYTHON, PYTHON_TIMEOUT, PYTHON_MAX_OUTPUT
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry


TOOL_META = ToolMeta(
    name="code",
    type=ToolType.BUILTIN,
    description="代码执行工具集：Python代码执行、包安装",
    version="1.0.0",
    tags=["code", "python", "execute"],
)

ALLOWED_MODULES = {
    "pandas", "numpy", "matplotlib", "openpyxl", "csv", "json",
    "re", "math", "statistics", "datetime", "collections",
    "pdfplumber", "docx", "PIL", "io", "os", "pathlib",
    "sys", "sqlalchemy", "requests", "bs4", "httpx",
    "base64", "hashlib", "urllib", "secrets",
}

DANGEROUS_ATTRS = {
    "__import__", "exec", "eval", "compile",
    "globals", "locals", "getattr", "setattr",
    "delattr", "breakpoint",
    "system", "popen", "spawn", "remove", "unlink",
    "rmdir", "renames", "kill",
}


def _validate_code(code: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"语法错误: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_MODULES:
                    return False, f"禁止导入: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root not in ALLOWED_MODULES:
                    return False, f"禁止导入: {node.module}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in DANGEROUS_ATTRS:
                    return False, f"禁止调用: {node.func.id}"
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in DANGEROUS_ATTRS:
                    return False, f"禁止调用属性: {node.func.attr}"
    return True, ""


def _run_python(code: str, state=None, user_id: str = "") -> ToolResult:
    valid, msg = _validate_code(code)
    if not valid:
        return ToolResult(success=False, error=f"代码安全检查失败: {msg}")

    script_path = WORKSPACE_DIR / "scripts" / f"run_{int(time.time())}.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)

    lines = code.split("\n")
    indented = "\n".join("    " + line for line in lines)
    wrapped = (
        "import sys, json\n"
        "sys.stdout.reconfigure(encoding='utf-8')\n"
        "try:\n"
        f"{indented}\n"
        "except Exception as _e:\n"
        "    print(json.dumps({'__error__': str(_e), '__type__': type(_e).__name__}), file=sys.stderr)\n"
    )
    script_path.write_text(wrapped, encoding="utf-8")

    try:
        result = subprocess.run(
            [str(VENV_PYTHON), str(script_path)],
            capture_output=True, text=True, timeout=PYTHON_TIMEOUT,
            cwd=str(WORKSPACE_DIR),
            encoding="utf-8", errors="replace",
        )
        stdout = result.stdout[:PYTHON_MAX_OUTPUT]
        stderr = result.stderr[:PYTHON_MAX_OUTPUT]
        if len(result.stdout) + len(result.stderr) > config.ADV_CODE_TOTAL_OUTPUT_LIMIT:
            trunc_note = "\n\n[输出已截断，超出 100KB 限制]"
            stdout = stdout[:45000] + trunc_note if len(stdout) >= 45000 else stdout

        if result.returncode != 0:
            error_detail = stderr.strip() if stderr.strip() else f"退出码: {result.returncode}"
            if stdout.strip():
                error_detail = f"{stdout.strip()}\n--- 错误 ---\n{error_detail}"
            return ToolResult(success=False, content=stdout,
                            error=f"代码执行失败，请根据错误信息修改代码后重试:\n{error_detail}")

        artifacts = sorted(
            (WORKSPACE_DIR / "output").glob("*"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        artifact_path = str(artifacts[0]) if artifacts else None
        artifact_info = f"\n生成文件: {artifacts[0].name}" if artifacts else ""

        return ToolResult(
            success=True,
            content=stdout + artifact_info,
            display=stdout[:200] + ("..." if len(stdout) > 200 else ""),
            artifact_path=artifact_path,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error=f"执行超时 ({PYTHON_TIMEOUT}秒)，请优化代码或减少数据量后重试")
    except Exception as e:
        return ToolResult(success=False, error=str(e))
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass


BLOCKED_PACKAGES = {
    "tensorflow", "torch", "keras", "theano", "cupy",
    "paddlepaddle", "paddleocr", "faster-whisper",
}


def _install_package(package: str, state=None, user_id: str = "") -> ToolResult:
    pkg_lower = package.lower().replace("-", "").replace("_", "")
    for blocked in BLOCKED_PACKAGES:
        if blocked.replace("-", "").replace("_", "") in pkg_lower:
            return ToolResult(success=False, error=f"禁止安装 {package}：该包体积过大或需要特殊硬件，请联系管理员手动安装")

    pip = WORKSPACE_DIR / ".venv" / "Scripts" / "pip.exe"
    if not pip.exists():
        return ToolResult(success=False, error="venv 不存在，请重启程序")

    try:
        result = subprocess.run(
            [str(pip), "install", "--quiet", package],
            capture_output=True, text=True, timeout=config.ADV_PIP_INSTALL_TIMEOUT,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return ToolResult(success=False, error=f"安装失败: {result.stderr.strip()}")
        return ToolResult(success=True, content=f"{package} 已安装到工作区 venv")
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error=f"安装超时 ({config.ADV_PIP_INSTALL_TIMEOUT}秒)，包可能过大")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


ToolRegistry.register(
    ToolDef(
        name="install_package",
        description="在工作区虚拟环境中安装 Python 包。包仅安装到 workspace/.venv，不影响系统 Python。"
                    "安装成功后可在 run_python 中使用。禁止安装大型包（如 tensorflow、torch）。",
        parameters={
            "package": {"type": "string", "description": "要安装的包名，如 'python-docx'、'httpx'"},
        },
        required=["package"],
    ),
    _install_package,
)


ToolRegistry.register(
    ToolDef(
        name="run_python",
        description="执行 Python 代码并返回结果。支持 pandas/numpy/matplotlib/python-docx/Pillow/httpx 等。"
                    "代码在 workspace/.venv 中执行，可读取用户文件，图表保存到 workspace/output/。"
                    "如果代码执行失败，会返回错误信息，请根据错误修改代码后重新调用此工具。"
                    "如果缺少某个包，先用 install_package 安装。",
        parameters={
            "code": {"type": "string", "description": "要执行的 Python 代码"},
        },
        required=["code"],
    ),
    _run_python,
)
