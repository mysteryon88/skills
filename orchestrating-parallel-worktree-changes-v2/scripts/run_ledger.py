#!/usr/bin/env python3
"""Maintain durable recovery state for one parallel worktree execution run."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = 1
OVERLAY_SCHEMA_VERSION = 2
EXECUTOR = "orchestrating-parallel-worktree-changes-v2"
START = "<!-- parallel-execution-manifest"
END = "parallel-execution-manifest -->"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REPLAN_REASON_CODES = {
    "WORKTREE_UNAVAILABLE",
    "HIDDEN_OVERLAP",
    "CONTRACT_DRIFT",
    "OWNERSHIP_DRIFT",
}
REVIEW_STATUSES = {
    "NOT_STARTED",
    "READY",
    "CHANGES_REQUIRED",
    "BLOCKED",
    "NEEDS_CONTEXT",
    "REPLAN_REQUIRED",
}
RESOURCE_KINDS = {"worktree", "branch", "report", "manifest", "scratch"}
RESOURCE_STATES = {"preserve", "clean", "merged", "failed"}
CLEANUP_STATUSES = {"pending", "in_progress", "blocked", "complete"}


class LedgerError(RuntimeError):
    """Expected, actionable ledger failure."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(command: Sequence[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise LedgerError(f"Cannot run {' '.join(command)}: {error}") from error
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown command error"
        raise LedgerError(f"Command failed: {' '.join(command)}\n{detail}")
    return result


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(("git", "-C", str(repo), *args), cwd=repo, check=check)


def _repo_root(repo: Path) -> Path:
    candidate = repo.expanduser().resolve()
    result = _run(("git", "-C", str(candidate), "rev-parse", "--show-toplevel"), cwd=candidate)
    return Path(result.stdout.strip()).resolve()


