#!/usr/bin/env python3
"""Root-owned, dependency-free run-state recorder.

The command is intentionally a validation substrate rather than a scheduler.
It never starts processes, dispatches agents, infers workflow progress, or
modifies anything outside the explicit project root/run directory.

CLI contract::

    python scripts/run_state.py create --project-root PROJECT [--run-id ID]
    python scripts/run_state.py show --project-root PROJECT --run-id ID
    python scripts/run_state.py transition --project-root PROJECT --run-id ID \
        --to STATUS --reason REASON
    python scripts/run_state.py record-route --project-root PROJECT --run-id ID \
        --route ROUTE.json
    python scripts/run_state.py record-report --project-root PROJECT --run-id ID \
        --report REPORT.json
    python scripts/run_state.py reconcile --project-root PROJECT --run-id ID \
        --task-id TASK_ID [--report-id REPORT_ID] --decision DECISION --reason REASON
    python scripts/run_state.py set-acceptance --project-root PROJECT --run-id ID \
        (--criteria TEXT ... | --criteria-file CRITERIA.json) --satisfied true|false
    python scripts/run_state.py verify --project-root PROJECT --run-id ID \
        [--integrated-at TIMESTAMP] [--blocking-finding TEXT ...]
    python scripts/run_state.py complete --project-root PROJECT --run-id ID

All successful commands emit the canonical state JSON to stdout. Diagnostics
are written to stderr. Exit code 2 denotes invalid input, path, record, or
state; exit code 3 denotes an invalid transition or an unmet predicate.

An agent report can be recorded only after a route exists and its task ID and
role match one concrete route task instance.  Routes must name ``root`` as
workflow owner.  These consistency checks are deliberately explicit: the
recorder never infers a task result or acceptance from a report. Every report
requires an explicit root-owned reconciliation decision before completion;
only ``ACCEPT`` is completion-eligible. ``BLOCKED`` and ``NEEDS_CONTEXT`` are
never successful completion results.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from orchestrator_lib import artifact_identity, artifact_path, atomic_write_json, load_json, utc_now, validate_instance


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
STAT_REPARSE_POINT = 0x400

STATUSES = (
    "created",
    "routing",
    "awaiting-approval",
    "investigating",
    "planning",
    "implementing",
    "reviewing",
    "repairing",
    "verifying",
    "partial",
    "blocked",
    "failed",
    "completed",
)

# The table is deliberately explicit.  ``completed`` is absent from every
# ordinary edge because only ``complete`` may satisfy the final predicate.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"routing", "blocked", "failed"}),
    "routing": frozenset({"awaiting-approval", "investigating", "planning", "blocked", "failed"}),
    "awaiting-approval": frozenset({"investigating", "planning", "blocked", "failed"}),
    "investigating": frozenset({"planning", "implementing", "reviewing", "verifying", "partial", "blocked", "failed"}),
    "planning": frozenset({"implementing", "reviewing", "blocked", "failed"}),
    "implementing": frozenset({"investigating", "reviewing", "repairing", "verifying", "partial", "blocked", "failed"}),
    "reviewing": frozenset({"investigating", "repairing", "verifying", "partial", "blocked", "failed"}),
    "repairing": frozenset({"investigating", "implementing", "reviewing", "verifying", "partial", "blocked", "failed"}),
    "verifying": frozenset({"reviewing", "repairing", "partial", "blocked", "failed"}),
    "partial": frozenset({"implementing", "reviewing", "repairing", "verifying", "blocked", "failed"}),
    "blocked": frozenset(),
    "failed": frozenset(),
    "completed": frozenset(),
}
TERMINAL_STATUSES = frozenset({"blocked", "failed", "completed"})
COMPLETION_ELIGIBLE_STATUSES = frozenset({"verifying"})
RECONCILIATION_DECISIONS = frozenset({"ACCEPT", "REPAIR", "INVESTIGATE", "REPLAN", "BLOCK"})
WINDOWS_RESERVED_RUN_BASES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}
)


class RunStateError(Exception):
    """Base error carrying the stable CLI exit code."""

    exit_code = 2


class InputError(RunStateError):
    """Invalid command input, path, embedded record, or state."""


class StateError(InputError):
    """Malformed or tampered persisted state."""


class Refusal(RunStateError):
    """A valid command cannot be applied to the current lifecycle state."""

    exit_code = 3


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise InputError(f"cannot inspect path {path}: {exc}") from exc
    return path.is_symlink() or bool(getattr(stat_result, "st_file_attributes", 0) & STAT_REPARSE_POINT)


def _resolve_project_root(value: str | os.PathLike[str]) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise InputError("--project-root must be a non-empty explicit directory")
    try:
        root = Path(value).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise InputError(f"project root cannot be resolved: {value}") from exc
    if not root.is_dir():
        raise InputError(f"project root is not a directory: {value}")
    return root


def _validate_run_id(value: str) -> str:
    if not isinstance(value, str) or not value or not RUN_ID_PATTERN.fullmatch(value):
        raise InputError("run ID must be a single safe name matching ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise InputError("run ID cannot contain control characters")
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise InputError("run ID must be a direct child name")
    if value.endswith("."):
        raise InputError("run ID cannot end with a dot")
    windows_base = value.split(".", 1)[0].upper()
    if windows_base in WINDOWS_RESERVED_RUN_BASES:
        raise InputError("run ID cannot use a Windows reserved device name")
    return value


def _directory(parent: Path, name: str, *, create: bool) -> Path:
    child = parent / name
    exists = child.exists() or child.is_symlink()
    if not exists:
        if not create:
            raise InputError(f"required state directory is missing: {child}")
        try:
            child.mkdir()
        except FileExistsError:
            pass
    if _is_reparse_or_symlink(child):
        raise InputError(f"symlink/reparse state boundary is not allowed: {child}")
    if not child.is_dir():
        raise InputError(f"state boundary is not a directory: {child}")
    return child


def _state_path(project_root: Path, run_id: str, *, create: bool) -> Path:
    root = _resolve_project_root(project_root)
    safe_id = _validate_run_id(run_id)
    codex = _directory(root, ".codex", create=create)
    orchestrator = _directory(codex, "orchestrator", create=create)
    runs = _directory(orchestrator, "runs", create=create)
    run_dir = runs / safe_id
    if create:
        if run_dir.exists() or run_dir.is_symlink():
            raise InputError(f"run directory already exists: {run_dir}")
        try:
            run_dir.mkdir()
        except FileExistsError as exc:
            raise InputError(f"run directory already exists: {run_dir}") from exc
    elif not run_dir.exists() and not run_dir.is_symlink():
        raise InputError(f"run does not exist: {safe_id}")
    if _is_reparse_or_symlink(run_dir):
        raise InputError(f"symlink/reparse run boundary is not allowed: {run_dir}")
    if not run_dir.is_dir():
        raise InputError(f"run boundary is not a directory: {run_dir}")
    target = run_dir / "state.json"
    if target.exists() or target.is_symlink():
        if _is_reparse_or_symlink(target):
            raise InputError(f"symlink/reparse state file is not allowed: {target}")
        if not target.is_file():
            raise InputError(f"state path is not a regular file: {target}")
    elif not create:
        raise InputError(f"state file does not exist: {target}")
    return target


def _load_schema(filename: str) -> dict[str, Any]:
    try:
        return load_json(PACKAGE_ROOT / "schemas" / filename)
    except ValueError as exc:
        raise StateError(f"cannot load bundled schema {filename}: {exc}") from exc


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP_PATTERN.fullmatch(value):
        raise StateError(f"{label} must be an ISO-8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise StateError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _dispatch_instances(
    route: Mapping[str, Any], *, error_type: type[RunStateError] = InputError
) -> dict[str, dict[str, Any]]:
    """Return concrete dispatch instances after validating wave semantics.

    ``selected_roles`` remains a unique role decision set.  ``task_instances``
    is the dispatch identity set, so multiple instances may intentionally have
    the same role.  Waves retain ``roles`` for compatibility while
    ``task_ids`` is the authoritative instance identity in each position.
    """
    selected = route.get("selected_roles", [])
    selected_names = [entry["role"] for entry in selected]
    instances = route.get("task_instances", [])
    instance_by_id: dict[str, dict[str, Any]] = {}
    for index, instance in enumerate(instances):
        task_id = instance["task_id"]
        if task_id in instance_by_id:
            raise error_type(f"route task_instances[{index}].task_id is duplicated: {task_id}")
        if instance["role"] not in selected_names:
            raise error_type(
                f"route task_instances[{index}].role {instance['role']!r} is not selected"
            )
        instance_by_id[task_id] = instance

    waves = route.get("parallel_waves", [])
    wave_roles: list[str] = []
    dispatched_ids: list[str] = []
    wave_ids: set[int] = set()
    for index, wave in enumerate(waves):
        wave_id = wave["id"]
        if wave_id in wave_ids:
            raise error_type(f"route parallel_waves[{index}].id is duplicated")
        wave_ids.add(wave_id)
        roles = wave["roles"]
        task_ids = wave["task_ids"]
        if len(roles) != len(task_ids):
            raise error_type(
                f"route parallel_waves[{index}] roles and task_ids must have equal lengths"
            )
        for position, (role, task_id) in enumerate(zip(roles, task_ids)):
            if task_id in dispatched_ids:
                raise error_type(f"route dispatch task_id is duplicated: {task_id}")
            if task_id not in instance_by_id:
                raise error_type(
                    f"route parallel_waves[{index}].task_ids[{position}] is not a declared task instance: {task_id}"
                )
            if role not in selected_names:
                raise error_type(f"route dispatch role {role!r} is not selected")
            if instance_by_id[task_id]["role"] != role:
                raise error_type(
                    f"route task instance {task_id!r} role does not match its wave role"
                )
            wave_roles.append(role)
            dispatched_ids.append(task_id)

    mode = route["mode"]
    if mode == "inline":
        if selected_names or instance_by_id or dispatched_ids:
            raise error_type("inline route must select zero roles and emit zero dispatch instances")
    elif mode == "blocked":
        if instance_by_id or dispatched_ids:
            raise error_type("blocked route must emit zero dispatch instances")
    elif mode == "handoff":
        if instance_by_id or dispatched_ids:
            raise error_type("handoff route must emit zero local dispatch instances")
    elif mode in {"sequential", "parallel"}:
        if set(wave_roles) != set(selected_names):
            raise error_type("dispatch waves must cover every selected role exactly once")
        if set(dispatched_ids) != set(instance_by_id):
            raise error_type("dispatch waves must cover every task instance exactly once")
    return instance_by_id


def _validate_route(
    route: Any, *, error_type: type[RunStateError] = InputError
) -> dict[str, dict[str, Any]]:
    if not isinstance(route, dict):
        raise error_type("route must be a JSON object")
    try:
        errors = validate_instance(route, _load_schema("route.schema.json"), schema_name="route")
    except ValueError as exc:
        raise error_type(f"route schema cannot be evaluated: {exc}") from exc
    if errors:
        raise error_type("invalid route: " + "; ".join(errors))
    if route.get("workflow_owner") != "root":
        raise error_type("route workflow_owner must be root")
    selected = route.get("selected_roles", [])
    names = [entry.get("role") for entry in selected if isinstance(entry, dict)]
    if len(names) != len(set(names)):
        raise error_type("route selected_roles cannot contain duplicate roles")
    return _dispatch_instances(route, error_type=error_type)


def _validate_report(report: Any, *, error_type: type[RunStateError] = InputError) -> None:
    if not isinstance(report, dict):
        raise error_type("agent report must be a JSON object")
    try:
        errors = validate_instance(report, _load_schema("agent-report.schema.json"), schema_name="agent-report")
    except ValueError as exc:
        raise error_type(f"agent-report schema cannot be evaluated: {exc}") from exc
    if errors:
        raise error_type("invalid agent report: " + "; ".join(errors))


def _report_id(report: Mapping[str, Any]) -> str:
    """Return a stable report identity while keeping first-report compatibility."""
    return report.get("report_id", report["task_id"])


def _validate_reconciliation(
    reconciliation: Any,
    report_tasks: Mapping[str, str],
    *,
    error_type: type[RunStateError] = StateError,
    audit_at: datetime | None = None,
) -> None:
    if not isinstance(reconciliation, dict):
        raise error_type("reconciliation must be an object")
    decisions = reconciliation["decisions"]
    report_ids = [entry["report_id"] for entry in decisions]
    if len(report_ids) != len(set(report_ids)):
        raise error_type("reconciliation decisions cannot contain duplicate report IDs")
    unknown = set(report_ids) - set(report_tasks)
    if unknown:
        raise error_type(
            "reconciliation references unknown reports: "
            + ", ".join(sorted(unknown))
        )
    for index, entry in enumerate(decisions):
        if report_tasks[entry["report_id"]] != entry["task_id"]:
            raise error_type(
                f"reconciliation.decisions[{index}].task_id does not match its report"
            )
        if entry["decision"] not in RECONCILIATION_DECISIONS:
            raise error_type(f"reconciliation.decisions[{index}] has an unknown decision")
        decided_at = _timestamp(entry["at"], f"reconciliation.decisions[{index}].at")
        if audit_at is not None and decided_at > audit_at:
            raise error_type("reconciliation decision cannot be later than the state audit event")


def _validate_state(state: Any, run_id: str, *, error_type: type[RunStateError] = StateError) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise error_type("state must be a JSON object")
    try:
        errors = validate_instance(state, _load_schema("run-state.schema.json"), schema_name="run-state")
    except ValueError as exc:
        raise error_type(f"run-state schema cannot be evaluated: {exc}") from exc
    if errors:
        raise error_type("invalid run state: " + "; ".join(errors))
    if state.get("run_id") != run_id:
        raise error_type("state run_id does not match requested run ID")
    if state.get("status") not in STATUSES:
        raise error_type("state contains an unknown status")
    created_at = _timestamp(state["created_at"], "created_at")
    updated_at = _timestamp(state["updated_at"], "updated_at")
    history = state["history"]
    previous: str | None = None
    previous_at: datetime | None = None
    last_at: datetime | None = None
    for index, entry in enumerate(history):
        if not isinstance(entry, dict):
            raise error_type(f"history[{index}] must be an object")
        source = entry["from"]
        target = entry["to"]
        if index == 0:
            if source is not None or target != "created":
                raise error_type("history must begin with null -> created")
        elif source != previous:
            raise error_type(f"history[{index}] does not continue from the previous status")
        if index > 0 and previous in TERMINAL_STATUSES:
            raise error_type(f"history[{index}] occurs after terminal status {previous}")
        if target not in STATUSES:
            raise error_type(f"history[{index}] contains an unknown target status")
        if source is not None and source != target:
            if target == "completed":
                if entry["reason"] != "complete":
                    raise error_type("completed may only be entered by the complete command")
            elif target not in LEGAL_TRANSITIONS.get(source, frozenset()):
                raise error_type(f"illegal lifecycle transition in history: {source} -> {target}")
        entry_at = _timestamp(entry["at"], f"history[{index}].at")
        if index == 0 and entry_at != created_at:
            raise error_type("history must begin at created_at")
        if previous_at is not None and entry_at < previous_at:
            raise error_type(f"history[{index}].at is earlier than the previous event")
        previous_at = entry_at
        last_at = entry_at
        previous = target
    if previous != state["status"]:
        raise error_type("state status does not match the last history entry")
    if last_at is None or last_at != updated_at:
        raise error_type("updated_at must equal the timestamp of the last history event")
    route = state.get("route")
    dispatch_instances: dict[str, dict[str, Any]] = {}
    if route is not None:
        dispatch_instances = _validate_route(route, error_type=error_type)
    reports = state.get("reports", [])
    report_tasks: dict[str, str] = {}
    if route is None and reports:
        raise error_type("reports require a recorded dispatch route")
    for index, report in enumerate(reports):
        _validate_report(report, error_type=error_type)
        task_id = report["task_id"]
        report_id = _report_id(report)
        if report_id in report_tasks:
            raise error_type(f"duplicate report_id: {report_id}")
        report_tasks[report_id] = task_id
        if route is not None:
            instance = dispatch_instances.get(task_id)
            if instance is None:
                raise error_type(
                    f"reports[{index}].task_id {task_id!r} is not a declared dispatch instance"
                )
            if report["role"] != instance["role"]:
                raise error_type(
                    f"reports[{index}].role {report['role']!r} does not match dispatch instance {task_id!r}"
                )
    _validate_reconciliation(
        state["reconciliation"],
        report_tasks,
        error_type=error_type,
        audit_at=updated_at,
    )
    verification = state["verification"]
    if verification["integrated_at"] is not None:
        _timestamp(verification["integrated_at"], "verification.integrated_at")
    if state["status"] == "completed":
        _completion_predicate(
            state,
            error_type=error_type,
            require_eligible_status=False,
            audit_at=updated_at,
        )
    return state


def _load_state(path: Path, run_id: str) -> dict[str, Any]:
    try:
        state = load_json(path)
    except ValueError as exc:
        raise StateError(str(exc)) from exc
    return _validate_state(state, run_id)


def _canonical_output(state: Mapping[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _emit(state: Mapping[str, Any]) -> None:
    sys.stdout.write(_canonical_output(state))


def _new_run_id() -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run-{now}-{uuid.uuid4().hex[:12]}"


def _append_event(state: dict[str, Any], *, now: str, reason: str, target: str | None = None) -> None:
    source = state["status"]
    destination = source if target is None else target
    state["history"].append({"from": source, "to": destination, "at": now, "reason": reason})
    state["updated_at"] = now
    if target is not None:
        state["status"] = target


def _ensure_mutable(state: Mapping[str, Any]) -> None:
    if state["status"] in TERMINAL_STATUSES:
        raise Refusal(f"state is terminal ({state['status']}); no further mutation is allowed")


def _mutate(
    project_root: str | os.PathLike[str],
    run_id: str,
    operation: Callable[[dict[str, Any], str], None],
) -> dict[str, Any]:
    root = _resolve_project_root(project_root)
    path = _state_path(root, run_id, create=False)
    state = _load_state(path, run_id)
    _ensure_mutable(state)
    updated = copy.deepcopy(state)
    now = utc_now()
    operation(updated, now)
    _validate_state(updated, run_id)
    # The shared helper uses a sibling temporary and os.replace.  All parents
    # and the target were checked above, so it cannot create a new boundary.
    try:
        atomic_write_json(path, updated)
    except (OSError, ValueError) as exc:
        raise InputError(f"cannot atomically write state: {exc}") from exc
    return updated


def _read_json_value(path_value: str, label: str) -> Any:
    if not isinstance(path_value, str) or not path_value or path_value == "-":
        raise InputError(f"{label} must be an explicit JSON file path")
    path = Path(path_value)
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON constant: {value}")))
    except (OSError, UnicodeError, ValueError) as exc:
        raise InputError(f"cannot load {label} {path}: {exc}") from exc


def _read_record(path_value: str, label: str) -> dict[str, Any]:
    value = _read_json_value(path_value, label)
    if not isinstance(value, dict):
        raise InputError(f"{label} must contain a JSON object")
    return value


def _read_string_list_file(path_value: str, label: str) -> list[str]:
    value = _read_json_value(path_value, label)
    if isinstance(value, list):
        result = value
    elif isinstance(value, str):
        result = value.splitlines()
    else:
        raise InputError(f"{label} must contain a JSON string array or newline-delimited text")
    if not all(isinstance(item, str) and item.strip() for item in result):
        raise InputError(f"{label} must contain only non-empty strings")
    return [item.strip() for item in result]


def _latest_durable_mutation(state: Mapping[str, Any]) -> datetime | None:
    latest: datetime | None = None
    for entry in state["history"]:
        reason = entry["reason"]
        if reason.startswith(("route:", "report:", "acceptance:", "reconciliation:")) or (
            entry["from"] != entry["to"] and entry["to"] in {"implementing", "repairing"}
        ):
            timestamp = _timestamp(entry["at"], "history.at")
            if latest is None or timestamp > latest:
                latest = timestamp
    return latest


def _completion_predicate(
    state: Mapping[str, Any],
    *,
    error_type: type[RunStateError] = Refusal,
    require_eligible_status: bool,
    audit_at: datetime | None = None,
) -> None:
    """Validate completion prerequisites without requiring a lifecycle status.

    The same predicate is used by the transition command and by persisted
    ``completed`` state validation.  Keeping the predicate independent from
    status avoids trusting a terminal history reason after a state-file edit.
    """
    status = state["status"]
    if require_eligible_status and status not in COMPLETION_ELIGIBLE_STATUSES:
        raise error_type(f"completion requires an eligible state ({sorted(COMPLETION_ELIGIBLE_STATUSES)}), got {status}")
    acceptance = state["acceptance"]
    if acceptance["satisfied"] is not True:
        raise error_type("acceptance.satisfied must be true")
    if not acceptance["criteria"]:
        raise error_type("satisfied acceptance requires at least one criterion")
    route = state.get("route")
    if route is None:
        raise error_type("a recorded route is required")
    dispatch_instances = _validate_route(route, error_type=error_type)
    if route["mode"] == "blocked":
        raise error_type("blocked routes cannot complete")
    if route["mode"] in {"sequential", "parallel"}:
        if not dispatch_instances:
            raise error_type("an executable route must dispatch at least one task instance")
    elif route["mode"] not in {"inline"}:
        raise error_type(f"route mode {route['mode']!r} is not executable")
    reports = state["reports"]
    report_task_ids: set[str] = set()
    report_ids: set[str] = set()
    latest_reports: dict[str, Mapping[str, Any]] = {}
    for report in reports:
        _validate_report(report, error_type=error_type)
        task_id = report["task_id"]
        instance = dispatch_instances.get(task_id)
        if instance is None:
            raise error_type(f"report task_id {task_id!r} is not a declared dispatch instance")
        if report["role"] != instance["role"]:
            raise error_type(
                f"report role {report['role']!r} does not match dispatch instance {task_id!r}"
            )
        report_task_ids.add(task_id)
        report_id = _report_id(report)
        if report_id in report_ids:
            raise error_type(f"duplicate report_id: {report_id}")
        report_ids.add(report_id)
        latest_reports[task_id] = report
    # Historical failures remain immutable and require ACCEPT below; only a
    # later successful report of the same task can resolve their status.
    for report in latest_reports.values():
        if report["status"] in {"BLOCKED", "NEEDS_CONTEXT"}:
            raise error_type(
                f"report {_report_id(report)!r} has non-success status {report['status']}; completion is refused"
            )
    missing_reports = set(dispatch_instances) - report_task_ids
    if missing_reports:
        raise error_type("completion is missing reports for task instances: " + ", ".join(sorted(missing_reports)))
    decisions = {
        entry["report_id"]: entry["decision"]
        for entry in state["reconciliation"]["decisions"]
    }
    missing_decisions = report_ids - set(decisions)
    if missing_decisions:
        raise error_type(
            "completion requires an explicit ACCEPT decision for every report; missing: "
            + ", ".join(sorted(missing_decisions))
        )
    non_accept = {
        report_id: decisions[report_id]
        for report_id in report_ids
        if decisions[report_id] != "ACCEPT"
    }
    if non_accept:
        details = ", ".join(f"{report_id}={decision}" for report_id, decision in sorted(non_accept.items()))
        raise error_type("completion requires ACCEPT for every report; current decisions: " + details)

    reviewers = {"sol_reviewer", "security_reviewer"}
    writer_roles = {owner["role"] for owner in route["write_ownership"]}
    change_reports = {
        _report_id(report) for report in reports
        if report["role"] not in reviewers
        and (report["role"] in writer_roles or report["changed_files"])
    }
    report_events: dict[str, int] = {}
    last_change = last_verification = -1
    # Ledger order remains decisive when several events share one timestamp.
    for index, entry in enumerate(state["history"]):
        if entry["from"] != entry["to"] and entry["to"] in {"implementing", "repairing"}:
            last_change = index
        reason = entry["reason"]
        if reason.startswith("report:"):
            report_id = reason.removeprefix("report:")
            report_events[report_id] = index
            if report_id in change_reports:
                last_change = index
        elif reason == "verification:update":
            last_verification = index
    for report in latest_reports.values():
        if report["role"] in reviewers and report_events.get(_report_id(report), -1) <= last_change:
            raise error_type("final/security review must follow the latest implementation or diagnostic change")
    if last_verification <= last_change:
        raise error_type("integrated verification is stale after implementation or repair")

    integrated_at = state["verification"]["integrated_at"]
    if integrated_at is None:
        raise error_type("integrated verification is required")
    integrated_time = _timestamp(integrated_at, "verification.integrated_at")
    latest = _latest_durable_mutation(state)
    if latest is not None and integrated_time < latest:
        raise error_type(
            "integrated verification is stale after a route, report, acceptance, or reconciliation mutation"
        )
    audit_time = audit_at if audit_at is not None else _timestamp(state["updated_at"], "updated_at")
    if integrated_time > audit_time:
        raise error_type("integrated verification is later than the audit event")
    findings = state["verification"]["blocking_findings"]
    if findings:
        raise error_type("blocking findings must be empty")


def create_run(project_root: str | os.PathLike[str], run_id: str | None = None) -> dict[str, Any]:
    root = _resolve_project_root(project_root)
    chosen = _validate_run_id(run_id if run_id is not None else _new_run_id())
    path = _state_path(root, chosen, create=True)
    now = utc_now()
    state: dict[str, Any] = {
        "run_id": chosen,
        "status": "created",
        "created_at": now,
        "updated_at": now,
        "history": [{"from": None, "to": "created", "at": now, "reason": "created"}],
        "acceptance": {"criteria": [], "satisfied": False},
        "route": None,
        "reports": [],
        "reconciliation": {"decisions": []},
        "verification": {"integrated_at": None, "blocking_findings": []},
    }
    _validate_state(state, chosen)
    try:
        atomic_write_json(path, state)
    except (OSError, ValueError) as exc:
        run_dir = path.parent
        # The directory was created by this call.  Remove it only when it is
        # still the expected direct run child and remains empty; never recurse
        # or remove a path that may contain another writer's data.
        try:
            if (
                run_dir.name == chosen
                and run_dir.parent.name == "runs"
                and not run_dir.is_symlink()
                and run_dir.is_dir()
                and not any(run_dir.iterdir())
            ):
                run_dir.rmdir()
        except OSError:
            pass
        raise InputError(f"cannot atomically create state: {exc}") from exc
    return state


def show_run(project_root: str | os.PathLike[str], run_id: str) -> dict[str, Any]:
    root = _resolve_project_root(project_root)
    return _load_state(_state_path(root, run_id, create=False), run_id)


def transition_run(project_root: str | os.PathLike[str], run_id: str, target: str, reason: str) -> dict[str, Any]:
    if target not in STATUSES:
        raise Refusal(f"unknown lifecycle status: {target}")
    if target == "completed":
        raise Refusal("only the complete command may enter completed")
    if not isinstance(reason, str) or not reason.strip():
        raise Refusal("transition reason must be a non-empty string")

    def operation(state: dict[str, Any], now: str) -> None:
        source = state["status"]
        if source == target:
            raise Refusal("transition to the current status is not a lifecycle transition")
        if target not in LEGAL_TRANSITIONS[source]:
            raise Refusal(f"invalid lifecycle transition: {source} -> {target}")
        if target in {"implementing", "repairing"}:
            state["verification"]["integrated_at"] = None
        _append_event(state, now=now, target=target, reason=f"transition:{reason.strip()}")

    return _mutate(project_root, run_id, operation)


def record_route(project_root: str | os.PathLike[str], run_id: str, route: Mapping[str, Any]) -> dict[str, Any]:
    _validate_route(route)

    def operation(state: dict[str, Any], now: str) -> None:
        state["route"] = copy.deepcopy(dict(route))
        state["reconciliation"] = {"decisions": []}
        _append_event(state, now=now, reason="route:update")

    return _mutate(project_root, run_id, operation)


def record_report(project_root: str | os.PathLike[str], run_id: str, report: Mapping[str, Any]) -> dict[str, Any]:
    _validate_report(report)
    normalized_report = copy.deepcopy(dict(report))
    normalized_report.setdefault("report_id", normalized_report["task_id"])
    if metadata := normalized_report.get("artifact_review"):
        # Identity is recorder evidence, never a worker assertion.
        metadata.pop("filesystem_identity", None)
        try:
            root = Path(project_root).resolve(strict=True)
            artifact = artifact_path(root, metadata["path"])
            identity = artifact_identity(artifact)
            metadata["path"] = artifact.relative_to(root).as_posix()
        except (OSError, ValueError):
            identity = None  # Resolver still refuses unsafe or ambiguous paths.
        if identity is not None:
            metadata["filesystem_identity"] = identity

    def operation(state: dict[str, Any], now: str) -> None:
        route = state.get("route")
        if route is None:
            raise InputError("record a route before recording an agent report")
        dispatch_instances = _validate_route(route)
        instance = dispatch_instances.get(normalized_report["task_id"])
        if instance is None:
            raise InputError(
                f"report task_id {normalized_report['task_id']!r} is not a declared dispatch instance"
            )
        if normalized_report["role"] != instance["role"]:
            raise InputError(
                f"report role {normalized_report['role']!r} does not match dispatch instance {normalized_report['task_id']!r}"
            )
        report_id = normalized_report["report_id"]
        if any(_report_id(existing) == report_id for existing in state["reports"]):
            raise InputError(f"duplicate report_id: {report_id}")
        state["reports"].append(copy.deepcopy(normalized_report))
        _append_event(state, now=now, reason=f"report:{report_id}")

    return _mutate(project_root, run_id, operation)


def reconcile_run(
    project_root: str | os.PathLike[str],
    run_id: str,
    task_id: str,
    report_id: str | None,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    if not isinstance(task_id, str) or not task_id.strip():
        raise InputError("reconciliation requires one non-empty task ID")
    normalized_id = task_id.strip()
    if report_id is not None and (not isinstance(report_id, str) or not report_id.strip()):
        raise InputError("reconciliation report ID must be a non-empty string")
    normalized_report_id = report_id.strip() if report_id is not None else None
    if decision not in RECONCILIATION_DECISIONS:
        raise InputError("reconciliation decision must be ACCEPT, REPAIR, INVESTIGATE, REPLAN, or BLOCK")
    if not isinstance(reason, str) or not reason.strip():
        raise InputError("reconciliation reason must be a non-empty string")
    normalized_reason = reason.strip()

    def operation(state: dict[str, Any], now: str) -> None:
        matching_reports = [
            report for report in state["reports"] if report["task_id"] == normalized_id
        ]
        if not matching_reports:
            raise Refusal(f"task {normalized_id!r} has no recorded report to reconcile")
        if normalized_report_id is None:
            if len(matching_reports) != 1:
                raise Refusal(
                    f"task {normalized_id!r} has multiple reports; specify --report-id"
                )
            selected_report_id = _report_id(matching_reports[0])
        else:
            selected_report_id = normalized_report_id
            if not any(_report_id(report) == selected_report_id for report in matching_reports):
                raise Refusal(
                    f"report {selected_report_id!r} does not belong to task {normalized_id!r}"
                )
        entry = {
            "report_id": selected_report_id,
            "task_id": normalized_id,
            "decision": decision,
            "reason": normalized_reason,
            "at": now,
        }
        decisions = [
            existing
            for existing in state["reconciliation"]["decisions"]
            if existing["report_id"] != selected_report_id
        ]
        decisions.append(entry)
        state["reconciliation"] = {"decisions": sorted(decisions, key=lambda item: item["report_id"])}
        _append_event(state, now=now, reason=f"reconciliation:{selected_report_id}:{decision}")

    return _mutate(project_root, run_id, operation)


def set_acceptance(
    project_root: str | os.PathLike[str],
    run_id: str,
    criteria: list[str],
    satisfied: bool,
) -> dict[str, Any]:
    if not isinstance(criteria, list) or not all(isinstance(item, str) and item.strip() for item in criteria):
        raise InputError("acceptance criteria must be non-empty strings")
    if not isinstance(satisfied, bool):
        raise InputError("acceptance satisfied must be a boolean")
    normalized = [item.strip() for item in criteria]
    if satisfied and not normalized:
        raise InputError("satisfied acceptance requires at least one criterion")

    def operation(state: dict[str, Any], now: str) -> None:
        state["acceptance"] = {"criteria": normalized, "satisfied": satisfied}
        _append_event(state, now=now, reason="acceptance:update")

    return _mutate(project_root, run_id, operation)


def verify_run(
    project_root: str | os.PathLike[str],
    run_id: str,
    integrated_at: str | None = None,
    blocking_findings: list[str] | None = None,
) -> dict[str, Any]:
    timestamp = integrated_at if integrated_at is not None else utc_now()
    # Validate caller-supplied timestamps before reading/mutating state so a
    # rejected command cannot affect even the temporary file.
    if not isinstance(timestamp, str):
        raise InputError("integrated verification timestamp must be a string")
    _timestamp(timestamp, "integrated_at")
    findings = [] if blocking_findings is None else blocking_findings
    if not isinstance(findings, list) or not all(isinstance(item, str) and item.strip() for item in findings):
        raise InputError("blocking findings must be non-empty strings")
    findings = [item.strip() for item in findings]

    def operation(state: dict[str, Any], now: str) -> None:
        integrated_time = _timestamp(timestamp, "integrated_at")
        command_time = _timestamp(now, "verification event time")
        if integrated_time > command_time:
            raise Refusal("integrated verification cannot be later than the verification event")
        state["verification"] = {"integrated_at": timestamp, "blocking_findings": findings}
        _append_event(state, now=now, reason="verification:update")

    return _mutate(project_root, run_id, operation)


def complete_run(project_root: str | os.PathLike[str], run_id: str) -> dict[str, Any]:
    def operation(state: dict[str, Any], now: str) -> None:
        _completion_predicate(
            state,
            error_type=Refusal,
            require_eligible_status=True,
            audit_at=_timestamp(now, "completion event time"),
        )
        _append_event(state, now=now, target="completed", reason="complete")

    return _mutate(project_root, run_id, operation)


def _add_common(parser: argparse.ArgumentParser, *, run_required: bool) -> None:
    parser.add_argument("--project-root", required=True, help="explicit target project root")
    parser.add_argument("--run-id", required=run_required, help="safe run directory name")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record and validate root-owned orchestrator run state; never dispatches agents.",
        epilog="Every command requires --project-root PROJECT_ROOT; every command except create requires --run-id RUN_ID.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create an empty root-owned run")
    _add_common(create, run_required=False)

    show = subparsers.add_parser("show", help="read and validate an existing run")
    _add_common(show, run_required=True)

    transition = subparsers.add_parser("transition", help="record one explicit lifecycle transition")
    _add_common(transition, run_required=True)
    transition.add_argument("--to", required=True, choices=STATUSES)
    transition.add_argument("--reason", required=True)

    route = subparsers.add_parser("record-route", help="validate and record a route JSON file")
    _add_common(route, run_required=True)
    route.add_argument("--route", "--route-file", dest="route_file", required=True)

    report = subparsers.add_parser("record-report", help="validate and record an agent report JSON file")
    _add_common(report, run_required=True)
    report.add_argument("--report", "--report-file", dest="report_file", required=True)

    reconcile = subparsers.add_parser(
        "reconcile", help="record one explicit root decision for a reported task"
    )
    _add_common(reconcile, run_required=True)
    reconcile.add_argument("--task-id", required=True)
    reconcile.add_argument("--report-id")
    reconcile.add_argument("--decision", required=True, choices=sorted(RECONCILIATION_DECISIONS))
    reconcile.add_argument("--reason", required=True)

    acceptance = subparsers.add_parser("set-acceptance", help="replace criteria and explicit satisfaction")
    _add_common(acceptance, run_required=True)
    criteria = acceptance.add_mutually_exclusive_group()
    criteria.add_argument("--criteria", "--criterion", dest="criteria", action="append")
    criteria.add_argument("--criteria-file", dest="criteria_file")
    acceptance.add_argument("--satisfied", required=True, choices=("true", "false"))

    verify = subparsers.add_parser("verify", help="record integrated verification evidence")
    _add_common(verify, run_required=True)
    verify.add_argument("--integrated-at")
    verify.add_argument("--blocking-finding", dest="blocking_findings", action="append")
    verify.add_argument("--blocking-findings-file")

    complete = subparsers.add_parser("complete", help="enter completed only when all predicates hold")
    _add_common(complete, run_required=True)
    return parser


def _command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create":
        return create_run(args.project_root, args.run_id)
    if args.command == "show":
        return show_run(args.project_root, args.run_id)
    if args.command == "transition":
        return transition_run(args.project_root, args.run_id, args.to, args.reason)
    if args.command == "record-route":
        return record_route(args.project_root, args.run_id, _read_record(args.route_file, "route"))
    if args.command == "record-report":
        return record_report(args.project_root, args.run_id, _read_record(args.report_file, "agent report"))
    if args.command == "reconcile":
        return reconcile_run(
            args.project_root, args.run_id, args.task_id, args.report_id, args.decision, args.reason
        )
    if args.command == "set-acceptance":
        if args.criteria is None and args.criteria_file is None:
            raise InputError("set-acceptance requires --criteria or --criteria-file")
        if args.criteria is not None:
            criteria = args.criteria
        else:
            criteria = _read_string_list_file(args.criteria_file, "criteria file")
        return set_acceptance(args.project_root, args.run_id, criteria, args.satisfied == "true")
    if args.command == "verify":
        if args.blocking_findings is not None and args.blocking_findings_file is not None:
            raise InputError("use either --blocking-finding or --blocking-findings-file, not both")
        if args.blocking_findings_file is not None:
            findings = _read_string_list_file(args.blocking_findings_file, "blocking findings file")
        else:
            findings = args.blocking_findings
        return verify_run(args.project_root, args.run_id, args.integrated_at, findings)
    if args.command == "complete":
        return complete_run(args.project_root, args.run_id)
    raise InputError(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        state = _command(args)
    except RunStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _emit(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
