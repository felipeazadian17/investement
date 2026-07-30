import re
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from investement.agents.models import AuditReceipt
from investement.orchestration import JsonlAuditLog, JsonMemoryStore

_SENSITIVE_KEY = re.compile(
    r"api.?key|secret|token|password|authorization|consumer.?key|client.?id|"
    r"credential|signature|cookie|account.?number",
    re.IGNORECASE,
)


class AuditorAgent:
    name = "auditor"

    def __init__(
        self,
        audit_log: JsonlAuditLog,
        memory: JsonMemoryStore | None = None,
    ) -> None:
        self._audit_log = audit_log
        self._memory = memory

    def record(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        memory_key: str | None = None,
    ) -> AuditReceipt:
        sanitized = _redact(payload)
        event = self._audit_log.append(run_id, event_type, sanitized)
        stored_key = None
        if memory_key is not None:
            if self._memory is None:
                raise RuntimeError("a memory store is required when memory_key is provided")
            self._memory.save(memory_key, sanitized)
            stored_key = memory_key
        return AuditReceipt(
            event_hash=event.event_hash,
            memory_key=stored_key,
            chain_valid=self._audit_log.verify(),
        )

    def verify(self) -> bool:
        return self._audit_log.verify()


def _redact(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list, set)):
        return [_redact(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return repr(value)
