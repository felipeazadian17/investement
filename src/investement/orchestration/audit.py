import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    run_id: str
    event_type: str
    timestamp: str
    payload: Mapping[str, Any]
    previous_hash: str | None
    event_hash: str


class JsonlAuditLog:
    """Append-only JSONL log with a tamper-evident SHA-256 hash chain."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, run_id: str, event_type: str, payload: Mapping[str, Any]) -> AuditEvent:
        if not run_id.strip() or not event_type.strip():
            raise ValueError("run_id and event_type are required")
        with self._lock:
            previous_hash = self._last_hash()
            body = {
                "event_id": str(uuid4()),
                "run_id": run_id,
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": _json_safe(payload),
                "previous_hash": previous_hash,
            }
            event_hash = _hash(body)
            event = AuditEvent(event_hash=event_hash, **body)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), sort_keys=True, separators=(",", ":")))
                handle.write("\n")
                handle.flush()
            return event

    def read(self) -> Sequence[AuditEvent]:
        if not self.path.exists():
            return ()
        events = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    events.append(AuditEvent(**json.loads(line)))
        return tuple(events)

    def verify(self) -> bool:
        previous_hash = None
        for event in self.read():
            body = {
                "event_id": event.event_id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "timestamp": event.timestamp,
                "payload": event.payload,
                "previous_hash": event.previous_hash,
            }
            if event.previous_hash != previous_hash or event.event_hash != _hash(body):
                return False
            previous_hash = event.event_hash
        return True

    def _last_hash(self) -> str | None:
        events = self.read()
        return events[-1].event_hash if events else None


def _hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    return repr(value)
