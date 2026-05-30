import re
from enum import Enum

import yaml


class RiskLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"


DANGEROUS_PATTERNS = [
    re.compile(r'(&&|\|)\s*(rm|del|format|shutdown|taskkill|reg)\b', re.I),
    re.compile(r';\s*(rm|del|format|shutdown|taskkill|reg)\b', re.I),
    re.compile(r'\b(rm|del)\s+(-[rf]|/s|/q)', re.I),
    re.compile(r'(curl|wget)\s+.*\|\s*(bash|sh|python|powershell)', re.I),
    re.compile(r'(base64|encodedcommand|frombase64string)', re.I),
    re.compile(r'(>.*\.(bat|cmd|ps1|vbs|js))', re.I),
    re.compile(r'%[A-Za-z_][A-Za-z0-9_]*%', re.I),
    re.compile(r'powershell\s+-(e[nc]|enc?o?d?e?d?c?o?m?m?a?n?d?)\b', re.I),
]

SAFE_COMMANDS = re.compile(
    r'^(dir|ls|type|cat|echo|where|which|python\s+--version|'
    r'git\s+status|git\s+log|git\s+diff|git\s+branch|'
    r'netstat|systeminfo|tasklist|whoami|hostname|ipconfig|ping)\b', re.I)

CAUTION_COMMANDS = re.compile(
    r'^(pip\s+install|pip\s+uninstall|git\s+push|git\s+fetch|git\s+pull|'
    r'git\s+add|git\s+commit|npm\s+install|'
    r'python\s+-m\s+http\.server|python\s+-c)\b', re.I)

DANGEROUS_COMMANDS = re.compile(
    r'^(del|rm|rd|rmdir|taskkill|kill|shutdown|restart|reg|'
    r'format|fdisk|chkdsk|sfc|bcdedit|net\s+user|'
    r'wmic|schtasks|mshta|'
    r'powershell\s+-enc|cmd\s+/c|cmd\s+/k|certutil|bitsadmin)\b', re.I)

PYTHON_C_DANGEROUS = re.compile(
    r'python\s+-c\s+.*(?:'
    r'os\.system|os\.popen|os\.remove|os\.rmdir|os\.unlink|os\.kill|'
    r'subprocess\.(run|call|Popen)|'
    r'__import__|shutil\.rmtree|'
    r'open\s*\(.*[\'"]w[\'"]'
    r')', re.I | re.DOTALL)


def is_dev_mode() -> bool:
    try:
        from config import PROJECT_ROOT
        with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("security", {}).get("dev_mode", False)
    except Exception:
        return False


def classify_command(command: str) -> tuple[RiskLevel, str]:
    stripped = command.strip()
    for p in DANGEROUS_PATTERNS:
        if p.search(stripped):
            return RiskLevel.DANGEROUS, "检测到危险模式"
    if PYTHON_C_DANGEROUS.search(stripped):
        return RiskLevel.DANGEROUS, "python -c 包含危险调用"
    if DANGEROUS_COMMANDS.match(stripped):
        return RiskLevel.DANGEROUS, "高风险命令"
    if CAUTION_COMMANDS.match(stripped):
        return RiskLevel.CAUTION, "需注意的命令"
    if SAFE_COMMANDS.match(stripped):
        return RiskLevel.SAFE, "只读命令"
    return RiskLevel.DANGEROUS, "未知命令，默认按危险处理"
