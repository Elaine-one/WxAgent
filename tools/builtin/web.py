import httpx
from bs4 import BeautifulSoup

import config
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry


TOOL_META = ToolMeta(
    name="web",
    type=ToolType.BUILTIN,
    description="Web工具集：网页抓取",
    version="1.0.0",
    tags=["web", "http"],
)


def _web_fetch(url: str, state=None, user_id: str = "") -> ToolResult:
    try:
        resp = httpx.get(url, timeout=config.ADV_WEB_FETCH_TIMEOUT, follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        try:
            from readability import Document as ReadabilityDoc
            doc = ReadabilityDoc(resp.text)
            text = doc.summary()
            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text("\n", strip=True)
        except Exception:
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)

        return ToolResult(
            success=True, content=text[:config.ADV_WEB_FETCH_MAX_CHARS],
            display=f"已获取 {url[:60]} ({len(text)} 字符)",
        )
    except httpx.TimeoutException as e:
        return ToolResult(success=False, error=f"抓取超时: {e}")
    except httpx.HTTPStatusError as e:
        return ToolResult(success=False, error=f"抓取失败 HTTP {e.response.status_code}: {e}")
    except httpx.RequestError as e:
        return ToolResult(success=False, error=f"抓取网络错误: {e}")


ToolRegistry.register(
    ToolDef(
        name="web_fetch",
        description="抓取指定 URL 的网页内容，自动提取正文文本。",
        parameters={
            "url": {"type": "string", "description": "要抓取的网页 URL"},
        },
        required=["url"],
    ),
    _web_fetch,
)
