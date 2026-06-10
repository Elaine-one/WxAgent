import re

import config

MAX_CHARS = config.ADV_MAX_CHARS


def split_for_wechat(text: str) -> list[str]:
    """将长文本按段落边界切分为微信消息段。

    LLM 已通过 prompt 指令输出微信友好格式（■ 标题、【】强调、• 列表等），
    此函数只需按 \\n\\n 段落边界切分即可。
    """
    if len(text) <= MAX_CHARS:
        return [text]

    # 按 \n\n 拆成段落
    paragraphs = re.split(r"(\n\n+)", text)
    # 合并分隔符回段落
    blocks = []
    i = 0
    while i < len(paragraphs):
        block = paragraphs[i]
        if i + 1 < len(paragraphs) and paragraphs[i + 1].strip() == "":
            block += paragraphs[i + 1]
            i += 2
        else:
            i += 1
        if block.strip():
            blocks.append(block.strip())

    # 合并段落为消息段（每段 ≤ MAX_CHARS）
    segments = []
    current = ""
    for block in blocks:
        if not current:
            current = block
        elif len(current) + len(block) + 1 <= MAX_CHARS:
            current = current + "\n\n" + block
        else:
            segments.append(current)
            current = block
    if current:
        segments.append(current)

    # 处理超长段落（单个段落 > MAX_CHARS）
    final = []
    for seg in segments:
        if len(seg) <= MAX_CHARS:
            final.append(seg)
        else:
            sub_parts = _split_long_paragraph(seg, MAX_CHARS)
            final.extend(sub_parts)

    return final


def _split_long_paragraph(text: str, max_chars: int) -> list[str]:
    """对超长段落按句末标点二次切分"""
    parts = []
    remaining = text
    while len(remaining) > max_chars:
        chunk = remaining[:max_chars]
        cut_pos = -1
        for i in range(len(chunk) - 1, max(len(chunk) * 3 // 5, 1), -1):
            if chunk[i] in "。！？；：\n":
                cut_pos = i + 1
                break
        if cut_pos > 0:
            parts.append(remaining[:cut_pos].strip())
            remaining = remaining[cut_pos:].strip()
        else:
            parts.append(chunk.strip())
            remaining = remaining[max_chars:].strip()
    if remaining:
        parts.append(remaining)
    return parts
