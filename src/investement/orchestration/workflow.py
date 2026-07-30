from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from investement.orchestration.audit import JsonlAuditLog


@dataclass
class WorkflowContext:
    run_id: str
    as_of: datetime
    inputs: Mapping[str, Any]
    outputs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    handler: Callable[[WorkflowContext], Any]
    requires: Sequence[str] = ()
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("workflow step name and version are required")


@dataclass(frozen=True)
class WorkflowResult:
    run_id: str
    outputs: Mapping[str, Any]
    execution_order: Sequence[str]


class WorkflowEngine:
    def __init__(self, steps: Sequence[WorkflowStep], audit_log: JsonlAuditLog | None = None):
        if not steps:
            raise ValueError("workflow requires at least one step")
        names = [step.name for step in steps]
        if len(names) != len(set(names)):
            raise ValueError("workflow step names must be unique")
        unknown = {
            dependency for step in steps for dependency in step.requires if dependency not in names
        }
        if unknown:
            raise ValueError(f"unknown workflow dependencies: {', '.join(sorted(unknown))}")
        _validate_acyclic(steps)
        self._steps = tuple(steps)
        self._audit_log = audit_log

    def run(
        self,
        inputs: Mapping[str, Any],
        as_of: datetime | None = None,
        run_id: str | None = None,
    ) -> WorkflowResult:
        context = WorkflowContext(
            run_id=run_id or str(uuid4()),
            as_of=as_of or datetime.now(UTC),
            inputs=dict(inputs),
        )
        if context.as_of.tzinfo is None or context.as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        pending = {step.name: step for step in self._steps}
        order = []
        self._audit(
            "workflow.started",
            context,
            {
                "as_of": context.as_of,
                "input_keys": sorted(str(key) for key in context.inputs),
                "steps": [
                    {
                        "name": step.name,
                        "version": step.version,
                        "requires": tuple(step.requires),
                    }
                    for step in self._steps
                ],
            },
        )
        while pending:
            ready = [
                step
                for step in self._steps
                if step.name in pending and all(dep in context.outputs for dep in step.requires)
            ]
            if not ready:
                raise ValueError("workflow contains a dependency cycle")
            for step in ready:
                self._audit("step.started", context, {"step": step.name})
                try:
                    output = step.handler(context)
                except Exception as exc:
                    self._audit(
                        "step.failed",
                        context,
                        {"step": step.name, "error_type": type(exc).__name__, "error": str(exc)},
                    )
                    raise
                context.outputs[step.name] = output
                order.append(step.name)
                del pending[step.name]
                self._audit("step.completed", context, {"step": step.name, "output": output})
        self._audit("workflow.completed", context, {"execution_order": order})
        return WorkflowResult(
            run_id=context.run_id,
            outputs=dict(context.outputs),
            execution_order=tuple(order),
        )

    def _audit(
        self,
        event_type: str,
        context: WorkflowContext,
        payload: Mapping[str, Any],
    ) -> None:
        if self._audit_log is not None:
            self._audit_log.append(context.run_id, event_type, payload)


def _validate_acyclic(steps: Sequence[WorkflowStep]) -> None:
    dependencies = {step.name: set(step.requires) for step in steps}
    resolved: set[str] = set()
    while dependencies:
        ready = {name for name, requires in dependencies.items() if requires <= resolved}
        if not ready:
            raise ValueError("workflow contains a dependency cycle")
        resolved.update(ready)
        for name in ready:
            del dependencies[name]
