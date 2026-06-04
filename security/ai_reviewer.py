"""AI 安全审查器

对关键词匹配无法确定的命令，使用 LLM 进行意图判断。
配置在 config.yaml 的 ai_reviewer 节。
"""

import json
import logging

import yaml

logger = logging.getLogger("wxagent.security.ai_reviewer")

# 缓存配置
_config: dict = {}


def _load_config() -> dict:
    """加载 AI 审查器配置。"""
    global _config
    if _config:
        return _config
    try:
        from config import PROJECT_ROOT
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        # 优先使用顶层 ai_reviewer，兼容 security.ai_reviewer
        _config = cfg.get("ai_reviewer", cfg.get("security", {}).get("ai_reviewer", {}))
    except Exception:
        pass
    return _config


def is_enabled() -> bool:
    """AI 审查器是否启用。"""
    cfg = _load_config()
    return cfg.get("enabled", False)


def get_review_levels() -> list[str]:
    """获取需要 AI 审查的风险级别列表。"""
    cfg = _load_config()
    return cfg.get("review_levels", [])


def get_max_command_length() -> int:
    """获取命令最大长度限制。"""
    cfg = _load_config()
    return cfg.get("max_command_length", 500)


def get_model() -> str:
    """获取审查使用的模型名称。"""
    cfg = _load_config()
    return cfg.get("model", "deepseek-chat")


def _get_safety_prompt() -> str:
    """获取安全审查提示词。"""
    try:
        from config import PROJECT_ROOT
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("prompts", {}).get("ai_safety_prompt", "")
    except Exception:
        return ""


async def review_command(command: str, context: str = "") -> dict:
    """使用 AI 审查命令安全性。

    返回:
        {"verdict": "allow"/"deny"/"ask_user", "reason": "...", "risk_score": 0.0~1.0}
    """
    cfg = _load_config()

    # 超长命令直接拒绝
    max_len = cfg.get("max_command_length", 500)
    if len(command) > max_len:
        return {
            "verdict": "deny",
            "reason": f"命令长度 ({len(command)}) 超过限制 ({max_len})",
            "risk_score": 0.8,
        }

    prompt_template = _get_safety_prompt()
    if not prompt_template:
        logger.warning("ai_safety_prompt 未配置，跳过 AI 审查")
        return {"verdict": "allow", "reason": "AI 审查未配置", "risk_score": 0.0}

    # 构建审查请求
    review_context = f"命令: {command}"
    if context:
        review_context += f"\n上下文: {context}"
    prompt = prompt_template.replace("{context}", review_context)

    try:
        from llm import create_llm
        from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

        model = create_llm(LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)
        messages = [{"role": "user", "content": prompt}]
        resp = model.chat(messages)
        text = resp.content if hasattr(resp, "content") else str(resp)
        # 提取 JSON 部分
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            verdict = result.get("verdict", "ask_user")
            if verdict not in ("allow", "deny", "ask_user"):
                verdict = "ask_user"
            return {
                "verdict": verdict,
                "reason": result.get("reason", "AI 审查未返回理由"),
                "risk_score": float(result.get("risk_score", 0.5)),
            }
    except json.JSONDecodeError:
        logger.warning("AI 审查返回非 JSON 格式，降级为 ask_user")
    except ImportError:
        logger.warning("LLM 客户端不可用，跳过 AI 审查")
    except Exception as e:
        logger.warning("AI 审查异常，降级为 ask_user: %s", e)

    # 降级：无法判断时升级人工
    return {
        "verdict": "ask_user",
        "reason": "AI 审查未能完成判断，建议人工确认",
        "risk_score": 0.5,
    }
