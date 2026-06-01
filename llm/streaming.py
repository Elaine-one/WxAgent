import re

import config

MAX_CHARS = config.ADV_MAX_CHARS
SPLIT_RE = re.compile(r'([。！？\n]|\.{3,}|——)')


def split_for_wechat(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts = []
    remaining = text
    while len(remaining) > MAX_CHARS:
        chunk = remaining[:MAX_CHARS]
        matches = list(SPLIT_RE.finditer(chunk))
        if matches:
            cut = matches[-1].end()
            if cut > MAX_CHARS * 0.6:
                parts.append(remaining[:cut].strip())
                remaining = remaining[cut:].strip()
                continue
        parts.append(chunk.strip())
        remaining = remaining[MAX_CHARS:].strip()
    if remaining:
        parts.append(remaining)
    return parts
