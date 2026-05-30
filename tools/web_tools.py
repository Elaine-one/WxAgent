import httpx
from bs4 import BeautifulSoup

from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

_cloud_consent_granted = False


def _check_cloud_consent(service_name: str) -> ToolResult | None:
    global _cloud_consent_granted
    if _cloud_consent_granted:
        return None
    return ToolResult(
        success=False,
        error=f"此操作会将查询内容发送到 {service_name}，是否继续？",
        requires_confirmation=True,
        confirmation_detail={
            "type": "cloud_consent",
            "message": f"此操作会将数据发送到云端服务 {service_name}，是否继续？后续同类操作不再提示。",
        },
    )


def _web_search(query: str, max_results: int = 5, state=None, user_id: str = "") -> ToolResult:
    global _cloud_consent_granted
    consent = _check_cloud_consent("DuckDuckGo 搜索引擎")
    if consent is not None:
        return consent
    _cloud_consent_granted = True
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        formatted = "\n".join(
            f"{i+1}. {r['title']}\n   {r['href']}\n   {r['body']}"
            for i, r in enumerate(results)
        )
        return ToolResult(
            success=True, content=formatted,
            display=f"搜索 '{query}' 完成，共 {len(results)} 条结果",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"搜索失败: {e}")


def _web_fetch(url: str, state=None, user_id: str = "") -> ToolResult:
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True,
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
            success=True, content=text[:8000],
            display=f"已获取 {url[:60]} ({len(text)} 字符)",
        )
    except Exception as e:
        return ToolResult(success=False, error=f"抓取失败: {e}")


ToolRegistry.register(
    ToolDef(
        name="web_search",
        description="使用 DuckDuckGo 搜索引擎搜索网页。首次使用需确认数据出境。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "最大结果数，默认5"},
        },
        required=["query"],
    ),
    _web_search,
)

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
