import logging
import re
import subprocess

import config
from config import WORKSPACE_DIR, SHELL_TIMEOUT
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry

logger = logging.getLogger("wxagent.tools.system")


TOOL_META = ToolMeta(
    name="system",
    type=ToolType.BUILTIN,
    description="系统操作工具集：Shell命令、剪贴板、窗口感知",
    version="1.0.0",
    tags=["system", "shell", "clipboard"],
)


def _extract_affected_targets(command: str) -> list[str]:
    path_pattern = re.compile(r'(?:[A-Za-z]:\\|~/?|\./)[\w\\/.-]+')
    targets = path_pattern.findall(command)
    return targets or ["（命令中未包含明确路径，请人工确认）"]


def _run_shell(command: str, state=None, user_id: str = "", _skip_risk_check: bool = False) -> ToolResult:
    from security.risk_levels import classify_command, RiskLevel, is_dev_mode
    from security.audit import audit_logger

    if not _skip_risk_check:
        risk, reason = classify_command(command)

        if risk == RiskLevel.DANGEROUS:
            audit_logger.log(user_id, "run_shell", risk, {"command": command}, "blocked_confirmation_required")
            return ToolResult(
                success=False,
                error=f"命令需要确认: {reason}",
                requires_confirmation=True,
                confirmation_detail={
                    "type": "dangerous_command",
                    "command": command,
                    "risk_level": "dangerous",
                    "reason": reason,
                    "affected_targets": _extract_affected_targets(command),
                },
            )

        if risk == RiskLevel.CAUTION:
            # AI 审查：如果启用且 caution 在审查级别中，调用 AI 判断
            try:
                from security.ai_reviewer import is_enabled, get_review_levels
                if is_enabled() and "caution" in get_review_levels():
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    async def _do_review():
                        from security.ai_reviewer import review_command
                        return await review_command(command)

                    if loop and loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            ai_result = pool.submit(asyncio.run, _do_review()).result(timeout=15)
                    else:
                        ai_result = asyncio.run(_do_review())

                    verdict = ai_result.get("verdict", "ask_user")
                    ai_reason = ai_result.get("reason", "")
                    ai_score = ai_result.get("risk_score", 0.5)

                    if verdict == "deny":
                        audit_logger.log(user_id, "run_shell", risk,
                                         {"command": command, "ai_verdict": verdict, "ai_reason": ai_reason},
                                         "blocked_by_ai_reviewer")
                        return ToolResult(
                            success=False,
                            error=f"AI 安全审查拒绝执行: {ai_reason}",
                            requires_confirmation=True,
                            confirmation_detail={
                                "type": "ai_denied",
                                "command": command,
                                "risk_level": "caution",
                                "reason": ai_reason,
                                "risk_score": ai_score,
                            },
                        )
                    elif verdict == "ask_user":
                        audit_logger.log(user_id, "run_shell", risk,
                                         {"command": command, "ai_verdict": verdict}, "ai_ask_user")
                        return ToolResult(
                            success=False,
                            error=f"AI 安全审查建议确认: {ai_reason}",
                            requires_confirmation=True,
                            confirmation_detail={
                                "type": "ai_ask_user",
                                "command": command,
                                "risk_level": "caution",
                                "reason": ai_reason,
                                "risk_score": ai_score,
                            },
                        )
                    # verdict == "allow" → 继续执行
            except Exception as e:
                logger.warning("AI 审查调用失败，降级为关键词结果: %s", e)

            audit_logger.log(user_id, "run_shell", risk, {"command": command},
                            "caution_dev_auto" if is_dev_mode() else "caution_executed")

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=SHELL_TIMEOUT, cwd=str(WORKSPACE_DIR),
            encoding="utf-8", errors="replace",
        )
        output = (result.stdout or "") + (result.stderr or "")
        return ToolResult(
            success=result.returncode == 0,
            content=output[:config.ADV_TOOL_RESULT_MAX_CHARS],
            error=(result.stderr or f"退出码: {result.returncode}") if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error="命令执行超时 (30秒)")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _clipboard_read(state=None, user_id: str = "") -> ToolResult:
    try:
        import pyperclip
        text = pyperclip.paste()
        if not text:
            return ToolResult(success=True, content="", display="剪贴板为空")
        from security.sanitizer import sanitize_for_llm
        clean = sanitize_for_llm(text)
        return ToolResult(
            success=True, content=clean,
            display=f"剪贴板: {text[:80]}{'...' if len(text) > 80 else ''}",
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def _get_active_window(state=None, user_id: str = "") -> ToolResult:
    try:
        script = (
            '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; '
            '(Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | '
            'Select-Object -First 5 MainWindowTitle).MainWindowTitle'
        )
        result = subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True, timeout=5,
        )
        content = result.stdout.decode("utf-8", errors="replace").strip()
        return ToolResult(success=True, content=content)
    except Exception as e:
        return ToolResult(success=False, error=str(e))


ToolRegistry.register(
    ToolDef(
        name="run_shell",
        description="执行系统命令并返回输出。危险命令需要用户确认。"
                    "支持三级风险分类：SAFE/CAUTION/DANGEROUS。",
        parameters={
            "command": {"type": "string", "description": "要执行的 shell 命令"},
        },
        required=["command"],
    ),
    _run_shell,
)

ToolRegistry.register(
    ToolDef(
        name="clipboard_read",
        description="读取剪贴板文本内容，自动脱敏疑似密钥。",
        parameters={},
    ),
    _clipboard_read,
)

ToolRegistry.register(
    ToolDef(
        name="get_active_window",
        description="获取当前活跃窗口标题，用于感知用户正在使用的应用。",
        parameters={},
    ),
    _get_active_window,
)
