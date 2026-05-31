import logging
import subprocess
from pathlib import Path

from config import WORKSPACE_DIR
from tasks.manager import get_task_manager
from tools.base import ToolDef, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _silk_to_wav(silk_path: str) -> str | None:
    wav_path = silk_path.rsplit(".", 1)[0] + ".wav"
    try:
        import pilk
        pilk.decode(silk_path, wav_path)
        if Path(wav_path).is_file():
            return wav_path
    except ImportError:
        pass
    except Exception as e:
        logger.debug("pilk decode failed: %s", e)

    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", silk_path, "-acodec", "pcm_s16le",
             "-ar", "24000", "-ac", "1", wav_path],
            capture_output=True, timeout=30,
        )
        if Path(wav_path).is_file():
            return wav_path
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("ffmpeg silk decode failed: %s", e)

    return None


def _transcribe_audio(file_path: str, language: str = "zh",
                      state=None, user_id: str = "") -> ToolResult:
    if not Path(file_path).is_file():
        return ToolResult(success=False, error=f"文件不存在: {file_path}")

    actual_path = file_path
    if file_path.lower().endswith(".silk"):
        wav_path = _silk_to_wav(file_path)
        if wav_path:
            actual_path = wav_path
            logger.info("silk_to_wav: %s -> %s", file_path, wav_path)
        else:
            return ToolResult(success=False, error="SILK 格式转换失败：需要安装 pilk (pip install pilk) 或 ffmpeg")

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(actual_path, language=language)
        text = " ".join(s.text for s in segments)
        return ToolResult(
            success=True, content=text,
            display=f"转录完成，{len(text)} 字",
        )
    except ImportError:
        logger.info("faster_whisper 不可用，降级到云端 API")
        return _transcribe_via_api(actual_path, language)
    except Exception as e:
        return ToolResult(success=False, error=f"转录失败: {e}")


def _transcribe_via_api(file_path: str, language: str) -> ToolResult:
    from llm import create_llm
    from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL
    try:
        llm = create_llm(LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, "whisper-1")
        with open(file_path, "rb") as f:
            result = llm.transcribe(f, language=language)
        return ToolResult(success=True, content=result.text)
    except Exception as e:
        return ToolResult(success=False, error=f"云端转录失败: {e}")


def _video_add_subtitles(video_path: str, target_language: str = "zh",
                         state=None, user_id: str = "") -> ToolResult:
    if not Path(video_path).is_file():
        return ToolResult(success=False, error=f"文件不存在: {video_path}")

    tm = get_task_manager()
    task_id = tm.submit(
        "video_subtitle",
        {"video_path": video_path, "target_language": target_language},
        user_id,
        _do_subtitle_task,
    )
    return ToolResult(
        success=True,
        content=f"字幕任务已启动（ID: {task_id}），完成后会通知你。",
        display="字幕生成中，完成后通知你",
    )


def _do_subtitle_task(video_path: str, target_language: str = "zh") -> str:
    output_dir = str(WORKSPACE_DIR / "output")
    audio_path = f"{output_dir}/audio_temp.wav"

    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", audio_path],
        capture_output=True, timeout=300,
    )

    result = _transcribe_audio(audio_path)
    if not result.success:
        raise RuntimeError(f"转录失败: {result.error}")

    Path(audio_path).unlink(missing_ok=True)
    return result.content


def _ocr_image(image_path: str, output_format: str = "text",
               state=None, user_id: str = "") -> ToolResult:
    if not Path(image_path).is_file():
        return ToolResult(success=False, error=f"文件不存在: {image_path}")

    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang="ch")
        result = ocr.ocr(image_path, cls=True)
        if output_format == "xlsx":
            output_path = str(WORKSPACE_DIR / "output" / "ocr_result.xlsx")
            _ocr_table_to_xlsx(result, output_path)
            return ToolResult(
                success=True, content="表格已生成",
                artifact_path=output_path,
            )
        text = "\n".join(
            line[1][0] for line in result[0] if line[1]
        ) if result and result[0] else ""
        return ToolResult(success=True, content=text)
    except ImportError:
        logger.info("PaddleOCR 不可用，降级到云端 Vision API")
        return _ocr_via_vision_api(image_path, output_format)
    except Exception as e:
        return ToolResult(success=False, error=f"OCR 失败: {e}")


def _ocr_via_vision_api(image_path: str, output_format: str) -> ToolResult:
    from llm import create_llm
    from config import LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL
    try:
        llm = create_llm(LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, "gpt-4o")
        with open(image_path, "rb") as f:
            import base64
            img_b64 = base64.b64encode(f.read()).decode()
        prompt = "请识别图片中的所有文字" + (
            "，并还原表格结构" if output_format == "xlsx" else ""
        )
        resp = llm.chat([{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ],
        }])
        return ToolResult(success=True, content=resp.text)
    except Exception as e:
        return ToolResult(success=False, error=f"云端 OCR 失败: {e}")


def _ocr_table_to_xlsx(ocr_result, output_path: str):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for row_idx, line in enumerate(ocr_result[0] if ocr_result else [], 1):
        text = line[1][0] if line[1] else ""
        for col_idx, cell_text in enumerate(text.split("\t"), 1):
            ws.cell(row=row_idx, column=col_idx, value=cell_text)
    wb.save(output_path)


ToolRegistry.register(
    ToolDef(
        name="transcribe_audio",
        description="将音频文件转录为文字。本地 Whisper 优先，不可用时降级云端 API。",
        parameters={
            "file_path": {"type": "string", "description": "音频文件路径"},
            "language": {"type": "string", "description": "语言代码，如 zh/en，默认 zh"},
        },
        required=["file_path"],
    ),
    _transcribe_audio,
)

ToolRegistry.register(
    ToolDef(
        name="video_add_subtitles",
        description="为视频自动生成字幕。提取音轨→转录→压制字幕。异步执行，完成后通知。",
        parameters={
            "video_path": {"type": "string", "description": "视频文件路径"},
            "target_language": {"type": "string", "description": "目标字幕语言，默认 zh"},
        },
        required=["video_path"],
    ),
    _video_add_subtitles,
)

ToolRegistry.register(
    ToolDef(
        name="ocr_image",
        description="OCR 识别图片文字/表格。output_format=text 返回文字，output_format=xlsx 生成 Excel。本地 PaddleOCR 优先，降级云端。",
        parameters={
            "image_path": {"type": "string", "description": "图片文件路径"},
            "output_format": {"type": "string", "description": "输出格式: text / xlsx"},
        },
        required=["image_path"],
    ),
    _ocr_image,
)
