from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from channel.client import SessionState
    from memory.manager import MemoryManager
    from tools.base import ToolDef


@dataclass
class Deps:
    model: object
    model_cache: dict = field(default_factory=dict)
    tools: list[ToolDef] = field(default_factory=list)
    memory: MemoryManager | None = None
    session: SessionState | None = None

    def real_session(self, config: dict | None = None) -> SessionState | None:
        return self.session
