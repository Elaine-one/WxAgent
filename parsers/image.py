def ocr_image(path: str, profile: str = "basic") -> str:
    if profile == "basic":
        return _ocr_basic(path)
    return _ocr_full(path)


def _ocr_basic(path: str) -> str:
    try:
        import base64
        import httpx
        from pathlib import Path
        from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

        img_data = Path(path).read_bytes()
        b64 = base64.b64encode(img_data).decode()

        resp = httpx.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请识别并提取图片中的所有文字内容，保持原始格式。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }],
                "max_tokens": 2000,
            },
            timeout=30,
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"OCR 识别失败: {e}"


def _ocr_full(path: str) -> str:
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        result = ocr.ocr(path, cls=True)
        lines = [line[1][0] for line in result[0]] if result and result[0] else []
        return "\n".join(lines)
    except Exception as e:
        return f"PaddleOCR 识别失败: {e}"
