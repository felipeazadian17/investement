import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


@dataclass(frozen=True)
class MemoryRecord:
    key: str
    value: Mapping[str, Any]
    updated_at: str


class JsonMemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, value: Mapping[str, Any]) -> MemoryRecord:
        path = self._path(key)
        record = MemoryRecord(
            key=key,
            value=dict(value),
            updated_at=datetime.now(UTC).isoformat(),
        )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=key + ".", suffix=".tmp", dir=str(self.root)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(record.__dict__, handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return record

    def load(self, key: str) -> MemoryRecord | None:
        path = self._path(key)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return MemoryRecord(**json.load(handle))

    def list_keys(self) -> Sequence[str]:
        return tuple(sorted(path.stem for path in self.root.glob("*.json")))

    def _path(self, key: str) -> Path:
        if not _SAFE_KEY.fullmatch(key):
            raise ValueError("memory key contains unsupported characters")
        path = (self.root / (key + ".json")).resolve()
        if path.parent != self.root:
            raise ValueError("memory key escapes the store root")
        return path
