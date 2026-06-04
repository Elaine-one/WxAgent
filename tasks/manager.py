import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from enum import Enum

import config


class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    task_id: str
    task_type: str
    user_id: str
    status: TaskStatus
    params: dict
    result: str = ""
    error: str = ""
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    notify: str | None = None


class AsyncTaskManager:
    def __init__(self):
        self.io_pool = ThreadPoolExecutor(max_workers=config.ADV_IO_POOL_MAX_WORKERS)
        self.cpu_pool = ProcessPoolExecutor(max_workers=config.ADV_CPU_POOL_MAX_WORKERS)
        self._tasks: dict[str, TaskInfo] = {}
        self._futures: dict[str, Future] = {}
        self._on_complete_callback: Callable | None = None
        self._on_notify_callback: Callable | None = None
        self._lock = threading.Lock()

    def submit(self, task_type: str, params: dict, user_id: str,
               func: Callable, notify: str | None = None) -> str:
        task_id = f"task_{int(time.time())}_{len(self._tasks)}"
        info = TaskInfo(task_id=task_id, task_type=task_type,
                       user_id=user_id, status=TaskStatus.QUEUED, params=params,
                       notify=notify)
        with self._lock:
            self._tasks[task_id] = info

        pool = self.cpu_pool if task_type in ("transcode", "ocr") else self.io_pool
        future = pool.submit(self._run_task, task_id, func, params)
        with self._lock:
            self._futures[task_id] = future
        return task_id

    def _run_task(self, task_id: str, func: Callable, params: dict):
        with self._lock:
            self._tasks[task_id].status = TaskStatus.RUNNING
        try:
            result = func(**params)
            with self._lock:
                self._tasks[task_id].status = TaskStatus.COMPLETED
                self._tasks[task_id].result = str(result)
        except Exception as e:
            with self._lock:
                self._tasks[task_id].status = TaskStatus.FAILED
                self._tasks[task_id].error = str(e)
        if self._on_complete_callback:
            self._on_complete_callback(task_id)

        info = self._tasks.get(task_id)
        if info and info.notify and self._on_notify_callback:
            try:
                self._on_notify_callback(task_id, info.notify)
            except Exception:
                pass

    def query(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def list_running(self) -> list[TaskInfo]:
        with self._lock:
            return [t for t in self._tasks.values()
                    if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)]

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._futures and not self._futures[task_id].done():
                cancelled = self._futures[task_id].cancel()
                if cancelled:
                    self._tasks[task_id].status = TaskStatus.CANCELLED
                return cancelled
        return False

    def set_on_complete(self, callback: Callable):
        self._on_complete_callback = callback

    def set_on_notify(self, callback: Callable):
        self._on_notify_callback = callback


_task_manager: "AsyncTaskManager | None" = None
_task_manager_lock = threading.Lock()


def get_task_manager() -> "AsyncTaskManager":
    global _task_manager
    if _task_manager is None:
        with _task_manager_lock:
            if _task_manager is None:
                _task_manager = AsyncTaskManager()
    return _task_manager
