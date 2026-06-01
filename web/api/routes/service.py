import subprocess
import time
import locale
from pathlib import Path

from fastapi import APIRouter, HTTPException

from web.api.models.schemas import ServiceStatus

router = APIRouter(prefix="/api", tags=["service"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MAIN_PY = PROJECT_ROOT / "main.py"

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


def _kill_main_process() -> bool:
    pid = _find_main_process()
    if pid is None:
        return True
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=10,
                       encoding=_SYSTEM_ENCODING, errors="replace")
        return True
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

    if _process is not None and _process.poll() is None:
        try:
            _process.terminate()
            try:
                _process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _process.kill()
                _process.wait(timeout=5)
        except Exception:
            pass
        finally:
            _process = None
            _start_time = None
        return {"status": "stopped"}

    pid = _find_main_process()
    if pid is not None:
        if _kill_main_process():
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
