import logging
import subprocess
from pathlib import Path

from config import WORKSPACE_DIR
from tasks.manager import get_task_manager
from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


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
        check=True, capture_output=True, timeout=3600,
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