def _common_dir(root: Path) -> Path:
    raw = _git(root, "rev-parse", "--git-common-dir").stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _repo_relative_path(root: Path, path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise LedgerError(f"{label} must be inside the repository root") from error


def _current_branch(root: Path) -> str | None:
    result = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _resolve_commit(root: Path, ref: str) -> str:
    return _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").stdout.strip()


def _commit_exists(root: Path, commit: str) -> bool:
    if not COMMIT_RE.fullmatch(commit):
        return False
    result = _git(root, "cat-file", "-e", f"{commit}^{{commit}}", check=False)
    return result.returncode == 0


def _validate_identifier(value: str, label: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise LedgerError(
            f"Invalid {label} {value!r}. Use 1-80 ASCII letters, numbers, dots, "
            "underscores, or hyphens; start with a letter or number."
        )
    return value


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise LedgerError(f"Cannot hash {path}: {error}") from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise LedgerError(f"Cannot read {label} {path}: {error}") from error


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise LedgerError(f"Cannot atomically write {path}: {error}") from error


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_bytes(source.read_bytes())
        os.replace(temporary, target)
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise LedgerError(f"Cannot snapshot {source} to {target}: {error}") from error


def _extract_overlay(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise LedgerError(f"Cannot read overlay {path}: {error}") from error
    if text.count(START) != 1 or text.count(END) != 1:
        raise LedgerError("Overlay must contain exactly one parallel-execution-manifest block")
    payload = text.split(START, 1)[1].split(END, 1)[0].strip()
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as error:
        raise LedgerError(f"Cannot parse overlay manifest: {error}") from error
    if not isinstance(value, dict):
        raise LedgerError("Overlay manifest root must be a JSON object")
    return value


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{field} must be a non-empty string")
    return value


def _int_list(value: Any, field: str) -> list[int]:
    if not isinstance(value, list):
        raise LedgerError(f"{field} must be a list")
    result: list[int] = []
    for index, item in enumerate(value):
        if type(item) is not int:
            raise LedgerError(f"{field}[{index}] must be an integer Task ID")
        result.append(item)
    if len(set(result)) != len(result):
        raise LedgerError(f"{field} contains duplicate Task IDs")
    return result


def _evidence_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LedgerError(f"{field} must contain at least one evidence path")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_required_string(item, f"{field}[{index}]"))
    return result


def _task_ids(topology: dict[str, Any]) -> list[int]:
    scheduled: list[int] = []
    scheduled.extend(_int_list(topology.get("prelude_tasks", []), "prelude_tasks"))
    lanes = topology.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise LedgerError("lanes must contain at least one lane")
    lane_ids: set[str] = set()
    for index, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            raise LedgerError(f"lanes[{index}] must be an object")
        lane_id = _required_string(lane.get("id"), f"lanes[{index}].id")
        if lane_id in lane_ids:
            raise LedgerError(f"lanes[{index}].id duplicates lane {lane_id!r}")
        lane_ids.add(lane_id)
        scheduled.extend(_int_list(lane.get("tasks"), f"lanes[{index}].tasks"))
    scheduled.extend(_int_list(topology.get("epilogue_tasks", []), "epilogue_tasks"))
    if len(set(scheduled)) != len(scheduled):
        raise LedgerError("Overlay schedules a Task more than once")

    completed = topology.get("completed_tasks")
    if not isinstance(completed, list):
        raise LedgerError("completed_tasks must be a list")
    completed_ids: list[int] = []
    for index, record in enumerate(completed):
        if not isinstance(record, dict) or type(record.get("task")) is not int:
            raise LedgerError(f"completed_tasks[{index}].task must be an integer Task ID")
        completed_ids.append(record["task"])
    if len(set(completed_ids)) != len(completed_ids):
        raise LedgerError("completed_tasks contains duplicate Task IDs")
    if set(completed_ids) & set(scheduled):
        raise LedgerError("A Task cannot be both completed and scheduled")
    return sorted([*completed_ids, *scheduled])


def _validate_topology(topology: dict[str, Any], source: Path) -> list[int]:
    if topology.get("schema_version") != OVERLAY_SCHEMA_VERSION:
        raise LedgerError(f"Overlay schema_version must be {OVERLAY_SCHEMA_VERSION}")
    if topology.get("verdict") != "parallel":
        raise LedgerError("V2 run ledger requires a PARALLEL overlay")
    if topology.get("executor") != EXECUTOR:
        raise LedgerError(f"Overlay executor must be {EXECUTOR}")
    if topology.get("approval_required") is not True:
        raise LedgerError("PARALLEL overlay approval_required must be true")
    if topology.get("continue_without_confirmation") is not False:
        raise LedgerError("PARALLEL overlay continue_without_confirmation must be false")
    if topology.get("isolation") != "worktree":
        raise LedgerError("PARALLEL overlay isolation must be worktree")
    if topology.get("source_sha256") != _digest(source):
        raise LedgerError("Overlay source_sha256 does not match the source plan")
    if Path(str(topology.get("source_plan", ""))).name != source.name:
        raise LedgerError("Overlay source_plan does not match the source plan")
    return _task_ids(topology)


def _manifest_path(root: Path, run_id: str, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return _common_dir(root) / "parallel-runs" / run_id / "recovery.json"


def _snapshot_record(original: Path, snapshot: Path) -> dict[str, str]:
    return {
        "path": str(original.resolve()),
        "snapshot_path": str(snapshot.resolve()),
        "sha256": _digest(snapshot),
    }


def _validate_review_record(record: Any, task_ids: set[int]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LedgerError("review record must be a JSON object")
    task = record.get("task")
    if type(task) is not int or task not in task_ids:
        raise LedgerError("review record task must reference a source Task")
    status = record.get("status")
    if status not in REVIEW_STATUSES:
        raise LedgerError("review record status is invalid")
    fix_round = record.get("fix_round")
    if type(fix_round) is not int or not 0 <= fix_round <= 5:
        raise LedgerError("review record fix_round must be an integer from 0 through 5")
    findings = record.get("open_findings")
    if not isinstance(findings, list):
        raise LedgerError("review record open_findings must be a list")
    if status == "CHANGES_REQUIRED" and not findings:
        raise LedgerError("review record open_findings cannot be empty for CHANGES_REQUIRED")
    for index, finding in enumerate(findings):
        field = f"review record open_findings[{index}]"
        if not isinstance(finding, dict):
            raise LedgerError(f"{field} must be an object")
        _required_string(finding.get("id"), f"{field}.id")
        if finding.get("severity") not in {"Critical", "Important", "Minor"}:
            raise LedgerError(f"{field}.severity is invalid")
        _required_string(finding.get("summary"), f"{field}.summary")
        _evidence_list(finding.get("evidence"), f"{field}.evidence")
    reports = record.get("reports")
    if not isinstance(reports, list):
        raise LedgerError("review record reports must be a list")
    if status not in {"NOT_STARTED", "READY"} and not reports:
        raise LedgerError(f"review record reports cannot be empty for {status}")
    for index, report in enumerate(reports):
        _required_string(report, f"review record reports[{index}]")
    return copy.deepcopy(record)


def _validate_review_evidence(value: Any, field: str, verdict: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("verdict") != verdict:
        raise LedgerError(f"{field}.verdict must be {verdict}")
    _evidence_list(value.get("evidence"), f"{field}.evidence")
    return copy.deepcopy(value)


def _validate_lane_review_record(record: Any, lane_ids: set[str]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LedgerError("lane review record must be a JSON object")
    lane = record.get("lane")
    if lane not in lane_ids:
        raise LedgerError("lane review record lane must reference a topology lane")
    spec_verdict = record.get("spec_verdict")
    quality_verdict = record.get("quality_verdict")
    if spec_verdict not in {"NOT_STARTED", "PASS", "FAIL"}:
        raise LedgerError("lane review record spec_verdict is invalid")
    if quality_verdict not in {"NOT_STARTED", "APPROVED", "CHANGES_REQUIRED"}:
        raise LedgerError("lane review record quality_verdict is invalid")
    if quality_verdict != "NOT_STARTED" and spec_verdict != "PASS":
        raise LedgerError("lane quality review requires a passed specification verdict")
    findings = record.get("findings")
    if not isinstance(findings, list):
        raise LedgerError("lane review record findings must be a list")
    for index, finding in enumerate(findings):
        field = f"lane review record findings[{index}]"
        if not isinstance(finding, dict):
            raise LedgerError(f"{field} must be an object")
        _required_string(finding.get("id"), f"{field}.id")
        if finding.get("severity") not in {"Critical", "Important", "Minor"}:
            raise LedgerError(f"{field}.severity is invalid")
        _required_string(finding.get("summary"), f"{field}.summary")
        _evidence_list(finding.get("evidence"), f"{field}.evidence")
    reports = record.get("reports")
    if not isinstance(reports, list):
        raise LedgerError("lane review record reports must be a list")
    if spec_verdict != "NOT_STARTED" and not reports:
        raise LedgerError("lane review record reports must contain review evidence")
    for index, report in enumerate(reports):
        _required_string(report, f"lane review record reports[{index}]")
    if spec_verdict == "PASS" and quality_verdict == "APPROVED" and any(
        finding["severity"] in {"Critical", "Important"} for finding in findings
    ):
        raise LedgerError("approved lane review cannot retain Critical or Important findings")
    return copy.deepcopy(record)


def _validate_completion_record(
    record: Any,
    task_ids: set[int],
    root: Path,
    *,
    require_runtime_reviews: bool,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LedgerError("completion record must be a JSON object")
    task = record.get("task")
    if type(task) is not int or task not in task_ids:
        raise LedgerError("completion record task must reference a source Task")
    commits = record.get("commits")
    if not isinstance(commits, list) or not commits:
        raise LedgerError("completion record commits must contain at least one full commit SHA")
    for index, commit in enumerate(commits):
        if not isinstance(commit, str) or not _commit_exists(root, commit):
            raise LedgerError(f"completion record commits[{index}] must name an existing full commit SHA")
    checks = record.get("checks")
    if not isinstance(checks, list) or not checks:
        raise LedgerError("completion record checks must contain at least one command")
    for index, check in enumerate(checks):
        _required_string(check, f"completion record checks[{index}]")
    result = copy.deepcopy(record)
    runtime = require_runtime_reviews or record.get("completion_origin") == "runtime-replan"
    if runtime:
        result["completion_origin"] = "runtime-replan"
        result["spec_review"] = _validate_review_evidence(
            record.get("spec_review"), "completion record spec_review", "PASS"
        )
        result["quality_review"] = _validate_review_evidence(
            record.get("quality_review"), "completion record quality_review", "APPROVED"
        )
    elif record.get("completion_origin") is not None:
        raise LedgerError("completion record completion_origin is invalid")
    return result


def _validate_resource(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LedgerError("resource record must be a JSON object")
    kind = record.get("kind")
    if kind not in RESOURCE_KINDS:
        raise LedgerError("resource record kind is invalid")
    raw_path = _required_string(record.get("path"), "resource record path")
    if not Path(raw_path).is_absolute():
        raise LedgerError("resource record path must be absolute")
    if record.get("state") not in RESOURCE_STATES:
        raise LedgerError("resource record state is invalid")
    if kind in {"worktree", "branch"}:
        _required_string(record.get("branch"), "resource record branch")
    return copy.deepcopy(record)


def _validate_integration_record(record: Any, state: dict[str, Any], root: Path) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LedgerError("integration record must be a JSON object")
    lane = _required_string(record.get("lane"), "integration record lane")
    order = state["topology"].get("integration_order")
    if not isinstance(order, list) or any(not isinstance(item, str) for item in order):
        raise LedgerError("topology integration_order is invalid")
    completed_lanes = [item["lane"] for item in state["integration_records"]]
    if len(completed_lanes) >= len(order) or order[len(completed_lanes)] != lane:
        expected = order[len(completed_lanes)] if len(completed_lanes) < len(order) else "none"
        raise LedgerError(f"integration record lane {lane!r} is out of order; expected {expected!r}")
    lane_spec = next(
        (item for item in state["topology"]["lanes"] if item.get("id") == lane), None
    )
    if lane_spec is None:
        raise LedgerError(f"integration record lane {lane!r} is absent from topology lanes")
    completed_tasks = {item["task"] for item in state["completed_task_commits"]}
    incomplete_tasks = [task for task in lane_spec["tasks"] if task not in completed_tasks]
    if incomplete_tasks:
        raise LedgerError(
            f"integration record lane {lane!r} still has incomplete Tasks: "
            + ", ".join(str(task) for task in incomplete_tasks)
        )
    lane_review = next(item for item in state["lane_reviews"] if item["lane"] == lane)
    if (
        lane_review["spec_verdict"] != "PASS"
        or lane_review["quality_verdict"] != "APPROVED"
    ):
        raise LedgerError(
            f"integration record lane {lane!r} requires passed specification and quality reviews"
        )
    commit = _required_string(record.get("commit"), "integration record commit")
    if not _commit_exists(root, commit):
        raise LedgerError("integration record commit must name an existing full commit SHA")
    _evidence_list(record.get("checks"), "integration record checks")
    return copy.deepcopy(record)


def _validate_final_review(record: Any, state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LedgerError("final review record must be a JSON object")
    if record.get("verdict") not in {"APPROVED", "CHANGES_REQUIRED", "BLOCKED"}:
        raise LedgerError("final review verdict is invalid")
    _evidence_list(record.get("evidence"), "final review evidence")
    if not isinstance(record.get("cleanup_safe"), bool):
        raise LedgerError("final review cleanup_safe must be boolean")
    if record["verdict"] == "APPROVED":
        if state["review_state"]:
            raise LedgerError("final review cannot approve while Tasks remain")
        order = state["topology"].get("integration_order")
        integrated = [item["lane"] for item in state["integration_records"]]
        if integrated != order:
            raise LedgerError("final review cannot approve before every lane is integrated in order")
        if record["cleanup_safe"] is not True:
            raise LedgerError("approved final review must set cleanup_safe to true")
    return copy.deepcopy(record)


def _validate_cleanup_record(record: Any, state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LedgerError("cleanup record must be a JSON object")
    status = record.get("status")
    if status not in CLEANUP_STATUSES:
        raise LedgerError("cleanup record status is invalid")
    evidence = record.get("evidence", [])
    if status == "pending":
        if not isinstance(evidence, list):
            raise LedgerError("cleanup record evidence must be a list")
    else:
        _evidence_list(evidence, "cleanup record evidence")
    if status == "complete":
        final_review = state.get("final_review")
        if not isinstance(final_review, dict) or final_review.get("verdict") != "APPROVED":
            raise LedgerError("cleanup cannot complete without an approved final review")
        if final_review.get("cleanup_safe") is not True:
            raise LedgerError("cleanup cannot complete until final review marks cleanup safe")
    return copy.deepcopy(record)


def _identity_drift(record: dict[str, str]) -> bool:
    path = Path(record["path"])
    return not path.is_file() or _digest(path) != record["sha256"]


def _validate_manifest(
    state: Any,
    root: Path,
    run_id: str,
    path: Path,
) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise LedgerError("Recovery manifest root must be a JSON object")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError("Unsupported recovery manifest schema")
    if state.get("run_id") != run_id:
        raise LedgerError("Invalid recovery manifest ownership: run id mismatch")
    if Path(str(state.get("repo_root", ""))).resolve() != root:
        raise LedgerError("Invalid recovery manifest ownership: repository root mismatch")
    if Path(str(state.get("git_common_dir", ""))).resolve() != _common_dir(root):
        raise LedgerError("Invalid recovery manifest ownership: Git common directory mismatch")
    if Path(str(state.get("manifest_path", ""))).resolve() != path.resolve():
        raise LedgerError("Invalid recovery manifest ownership: manifest path mismatch")
    base_branch = _required_string(state.get("base_branch"), "base_branch")
    base_commit = _required_string(state.get("base_commit"), "base_commit")
    if not COMMIT_RE.fullmatch(base_commit) or not _commit_exists(root, base_commit):
        raise LedgerError("base_commit must name an existing full commit SHA")
    if not base_branch:
        raise LedgerError("base_branch is required")
    if state.get("isolation_mode") != "worktree":
        raise LedgerError("isolation_mode must be worktree")

    identities: dict[str, dict[str, Any]] = {}
    for field in ("source_plan", "overlay"):
        identity = state.get(field)
        if not isinstance(identity, dict):
            raise LedgerError(f"{field} identity is missing")
        snapshot = Path(_required_string(identity.get("snapshot_path"), f"{field}.snapshot_path"))
        digest_value = _required_string(identity.get("sha256"), f"{field}.sha256")
        if not snapshot.is_absolute() or not SHA256_RE.fullmatch(digest_value):
            raise LedgerError(f"{field} snapshot identity is invalid")
        if not snapshot.is_file() or _digest(snapshot) != digest_value:
            raise LedgerError(f"{field} snapshot hash mismatch")
        identities[field] = identity
    request_identity = state.get("source_request")
    if request_identity is not None:
        if not isinstance(request_identity, dict):
            raise LedgerError("source_request identity must be an object or null")
        request_snapshot = Path(
            _required_string(request_identity.get("snapshot_path"), "source_request.snapshot_path")
        )
        request_digest = _required_string(
            request_identity.get("sha256"), "source_request.sha256"
        )
        if (
            not request_snapshot.is_absolute()
            or not SHA256_RE.fullmatch(request_digest)
            or not request_snapshot.is_file()
            or _digest(request_snapshot) != request_digest
        ):
            raise LedgerError("source_request snapshot identity is invalid")

    topology = state.get("topology")
    if not isinstance(topology, dict):
        raise LedgerError("topology is missing")
    frozen_topology = _extract_overlay(Path(identities["overlay"]["snapshot_path"]))
    _validate_topology(frozen_topology, Path(identities["source_plan"]["snapshot_path"]))
    if topology != frozen_topology:
        raise LedgerError("topology does not match the frozen overlay snapshot")
    task_ids = _int_list(state.get("task_ids"), "task_ids")
    if task_ids != sorted(task_ids) or task_ids != _task_ids(topology):
        raise LedgerError("task_ids do not match the frozen topology")
    task_set = set(task_ids)

    completed = state.get("completed_task_commits")
    if not isinstance(completed, list):
        raise LedgerError("completed_task_commits must be a list")
    completed_ids: list[int] = []
    for record in completed:
        validated = _validate_completion_record(record, task_set, root, require_runtime_reviews=False)
        completed_ids.append(validated["task"])
    if len(set(completed_ids)) != len(completed_ids):
        raise LedgerError("completed_task_commits contains duplicate Tasks")

    reviews = state.get("review_state")
    if not isinstance(reviews, list):
        raise LedgerError("review_state must be a list")
    review_ids: list[int] = []
    for record in reviews:
        validated = _validate_review_record(record, task_set)
        review_ids.append(validated["task"])
    if len(set(review_ids)) != len(review_ids):
        raise LedgerError("review_state contains duplicate Tasks")
    if set(completed_ids) & set(review_ids):
        raise LedgerError("A Task cannot be both completed and remaining")
    if set(completed_ids) | set(review_ids) != task_set:
        raise LedgerError("completed_task_commits and review_state must cover every Task")

    lane_ids = [lane["id"] for lane in topology["lanes"]]
    lane_reviews = state.get("lane_reviews")
    if not isinstance(lane_reviews, list):
        raise LedgerError("lane_reviews must be a list")
    validated_lane_ids = [
        _validate_lane_review_record(record, set(lane_ids))["lane"]
        for record in lane_reviews
    ]
    if len(set(validated_lane_ids)) != len(validated_lane_ids):
        raise LedgerError("lane_reviews contains duplicate lanes")
    if set(validated_lane_ids) != set(lane_ids):
        raise LedgerError("lane_reviews must cover every topology lane")

    resources = state.get("resources")
    if not isinstance(resources, list):
        raise LedgerError("resources must be a list")
    resource_keys: set[tuple[str, str, str | None]] = set()
    for resource in resources:
        validated_resource = _validate_resource(resource)
        resource_key = (
            validated_resource["kind"],
            validated_resource["path"],
            validated_resource.get("branch"),
        )
        if resource_key in resource_keys:
            raise LedgerError("resources contains a duplicate owned resource")
        resource_keys.add(resource_key)
    integration_records = state.get("integration_records")
    if not isinstance(integration_records, list):
        raise LedgerError("integration_records must be a list")
    for index, integration_record in enumerate(integration_records):
        prefix_state = {**state, "integration_records": integration_records[:index]}
        _validate_integration_record(integration_record, prefix_state, root)
    final_review = state.get("final_review")
    if final_review is not None:
        _validate_final_review(final_review, state)
    _validate_cleanup_record(state.get("cleanup"), state)
    return state


def _load_manifest(
    root: Path,
    run_id: str,
    explicit: str | None,
    *,
    allow_drift: bool,
) -> tuple[Path, dict[str, Any]]:
    path = _manifest_path(root, run_id, explicit)
    if not path.is_file():
        raise LedgerError(f"No recovery manifest found for run {run_id!r}: {path}")
    state = _validate_manifest(_load_json(path, "recovery manifest"), root, run_id, path)
    drift = {
        "source_plan": _identity_drift(state["source_plan"]),
        "overlay": _identity_drift(state["overlay"]),
    }
    if not allow_drift and any(drift.values()):
        changed = ", ".join(key for key, value in drift.items() if value)
        raise LedgerError(f"Frozen input drift detected ({changed}); only status, validate, or replan is allowed")
    return path, state


def _write_manifest(path: Path, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = _now()
    _atomic_write_json(path, state)


def init_ledger(
    root: Path,
    run_id: str,
    source_plan: Path,
    overlay: Path,
    base_branch: str,
    base_commit: str,
    explicit_manifest: str | None,
    source_request: Path | None,
) -> dict[str, Any]:
    run_id = _validate_identifier(run_id, "run id")
    path = _manifest_path(root, run_id, explicit_manifest)
    if path.exists():
        raise LedgerError(f"Run {run_id!r} already has a recovery manifest: {path}")
    current_branch = _current_branch(root)
    if current_branch is None:
        raise LedgerError("Recovery ledger requires a checkout on a named branch; detached HEAD is unsupported")
    if current_branch != base_branch:
        raise LedgerError(f"Current named branch is {current_branch!r}, not requested base {base_branch!r}")
    if not COMMIT_RE.fullmatch(base_commit):
        raise LedgerError("--base-commit must be a full 40-character commit SHA")
    if _resolve_commit(root, "HEAD") != base_commit:
        raise LedgerError("--base-commit must match the current checkout HEAD")
    if _resolve_commit(root, base_branch) != base_commit:
        raise LedgerError("--base-branch tip must match --base-commit")

    source_plan = source_plan.expanduser().resolve()
    overlay = overlay.expanduser().resolve()
    if not source_plan.is_file() or not overlay.is_file():
        raise LedgerError("Source plan and overlay must be existing files")
    _repo_relative_path(root, source_plan, "Source plan")
    topology = _extract_overlay(overlay)
    task_ids = _validate_topology(topology, source_plan)

    run_dir = path.parent
    source_snapshot = run_dir / "inputs" / "source" / source_plan.name
    overlay_snapshot = run_dir / "inputs" / "overlay" / overlay.name
    _atomic_copy(source_plan, source_snapshot)
    _atomic_copy(overlay, overlay_snapshot)
    request_identity: dict[str, str] | None = None
    if source_request is not None:
        source_request = source_request.expanduser().resolve()
        if not source_request.is_file():
            raise LedgerError("--source-request must name an existing file")
        request_snapshot = run_dir / "inputs" / "request" / source_request.name
        _atomic_copy(source_request, request_snapshot)
        request_identity = _snapshot_record(source_request, request_snapshot)

    completed = copy.deepcopy(topology.get("completed_tasks", []))
    completed_ids: set[int] = set()
    for record in completed:
        validated = _validate_completion_record(record, set(task_ids), root, require_runtime_reviews=False)
        completed_ids.add(validated["task"])
    review_state = [
        {
            "task": task,
            "status": "NOT_STARTED",
            "fix_round": 0,
            "open_findings": [],
            "reports": [],
        }
        for task in task_ids
        if task not in completed_ids
    ]
    lane_reviews = [
        {
            "lane": lane["id"],
            "spec_verdict": "NOT_STARTED",
            "quality_verdict": "NOT_STARTED",
            "findings": [],
            "reports": [],
        }
        for lane in topology["lanes"]
    ]
    created = _now()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at_utc": created,
        "updated_at_utc": created,
        "repo_root": str(root),
        "git_common_dir": str(_common_dir(root)),
        "manifest_path": str(path.resolve()),
        "source_request": request_identity,
        "source_plan": _snapshot_record(source_plan, source_snapshot),
        "overlay": _snapshot_record(overlay, overlay_snapshot),
        "base_branch": base_branch,
        "base_commit": base_commit,
        "isolation_mode": "worktree",
        "phase": "initialized",
        "topology": topology,
        "task_ids": task_ids,
        "completed_task_commits": completed,
        "review_state": review_state,
        "lane_reviews": lane_reviews,
        "resources": [
            {"kind": "manifest", "path": str(path.resolve()), "state": "preserve"},
            {"kind": "scratch", "path": str(run_dir.resolve()), "state": "preserve"},
        ],
        "integration_records": [],
        "final_review": None,
        "replan": None,
        "cleanup": {"status": "pending", "evidence": []},
    }
    _validate_manifest(state, root, run_id, path)
    _write_manifest(path, state)
    return state


def set_review(root: Path, run_id: str, explicit: str | None, record_path: Path) -> dict[str, Any]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=False)
    record = _validate_review_record(_load_json(record_path, "review record"), set(state["task_ids"]))
    for index, existing in enumerate(state["review_state"]):
        if existing["task"] == record["task"]:
            state["review_state"][index] = record
            state["phase"] = "running"
            _validate_manifest(state, root, run_id, path)
            _write_manifest(path, state)
            return state
    raise LedgerError(f"Task {record['task']} is already completed or absent from this run")


def record_completion(
    root: Path, run_id: str, explicit: str | None, record_path: Path
) -> dict[str, Any]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=False)
    record = _validate_completion_record(
        _load_json(record_path, "completion record"),
        set(state["task_ids"]),
        root,
        require_runtime_reviews=True,
    )
    remaining = [item for item in state["review_state"] if item["task"] != record["task"]]
    if len(remaining) == len(state["review_state"]):
        raise LedgerError(f"Task {record['task']} is already completed or absent from this run")
    state["review_state"] = remaining
    state["completed_task_commits"].append(record)
    state["completed_task_commits"].sort(key=lambda item: item["task"])
    state["phase"] = "tasks_complete" if not remaining else "running"
    _validate_manifest(state, root, run_id, path)
    _write_manifest(path, state)
    return state


def register_resource(
    root: Path, run_id: str, explicit: str | None, record_path: Path
) -> dict[str, Any]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=False)
    record = _validate_resource(_load_json(record_path, "resource record"))
    key = (record["kind"], record["path"], record.get("branch"))
    for index, existing in enumerate(state["resources"]):
        existing_key = (existing["kind"], existing["path"], existing.get("branch"))
        if existing_key == key:
            state["resources"][index] = record
            break
    else:
        state["resources"].append(record)
    _validate_manifest(state, root, run_id, path)
    _write_manifest(path, state)
    return state


def set_lane_review(
    root: Path, run_id: str, explicit: str | None, record_path: Path
) -> dict[str, Any]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=False)
    lane_ids = {lane["id"] for lane in state["topology"]["lanes"]}
    record = _validate_lane_review_record(
        _load_json(record_path, "lane review record"), lane_ids
    )
    for index, existing in enumerate(state["lane_reviews"]):
        if existing["lane"] == record["lane"]:
            state["lane_reviews"][index] = record
            state["phase"] = "lane_review"
            _validate_manifest(state, root, run_id, path)
            _write_manifest(path, state)
            return state
    raise LedgerError(f"Lane {record['lane']!r} is absent from this run")


def record_integration(
    root: Path, run_id: str, explicit: str | None, record_path: Path
) -> dict[str, Any]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=False)
    record = _validate_integration_record(
        _load_json(record_path, "integration record"), state, root
    )
    state["integration_records"].append(record)
    state["phase"] = "integrating"
    _validate_manifest(state, root, run_id, path)
    _write_manifest(path, state)
    return state


def record_final_review(
    root: Path, run_id: str, explicit: str | None, record_path: Path
) -> dict[str, Any]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=False)
    record = _validate_final_review(_load_json(record_path, "final review record"), state)
    state["final_review"] = record
    state["phase"] = "verified" if record["verdict"] == "APPROVED" else "final_review"
    _validate_manifest(state, root, run_id, path)
    _write_manifest(path, state)
    return state


def record_cleanup(
    root: Path, run_id: str, explicit: str | None, record_path: Path
) -> dict[str, Any]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=False)
    record = _validate_cleanup_record(_load_json(record_path, "cleanup record"), state)
    state["cleanup"] = record
    state["phase"] = "complete" if record["status"] == "complete" else "cleanup"
    _validate_manifest(state, root, run_id, path)
    _write_manifest(path, state)
    return state


def write_replan(
    root: Path,
    run_id: str,
    explicit: str | None,
    reason_code: str,
    reason: str,
    recommended_verdict: str,
) -> tuple[Path, dict[str, Any]]:
    path, state = _load_manifest(root, run_id, explicit, allow_drift=True)
    if reason_code not in REPLAN_REASON_CODES:
        raise LedgerError("reason_code is invalid")
    _required_string(reason, "reason")
    if recommended_verdict not in {"sequential", "recompile"}:
        raise LedgerError("recommended_verdict is invalid")
    if reason_code == "WORKTREE_UNAVAILABLE" and recommended_verdict != "sequential":
        raise LedgerError("WORKTREE_UNAVAILABLE must recommend sequential")
    if not state["review_state"]:
        raise LedgerError("Cannot create a replan packet when no Tasks remain")

    packet_path = path.parent / "replan-required.json"
    state["phase"] = "replan_required"
    state["replan"] = {
        "reason_code": reason_code,
        "reason": reason,
        "recommended_verdict": recommended_verdict,
        "packet_path": str(packet_path.resolve()),
    }
    _validate_manifest(state, root, run_id, path)
    _write_manifest(path, state)
    packet = {
        "status": "REPLAN_REQUIRED",
        "reason_code": reason_code,
        "reason": reason,
        "source_plan": _repo_relative_path(
            root, Path(state["source_plan"]["path"]), "Source plan"
        ),
        "source_snapshot_path": state["source_plan"]["snapshot_path"],
        "source_sha256": state["source_plan"]["sha256"],
        "overlay_path": state["overlay"]["snapshot_path"],
        "overlay_sha256": state["overlay"]["sha256"],
        "base_branch": state["base_branch"],
        "base_commit": state["base_commit"],
        "manifest_path": str(path.resolve()),
        "manifest_sha256": _digest(path),
        "remaining_tasks": [item["task"] for item in state["review_state"]],
        "completed_task_commits": state["completed_task_commits"],
        "review_state": state["review_state"],
        "lane_reviews": state["lane_reviews"],
        "resources": state["resources"],
        "recommended_verdict": recommended_verdict,
    }
    _atomic_write_json(packet_path, packet)
    return packet_path, packet


def _validate_packet(path: Path, root: Path) -> dict[str, Any]:
    packet = _load_json(path, "replan packet")
    if not isinstance(packet, dict):
        raise LedgerError("Replan packet root must be a JSON object")
    if packet.get("status") != "REPLAN_REQUIRED":
        raise LedgerError("Replan packet status must be REPLAN_REQUIRED")
    if packet.get("reason_code") not in REPLAN_REASON_CODES:
        raise LedgerError("Replan packet reason_code is invalid")
    _required_string(packet.get("reason"), "replan packet reason")
    source_relative = _required_string(packet.get("source_plan"), "replan packet source_plan")
    source_path = (root / source_relative).resolve()
    if source_path == root or root not in source_path.parents:
        raise LedgerError("Replan packet source_plan must be repository-relative")
    source_sha = _required_string(packet.get("source_sha256"), "replan packet source_sha256")
    if not SHA256_RE.fullmatch(source_sha):
        raise LedgerError("Replan packet source_sha256 is invalid")
    if not source_path.is_file() or _digest(source_path) != source_sha:
        raise LedgerError("Replan packet source_plan hash mismatch")
    for field, hash_field in (
        ("source_snapshot_path", "source_sha256"),
        ("overlay_path", "overlay_sha256"),
        ("manifest_path", "manifest_sha256"),
    ):
        target = Path(_required_string(packet.get(field), f"replan packet {field}"))
        expected = _required_string(packet.get(hash_field), f"replan packet {hash_field}")
        if not target.is_absolute() or not SHA256_RE.fullmatch(expected):
            raise LedgerError(f"Replan packet {field} identity is invalid")
        if not target.is_file() or _digest(target) != expected:
            raise LedgerError(f"Replan packet {field} hash mismatch")
    if packet.get("recommended_verdict") not in {"sequential", "recompile"}:
        raise LedgerError("Replan packet recommended_verdict is invalid")
    return packet


def _summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": state["run_id"],
        "manifest_path": state["manifest_path"],
        "phase": state["phase"],
        "base_branch": state["base_branch"],
        "base_commit": state["base_commit"],
        "task_ids": state["task_ids"],
        "completed_tasks": [item["task"] for item in state["completed_task_commits"]],
        "remaining_tasks": [item["task"] for item in state["review_state"]],
    }


def _print(value: dict[str, Any], as_json: bool) -> None:
    del as_json
    print(json.dumps(value, indent=2, sort_keys=True))


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest", default=None, help="Optional harness-owned recovery.json path")
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create a validated recovery manifest")
    _add_common(init)
    init.add_argument("--source-plan", required=True)
    init.add_argument("--source-request")
    init.add_argument("--overlay", required=True)
    init.add_argument("--base-branch", required=True)
    init.add_argument("--base-commit", required=True)

    for name, help_text in (
        ("status", "Show the validated recovery manifest"),
        ("set-review", "Replace one remaining Task review record"),
        ("record-completion", "Record one fully reviewed Task completion"),
        ("register-resource", "Register or update one owned resource"),
        ("set-lane-review", "Replace one lane review record"),
        ("record-integration", "Record the next serial lane integration"),
        ("record-final-review", "Record the whole-branch final review"),
        ("record-cleanup", "Record resumable cleanup evidence"),
    ):
        command = commands.add_parser(name, help=help_text)
        _add_common(command)
        if name != "status":
            command.add_argument("--record", required=True)

    replan = commands.add_parser("replan", help="Write a compiler-compatible replan packet")
    _add_common(replan)
    replan.add_argument("--reason-code", required=True, choices=sorted(REPLAN_REASON_CODES))
    replan.add_argument("--reason", required=True)
    replan.add_argument("--recommended-verdict", required=True, choices=("sequential", "recompile"))

    validate = commands.add_parser("validate", help="Validate a recovery manifest or replan packet")
    _add_common(validate)
    validate.add_argument("--packet")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = _repo_root(Path(args.repo))
        run_id = _validate_identifier(args.run_id, "run id")
        if args.command == "init":
            state = init_ledger(
                root,
                run_id,
                Path(args.source_plan),
                Path(args.overlay),
                args.base_branch,
                args.base_commit,
                args.manifest,
                Path(args.source_request) if args.source_request else None,
            )
            _print(_summary(state), args.json)
        elif args.command == "status":
            _, state = _load_manifest(root, run_id, args.manifest, allow_drift=True)
            value = copy.deepcopy(state)
            value["input_drift"] = {
                "source_plan": _identity_drift(state["source_plan"]),
                "overlay": _identity_drift(state["overlay"]),
            }
            _print(value, args.json)
        elif args.command == "set-review":
            _print(_summary(set_review(root, run_id, args.manifest, Path(args.record))), args.json)
        elif args.command == "record-completion":
            _print(
                _summary(record_completion(root, run_id, args.manifest, Path(args.record))),
                args.json,
            )
        elif args.command == "register-resource":
            _print(
                _summary(register_resource(root, run_id, args.manifest, Path(args.record))),
                args.json,
            )
        elif args.command == "set-lane-review":
            _print(
                _summary(set_lane_review(root, run_id, args.manifest, Path(args.record))),
                args.json,
            )
        elif args.command == "record-integration":
            _print(
                _summary(record_integration(root, run_id, args.manifest, Path(args.record))),
                args.json,
            )
        elif args.command == "record-final-review":
            _print(
                _summary(record_final_review(root, run_id, args.manifest, Path(args.record))),
                args.json,
            )
        elif args.command == "record-cleanup":
            _print(
                _summary(record_cleanup(root, run_id, args.manifest, Path(args.record))),
                args.json,
            )
        elif args.command == "replan":
            packet_path, packet = write_replan(
                root,
                run_id,
                args.manifest,
                args.reason_code,
                args.reason,
                args.recommended_verdict,
            )
            _print(
                {
                    "status": packet["status"],
                    "packet_path": str(packet_path.resolve()),
                    "packet_sha256": _digest(packet_path),
                },
                args.json,
            )
        elif args.command == "validate":
            if args.packet:
                _validate_packet(Path(args.packet).expanduser().resolve(), root)
                _print({"status": "VALID", "packet": str(Path(args.packet).resolve())}, args.json)
            else:
                path, state = _load_manifest(root, run_id, args.manifest, allow_drift=True)
                _print({"status": "VALID", "manifest": str(path), **_summary(state)}, args.json)
        else:  # pragma: no cover - argparse enforces commands
            parser.error(f"Unknown command: {args.command}")
        return 0
    except LedgerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: operation interrupted; the last atomic checkpoint remains authoritative", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
