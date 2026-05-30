import json
import os
from datetime import datetime
from pathlib import Path

from config import WORKSPACE_DIR


class DebugDumper:
    def __init__(self):
        self.enabled = os.getenv("WXAGENT_DEBUG", "0") == "1"
        self.dump_dir = WORKSPACE_DIR / "data" / "debug"

    def dump_state(self, node_name: str, state: dict):
        if not self.enabled:
            return
        self.dump_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S_%f")
        filename = f"{ts}_{node_name}.json"
        filepath = self.dump_dir / filename
        try:
            serializable = {}
            for k, v in state.items():
                try:
                    json.dumps(v)
                    serializable[k] = v
                except (TypeError, ValueError):
                    serializable[k] = str(v)
            filepath.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


debug_dumper = DebugDumper()
