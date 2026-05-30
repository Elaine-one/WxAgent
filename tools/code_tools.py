import ast
import subprocess
import time
from pathlib import Path

from config import WORKSPACE_DIR, VENV_PYTHON
from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

ALLOWED_MODULES = {
    "pandas", "numpy", "matplotlib", "openpyxl", "csv", "json",
    "re", "math", "statistics", "datetime", "collections",
    "pdfplumber", "docx", "PIL", "io", "os", "pathlib",
    "sys", "sqlalchemy", "requests", "bs4",
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
            capture_output=True, text=True, timeout=30,
            cwd=str(WORKSPACE_DIR),
            encoding="utf-8", errors="replace",
        )
        stdout = result.stdout[:50000]
        stderr = result.stderr[:50000]
        if len(result.stdout) + len(result.stderr) > 100_000:
            trunc_note = "\n\n[输出已截断，超出 100KB 限制]"
            stdout = stdout[:45000] + trunc_note if len(stdout) >= 45000 else stdout

        if result.returncode != 0:
            return ToolResult(success=False, content=stdout,
                            error=stderr or f"退出码: {result.returncode}")

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
        return ToolResult(success=False, error="执行超时 (30秒)")
    except Exception as e:
        return ToolResult(success=False, error=str(e))
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass


ToolRegistry.register(
    ToolDef(
        name="run_python",
        description="执行 Python 代码并返回结果。支持 pandas/numpy/matplotlib 等。"
                    "代码在 workspace/.venv 中执行，可读取用户文件，图表保存到 workspace/output/。",
        parameters={
            "code": {"type": "string", "description": "要执行的 Python 代码"},
        },
        required=["code"],
    ),
    _run_python,
)
