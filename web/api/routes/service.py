import subprocess
import time
import locale
from pathlib import Path

from fastapi import APIRouter, HTTPException

from web.api.models.schemas import ServiceStatus

router = APIRouter(prefix="/api", tags=["service"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MAIN_PY = PROJECT_ROOT / "main.py"
SHUTDOWN_SIGNAL_FILE = PROJECT_ROOT / "workspace" / "data" / "shutdown_signal"

_process: subprocess.Popen | None = None
_start_time: float | None = None

_SYSTEM_ENCODING = locale.getpreferredencoding(False) or "utf-8"


def _find_main_process() -> int | None:
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             f"CommandLine like '%python%main.py%' and not CommandLine like '%wmic%'",
             "get", "ProcessId"],
            capture_output=True, text=True, timeout=10,
            encoding=_SYSTEM_ENCODING, errors="replace",
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                return int(line)
    except Exception:
        pass
    return None


def _force_kill(pid: int) -> bool:
    """强制终止进程并验证。"""
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=10,
                       encoding=_SYSTEM_ENCODING, errors="replace")
    except Exception:
        pass
    # 验证进程是否已退出
    time.sleep(0.5)
    return _is_pid_still_running(pid)


def _is_pid_still_running(pid: int) -> bool:
    """检查指定 PID 的进程是否仍在运行。"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "ProcessId"],
            capture_output=True, text=True, timeout=5,
            encoding=_SYSTEM_ENCODING, errors="replace",
        )
        return str(pid) in result.stdout
    except Exception:
        return True  # 无法确认，假设仍在运行


def _kill_main_process_graceful(pid: int) -> bool:
    """尝试优雅关闭，失败后强制终止，最终验证进程已退出。"""
    # 1. 先尝试信号文件（仅对支持的新版 main.py 有效）
    try:
        SHUTDOWN_SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        SHUTDOWN_SIGNAL_FILE.touch()
    except Exception:
        pass

    # 2. 等待进程自行退出（信号文件方式）
    for _ in range(10):
        if not _is_pid_still_running(pid):
            return True
        time.sleep(0.5)

    # 3. 强制终止（taskkill /F 是 Windows 上对控制台程序唯一可靠的方式）
    _force_kill(pid)

    # 4. 最终验证
    return not _is_pid_still_running(pid)


def _kill_main_process() -> bool:
    pid = _find_main_process()
    if pid is None:
        return True
    return _kill_main_process_graceful(pid)


def _request_graceful_stop(timeout: int = 10) -> bool:
    """通过信号文件请求 main.py 优雅关闭，等待进程退出。"""
    pid = _find_main_process()
    if pid is None:
        return True
    try:
        SHUTDOWN_SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        SHUTDOWN_SIGNAL_FILE.touch()
        # 等待进程退出
        for _ in range(timeout * 2):
            if not _is_pid_still_running(pid):
                return True
            time.sleep(0.5)
        return False
    except Exception:
        return False


@router.get("/status", response_model=ServiceStatus)
def get_status():
    global _process, _start_time

    if _process is not None and _process.poll() is None:
        uptime = time.time() - _start_time if _start_time else None
        return ServiceStatus(running=True, pid=_process.pid, uptime=uptime)

    pid = _find_main_process()
    if pid is not None:
        return ServiceStatus(running=True, pid=pid, uptime=None)

    return ServiceStatus(running=False, pid=None, uptime=None)


@router.post("/service/start")
def start_service():
    global _process, _start_time

    if _process is not None and _process.poll() is None:
        raise HTTPException(status_code=409, detail="Service is already running")

    pid = _find_main_process()
    if pid is not None:
        raise HTTPException(status_code=409, detail="Service is already running (external process)")

    try:
        _process = subprocess.Popen(
            ["python", str(MAIN_PY)],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            encoding=_SYSTEM_ENCODING, errors="replace",
        )
        _start_time = time.time()
        return {"status": "started", "pid": _process.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/service/stop")
def stop_service():
    global _process, _start_time

    # 如果有 Popen 对象，先尝试优雅关闭
    if _process is not None and _process.poll() is None:
        # 写信号文件让 main.py 优雅退出
        try:
            SHUTDOWN_SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
            SHUTDOWN_SIGNAL_FILE.touch()
        except Exception:
            pass
        try:
            _process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # 优雅关闭超时，强制终止
            try:
                _process.kill()
                _process.wait(timeout=5)
            except Exception:
                pass
        finally:
            _process = None
            _start_time = None
        return {"status": "stopped"}

    # 没有 Popen 对象（外部进程或上次 Web 面板遗留的进程）
    pid = _find_main_process()
    if pid is not None:
        if _kill_main_process_graceful(pid):
            _process = None
            _start_time = None
            return {"status": "stopped"}
        raise HTTPException(status_code=500, detail="Failed to stop external process")

    return {"status": "already_stopped"}


@router.post("/service/restart")
def restart_service():
    stop_service()
    time.sleep(1)
    return start_service()
