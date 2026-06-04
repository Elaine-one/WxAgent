import logging
import threading
import time
from pathlib import Path

import yaml

import config
from config import PROJECT_ROOT, WORKSPACE_DIR
from memory.embedding import get_embedding_fn

_embedding_fn = None  # deprecated: use get_embedding_fn() instead


def _get_embedding_fn():
    return get_embedding_fn()

logger = logging.getLogger(__name__)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_pdf(path: Path) -> str:
    try:
        from parsers.pdf import read_pdf
        return read_pdf(str(path))
    except Exception:
        return _read_text(path)


def _read_docx(path: Path) -> str:
    try:
        from parsers.word import read_docx
        return read_docx(str(path))
    except Exception:
        return _read_text(path)


_PARSER_REGISTRY: dict[str, callable] = {
    ".pdf": _read_pdf,
    ".docx": _read_docx,
    ".pptx": _read_docx,
    ".xlsx": _read_text,
    ".txt": _read_text,
    ".md": _read_text,
    ".py": _read_text,
    ".js": _read_text,
    ".csv": _read_text,
}


class BackgroundIndexer:
    def __init__(self, db_path: str | None = None):
        cfg = self._load_config()
        self.watch_dirs = [Path(p).expanduser() for p in cfg.get("watch_dirs", [])]
        self.supported_types = set(cfg.get("supported_types", []))
        self.idle_cpu_pct = cfg.get("idle_cpu_threshold", 20)
        self.scan_interval = cfg.get("scan_interval_seconds", 300)
        self.max_chars = cfg.get("max_document_chars", 8000)
        self.use_watchdog = cfg.get("use_watchdog", True)

        self._stop = threading.Event()
        self._indexed: dict[str, float] = {}
        self.stats = {"files_indexed": 0, "errors": 0}

        self._client = None
        self._db_path = db_path

    def _load_config(self) -> dict:
        try:
            with open(PROJECT_ROOT / "config.yaml", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg.get("indexer", {})
        except Exception:
            return {}

    def _get_client(self):
        if self._client is None:
            import chromadb
            from chromadb.config import Settings
            path = self._db_path or str(WORKSPACE_DIR / "data" / "chroma")
            self._client = chromadb.PersistentClient(
                path=path, settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    def start(self):
        if self.use_watchdog:
            self._start_watchdog()
        self._thread = threading.Thread(target=self._polling_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _start_watchdog(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class Handler(FileSystemEventHandler):
                def __init__(self, indexer):
                    self.indexer = indexer

                def on_modified(self, event):
                    if not event.is_directory:
                        self.indexer._index_file(Path(event.src_path))

                def on_created(self, event):
                    if not event.is_directory:
                        self.indexer._index_file(Path(event.src_path))

            self._observer = Observer()
            handler = Handler(self)
            for d in self.watch_dirs:
                if d.exists():
                    self._observer.schedule(handler, str(d), recursive=True)
            self._observer.start()
            logger.info("watchdog 索引器已启动，监控 %d 个目录", len(self.watch_dirs))
        except ImportError:
            logger.warning("watchdog 未安装，回退到轮询模式")
            self.use_watchdog = False

    def _polling_loop(self):
        self._stop.wait(self.scan_interval)
        while not self._stop.is_set():
            self._scan_all()
            self._stop.wait(self.scan_interval)

    def _scan_all(self):
        col = self._get_client().get_or_create_collection("file_index", embedding_function=_get_embedding_fn())
        for root in self.watch_dirs:
            if not root.exists():
                continue
            for fp in root.rglob("*"):
                if self._stop.is_set():
                    return
                self._index_file(fp, col)

    def _index_file(self, fp: Path, col=None):
        if not fp.is_file() or fp.suffix.lower() not in self.supported_types:
            return
        key = str(fp)
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            return
        if self._indexed.get(key, 0) >= mtime:
            return

        text = self._extract(fp)
        if not text:
            return

        if col is None:
            col = self._get_client().get_or_create_collection("file_index", embedding_function=_get_embedding_fn())

        col.upsert(
            ids=[key],
            documents=[text[:self.max_chars]],
            metadatas=[{"path": key, "name": fp.name, "suffix": fp.suffix}],
        )
        self._indexed[key] = mtime
        self.stats["files_indexed"] += 1

    def _extract(self, path: Path) -> str:
        return _PARSER_REGISTRY.get(path.suffix.lower(), _read_text)(path)
