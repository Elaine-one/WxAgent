from pathlib import Path

from config import PROJECT_ROOT, WORKSPACE_DIR


class PathSandbox:

    READ_ROOTS = [
        PROJECT_ROOT,
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
    ]

    WRITE_ROOTS = [
        WORKSPACE_DIR,
        WORKSPACE_DIR / "output",
        WORKSPACE_DIR / "temp",
        WORKSPACE_DIR / "scripts",
        WORKSPACE_DIR / "downloads",
    ]

    DENIED = [
        ".ssh", ".gnupg", ".env",
        "AppData/Roaming/Microsoft",
        "NTUSER.DAT",
    ]

    @classmethod
    def validate_write(cls, path: str) -> Path:
        resolved = Path(path).resolve()
        for denied in cls.DENIED:
            if denied.lower() in str(resolved).lower():
                raise PermissionError(f"路径触及保护区域: {denied}")
        if any(str(resolved).startswith(str(d)) for d in cls.WRITE_ROOTS):
            return resolved
        raise PermissionError(
            f"不允许写入: {path}\n所有写操作限制在 {WORKSPACE_DIR} 目录内。"
        )

    @classmethod
    def validate_read(cls, path: str) -> Path:
        resolved = Path(path).resolve()
        if any(str(resolved).startswith(str(d)) for d in cls.READ_ROOTS + cls.WRITE_ROOTS):
            return resolved
        raise PermissionError(f"不允许读取: {path}")
