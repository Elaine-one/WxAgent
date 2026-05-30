import json
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Verdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK_USER = "ask_user"


@dataclass
class ReviewResult:
    verdict: Verdict
    reason: str
    risk_score: float


class AISafetyReviewer:
    PROMPT = """判断以下命令是否有恶意意图。只回复JSON。
{{"verdict":"allow"|"deny"|"ask_user","reason":"...","risk_score":0.0~1.0}}

判断依据:
- allow: 正常操作，无安全风险
- deny: 明确恶意（数据窃取、系统破坏、持久化后门）
- ask_user: 无法确定，升级人工判断

上下文: {context}"""

    def __init__(self, model, config: dict | None = None):
        self.model = model
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.review_levels = self.config.get("review_levels", ["caution"])
        self.max_length = self.config.get("max_command_length", 500)

    def should_review(self, risk_level: str) -> bool:
        if not self.enabled:
            return False
        return risk_level in self.review_levels

    def review(self, command: str, user_intent: str = "",
               risk_level: str = "") -> ReviewResult:
        if not self.should_review(risk_level):
            return ReviewResult(Verdict.ALLOW, "不在审查范围", 0.0)

        if len(command) > self.max_length:
            return ReviewResult(Verdict.ASK_USER, "命令过长，需人工确认", 0.5)

        context = f"用户意图: {user_intent}" if user_intent else "无"
        prompt = self.PROMPT.format(context=context)
        msg = f"{prompt}\n命令: {command}"

        try:
            resp = self.model.chat([{"role": "user", "content": msg}])
            text = resp.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            d = json.loads(text)
            return ReviewResult(
                Verdict(d.get("verdict", "ask_user")),
                d.get("reason", "解析失败"),
                float(d.get("risk_score", 0.8)),
            )
        except Exception as e:
            logger.warning("AI 审查结果解析失败: %s", e)
            return ReviewResult(Verdict.ASK_USER, "AI审查结果解析失败", 0.8)
