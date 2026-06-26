import logging
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import config
from config import WORKSPACE_DIR
from network.async_client import stream_sync
from tasks.manager import get_task_manager
from tools.base import ToolDef, ToolResult, ToolMeta, ToolType
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TOOL_META = ToolMeta(
    name="download",
    type=ToolType.BUILTIN,
    description="下载工具集：HTTP下载、视频下载、网页快照",
    version="1.0.0",
    tags=["download", "http", "video"],
)

_GITHUB_MIRRORS = config.ADV_GITHUB_MIRRORS


def _rewrite_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host in ("github.com", "www.github.com"):
        m = re.match(r"^/([^/]+)/([^/]+)(/.*)?$", parsed.path)
        if m:
            owner, repo, rest = m.group(1), m.group(2), m.group(3) or ""
            rest = rest.rstrip("/")
            if rest.startswith("/releases/download/"):
                for mirror in _GITHUB_MIRRORS:
                    return f"{mirror}/{url}", f"GitHub Release → 镜像加速下载"
            if rest and not rest.startswith("/archive/"):
                return url, f"GitHub 子路径，需用 web_fetch 查看页面内容"
            else:
                if not rest:
                    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
                else:
                    zip_url = url
                for mirror in _GITHUB_MIRRORS:
                    return f"{mirror}/{zip_url}", f"GitHub 仓库 → 镜像加速下载 ZIP"
                return zip_url, f"GitHub 仓库 → 下载 ZIP"

    if host in ("raw.githubusercontent.com",):
        for mirror in _GITHUB_MIRRORS:
            return f"{mirror}/{url}", f"GitHub Raw → 镜像加速"

    if host in ("objects.githubusercontent.com",):
        for mirror in _GITHUB_MIRRORS:
            return f"{mirror}/{url}", f"GitHub Release → 镜像加速"

    return url, ""


def _http_download(url: str, filename: str | None = None,
                   output_dir: str | None = None,
                   state=None, user_id: str = "") -> ToolResult:
    if output_dir is None:
        output_dir = str(WORKSPACE_DIR / "downloads")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    real_url, note = _rewrite_url(url)
    if note:
        logger.info("url_rewrite: %s → %s (%s)", url[:80], real_url[:80], note)

    if not filename:
        parsed = urlparse(real_url)
        name = Path(parsed.path).name
        if name and "." in name and len(name) < 200:
            filename = name
        else:
            parsed_orig = urlparse(url)
            name_orig = Path(parsed_orig.path).name
            filename = name_orig if name_orig and "." in name_orig else "download"

    save_path = str(Path(output_dir) / filename)
    try:
        with stream_sync("GET", real_url, timeout=config.ADV_HTTP_DOWNLOAD_TIMEOUT,
                         follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"}) as resp:
            resp.raise_for_status()
            cd = resp.headers.get("content-disposition", "")
            if cd and "filename=" in cd and filename == "download":
                m = re.search(r'filename[*]?=["\']?([^"\';\n]+)', cd)
                if m:
                    real_name = m.group(1).strip()
                    if real_name:
                        save_path = str(Path(output_dir) / real_name)
            ct = resp.headers.get("content-type", "")
            if "text/html" in ct and not url.endswith((".html", ".htm")):
                Path(save_path).unlink(missing_ok=True)
                return ToolResult(
                    success=False,
                    error=f"该 URL 返回的是网页而非文件。如需查看网页内容请用 web_fetch，如需保存网页请用 webpage_snapshot。",
                )
            with open(save_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        size = Path(save_path).stat().st_size
        logger.info("http_download_ok: url=%s path=%s size=%s", url[:100], save_path, size)
        msg = f"下载完成: {save_path} ({size:,} bytes)"
        if note:
            msg += f"\n({note})"
        return ToolResult(
            success=True,
            content=msg,
            display=f"已下载 {filename} ({size:,} bytes)",
            artifact_path=save_path,
        )
    except Exception as e:
        logger.warning("http_download_fail: url=%s error=%s", url[:100], e)
        return ToolResult(success=False, error=f"下载失败: {e}")


def _download_video(url: str, output_dir: str | None = None,
                    state=None, user_id: str = "") -> ToolResult:
    if output_dir is None:
        output_dir = str(WORKSPACE_DIR / "downloads")

    tm = get_task_manager()
    task_id = tm.submit(
        "video_download", {"url": url, "output_dir": output_dir},
        user_id, _do_download,
    )
    return ToolResult(
        success=True,
        content=f"下载任务已开始（ID: {task_id}），完成后通知你。",
        display="开始下载，完成后通知你",
    )


def _do_download(url: str, output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["yt-dlp", "-o", f"{output_dir}/%(title)s.%(ext)s",
         "--no-playlist", url],
        check=True, capture_output=True, timeout=config.ADV_VIDEO_DOWNLOAD_TIMEOUT,
    )
    return "下载完成"


def _webpage_snapshot(url: str, output_dir: str | None = None,
                      state=None, user_id: str = "") -> ToolResult:
    if output_dir is None:
        output_dir = str(WORKSPACE_DIR / "downloads")

    tm = get_task_manager()
    task_id = tm.submit(
        "webpage_snapshot", {"url": url, "output_dir": output_dir},
        user_id, _do_snapshot,
    )
    return ToolResult(
        success=True,
        content=f"快照任务已开始（ID: {task_id}），完成后通知你。",
        display="正在生成网页快照",
    )


def _do_snapshot(url: str, output_dir: str) -> str:
    from playwright.sync_api import sync_playwright
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        title = page.title() or "snapshot"
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:50]
        output_path = f"{output_dir}/{safe_title}.pdf"
        page.pdf(path=output_path)
        browser.close()
    return output_path


ToolRegistry.register(
    ToolDef(
        name="download_video",
        description="使用 yt-dlp 下载视频。异步执行，完成后微信通知。支持 B站/YouTube 等主流平台。",
        parameters={
            "url": {"type": "string", "description": "视频 URL"},
            "output_dir": {"type": "string", "description": "输出目录，默认 workspace/downloads"},
        },
        required=["url"],
    ),
    _download_video,
)

ToolRegistry.register(
    ToolDef(
        name="webpage_snapshot",
        description="将网页渲染保存为 PDF 快照。异步执行，完成后通知。",
        parameters={
            "url": {"type": "string", "description": "网页 URL"},
            "output_dir": {"type": "string", "description": "输出目录，默认 workspace/downloads"},
        },
        required=["url"],
    ),
    _webpage_snapshot,
)

ToolRegistry.register(
    ToolDef(
        name="http_download",
        description="下载 HTTP/HTTPS 文件到本地。自动识别 GitHub 仓库 URL 并通过镜像加速下载 ZIP。禁止用 curl/wget 下载，必须用此工具。",
        parameters={
            "url": {"type": "string", "description": "下载链接（HTTP/HTTPS）。GitHub 仓库链接会自动转为 ZIP 下载"},
            "filename": {"type": "string", "description": "保存文件名（可选，默认从 URL 提取）"},
            "output_dir": {"type": "string", "description": "保存目录（可选，默认 workspace/downloads）"},
        },
        required=["url"],
    ),
    _http_download,
)
