#!/usr/bin/env python3
"""Validate a derived execution overlay against its source plan."""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable

from plan_model import (
    PlanFormatError,
    canonical_path_key,
    interface_symbols,
    normalize_repo_path,
    parse_plan,
)
from normalize_plan_bundle import validate_bundle_bindings

START = "<!-- parallel-execution-manifest"
END = "parallel-execution-manifest -->"
SCHEMA_VERSION = 2
PARALLEL_EXECUTOR = "orchestrating-parallel-worktree-changes-v2"
SEQUENTIAL_EXECUTOR = "repository-sequential-workflow"
CRITICAL_PATH_SCHEDULER = "critical-path-v1"
RELATIONSHIP_CLASSIFICATIONS = {
    "hard-implementation",
    "ordering-only",
    "frozen-contract",
    "shared-file-conflict",
    "exclusive-resource",
}
CONTRACT_EVIDENCE_RE = re.compile(
    r"(^|/)(tests?|fixtures?|mocks?)(/|$)|(^|[._-])test([._-]|$)"
)
CONTRACT_TEST_COMMAND_RE = re.compile(r"\b(?:test|tests|pytest|unittest|vitest|jest)\b")
PLACEHOLDER_RE = re.compile(r"(?<![A-Za-z0-9_])<[A-Za-z][^<>\r\n]{0,100}>")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REPLAN_REASON_CODES = {
    "WORKTREE_UNAVAILABLE",
    "HIDDEN_OVERLAP",
    "CONTRACT_DRIFT",
    "OWNERSHIP_DRIFT",
}
GIT_TIMEOUT_SECONDS = 10.0
HARD_BASENAMES = {
    "bun.lock",
    "bun.lockb",
    "cargo.lock",
    "cargo.toml",
    "composer.json",
    "deno.json",
    "deno.jsonc",
    "gemfile",
    "gemfile.lock",
    "go.mod",
    "go.sum",
    "package.json",
    "package-lock.json",
    "pipfile",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pyproject.toml",
    "requirements.txt",
    "yarn.lock",
}
HARD_SEGMENTS = {"generated", "migrations", "migration", "schemas", "schema"}


def diagnostic_code(message: str) -> str:
    """Map human diagnostics to stable machine-readable categories."""
    rules = (
        ("executor must be", "EXECUTOR_INVALID"),
        ("WORKTREE_UNAVAILABLE requires", "WORKTREE_FALLBACK_INVALID"),
        ("source_sha256", "SOURCE_PLAN_HASH_INVALID"),
        ("source_plan", "SOURCE_PLAN_IDENTITY_INVALID"),
        ("hard shared surface", "HARD_SURFACE_CONFLICT"),
        ("allowed_overlaps", "OVERLAP_CONTRACT_INVALID"),
        ("allowed overlap", "OVERLAP_CONTRACT_INVALID"),
        ("between two and four", "LANE_COUNT_INVALID"),
        ("four active lanes", "LANE_COUNT_INVALID"),
        ("prelude_evidence", "PRELUDE_EVIDENCE_INVALID"),
        ("completed_tasks", "COMPLETION_EVIDENCE_INVALID"),
        ("completed Task", "COMPLETION_EVIDENCE_INVALID"),
        ("commit", "COMPLETION_EVIDENCE_INVALID"),
        ("global constraint", "GLOBAL_CONSTRAINT_INVALID"),
        ("task dependency", "TASK_DEPENDENCY_INVALID"),
        ("integration_order", "INTEGRATION_ORDER_INVALID"),
        ("placeholder", "PLACEHOLDER_UNRESOLVED"),
    )
    for fragment, code in rules:
        if fragment in message:
            return code
    return "VALIDATION_ERROR"


class DuplicateKeyError(ValueError):
    pass


def resolve_git_executable(value: Path | None) -> Path | None:
    """Validate an explicitly trusted Git executable without searching PATH."""
    if value is None:
        return None
    if not value.is_absolute():
        raise ValueError("--git-executable must be an absolute path")
    try:
        resolved = value.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"cannot resolve --git-executable: {exc}") from exc
    if not resolved.is_file():
        raise ValueError("--git-executable must resolve to a regular file")
    try:
        version = subprocess.run(
            [str(resolved), "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Git version probe failed: {exc}") from exc
    if version.returncode != 0:
        raise ValueError("--git-executable did not pass the Git version probe")
    return resolved


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def extract_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("overlay must contain exactly one parallel-execution-manifest block")
    payload = text.split(START, 1)[1].split(END, 1)[0].strip()
    value = json.loads(payload, object_pairs_hook=_object_no_duplicates)
    if not isinstance(value, dict):
        raise ValueError("manifest root must be a JSON object")
    return value


def _as_int_list(value: Any, field: str, errors: list[str]) -> list[int]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        errors.append(f"{field} must be a list of integer task IDs")
        return []
    return value


def _contains_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_RE.search(value))


def _validate_no_placeholders(value: Any, field: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if _contains_placeholder(value):
            errors.append(f"{field} contains an unresolved placeholder")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_placeholders(item, f"{field}[{index}]", errors)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_no_placeholders(item, f"{field}.{key}", errors)


def _as_nonempty_string_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must contain at least one non-empty command")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field}[{index}] must be a non-empty command")
            continue
        item = item.strip()
        if _contains_placeholder(item):
            errors.append(f"{field}[{index}] contains an unresolved placeholder")
            continue
        result.append(item)
    return result


def _as_path_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of repository-relative paths")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        try:
            normalized = normalize_repo_path(item)
        except PlanFormatError as exc:
            errors.append(f"{field}[{index}] is invalid: {exc}")
            continue
        result.append(normalized)
    return result


def _hard_surface(path_value: str) -> bool:
    try:
        normalized = normalize_repo_path(path_value)
    except PlanFormatError:
        return True
    pure = PurePosixPath(normalized)
    name = pure.name.casefold()
    parts = {part.casefold() for part in pure.parts}
    return (
        name in HARD_BASENAMES
        or pure.suffix.casefold() == ".lock"
        or (name.startswith("requirements") and name.endswith(".txt"))
        or bool(parts & HARD_SEGMENTS)
    )


def _validate_review_policy(manifest: dict[str, Any], errors: list[str]) -> None:
    policy = manifest.get("review_policy")
    if not isinstance(policy, dict):
        errors.append("review_policy is required")
        return
    required_true = (
        "per_task",
        "per_lane",
        "spec_and_quality",
        "scoped_rereview_each_round",
        "final_whole_branch",
    )
    for field in required_true:
        if policy.get(field) is not True:
            errors.append(f"review_policy.{field} must be true")
    if policy.get("max_fix_rounds") != 5:
        errors.append("review_policy.max_fix_rounds must be 5")
    if policy.get("final_fix_waves") != 1:
        errors.append("review_policy.final_fix_waves must be 1")


def _lane_graph_is_acyclic(lanes: list[dict[str, Any]], errors: list[str]) -> None:
    graph = {str(lane.get("id")): [str(dep) for dep in lane.get("depends_on", [])] for lane in lanes}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            errors.append(f"lane dependency cycle includes {node}")
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _dependency_graph_is_acyclic(edges: Iterable[tuple[int, int]], errors: list[str]) -> None:
    graph: dict[int, set[int]] = defaultdict(set)
    nodes: set[int] = set()
    for before, after in edges:
        graph[before].add(after)
        nodes.update((before, after))
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(node: int) -> None:
        if node in visited:
            return
        if node in visiting:
            errors.append(f"task dependency cycle includes Task {node}")
            return
        visiting.add(node)
        for child in graph.get(node, set()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node)


def _has_path(edges: set[tuple[int, int]], start: int, target: int) -> bool:
    graph: dict[int, set[int]] = defaultdict(set)
    for before, after in edges:
        graph[before].add(after)
    stack = [start]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, set()))
    return False


def _declared_dependencies(
    manifest: dict[str, Any],
    source_ids: set[int],
    errors: list[str],
    critical_path_overlay: bool,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    raw = manifest.get("task_dependencies", [])
    if not isinstance(raw, list):
        errors.append("task_dependencies must be a list")
        return set(), set()
    hard: set[tuple[int, int]] = set()
    frozen: set[tuple[int, int]] = set()
    seen: set[tuple[int, int]] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"task_dependencies[{index}] must be an object")
            continue
        before = item.get("before")
        after = item.get("after")
        if type(before) is not int or type(after) is not int:
            errors.append(f"task_dependencies[{index}] before/after must be integer task IDs")
            continue
        if before not in source_ids or after not in source_ids:
            errors.append(f"task dependency {before}->{after} references an unknown task")
        if before == after:
            errors.append(f"Task {before} cannot depend on itself")
        edge = (before, after)
        if edge in seen:
            errors.append(f"duplicate task dependency {before}->{after}")
            continue
        seen.add(edge)
        if not str(item.get("reason", "")).strip():
            errors.append(f"task dependency {before}->{after} requires a reason")
        classification = item.get("classification")
        if critical_path_overlay and classification not in {
            "hard-implementation",
            "frozen-contract",
        }:
            errors.append(
                f"task_dependencies classification for {before}->{after} must be "
                "hard-implementation or frozen-contract"
            )
            continue
        if classification == "frozen-contract":
            frozen.add((before, after))
        elif classification not in {"shared-file-conflict", "exclusive-resource"}:
            hard.add((before, after))
    return hard, frozen


def _contract_records(manifest: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    raw = manifest.get("contracts", [])
    if not isinstance(raw, list):
        errors.append("contracts must be a list")
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"contracts[{index}] must be an object")
        else:
            result.append(item)
    return result


def _matching_contract(
    contracts: list[dict[str, Any]], symbol: str, producer_lane: str, consumer_lane: str
) -> dict[str, Any] | None:
    for item in contracts:
        consumers = item.get("consumer_lanes", [])
        if (
            item.get("name") == symbol
            and item.get("producer_lane") == producer_lane
            and isinstance(consumers, list)
            and consumer_lane in consumers
        ):
            return item
    return None


def _quoted_interface_signatures(lines: Iterable[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        for signature in re.findall(r"`([^`]+)`", line):
            normalized = signature.strip()
            for symbol in interface_symbols([f"`{normalized}`"]):
                result[symbol].add(normalized)
    return result


def _is_pure_frozen_reference(line: str, producer: int, signatures: set[str]) -> bool:
    if producer not in {
        int(value) for value in re.findall(r"\bTask\s+(\d+)\b", line, re.IGNORECASE)
    }:
        return True
    quoted = {
        value.strip() for value in re.findall(r"`([^`]+)`", line) if value.strip()
    }
    if not quoted or not quoted.issubset(signatures):
        return False
    remainder = re.sub(r"^[\s-]*Consumes\s*:\s*", "", line, flags=re.IGNORECASE)
    remainder = re.sub(r"`[^`]+`", "", remainder)
    remainder = re.sub(
        r"\b(?:from\s+)?Task\s+\d+\b", "", remainder, flags=re.IGNORECASE
    )
    return not re.sub(r"[\s.,;:()\-]+", "", remainder)


def _longest_path_size(nodes: set[int], edges: set[tuple[int, int]]) -> int:
    parents: dict[int, set[int]] = {node: set() for node in nodes}
    children: dict[int, set[int]] = {node: set() for node in nodes}
    for before, after in edges:
        if before in nodes and after in nodes:
            parents[after].add(before)
            children[before].add(after)
    ranks = {node: 1 for node in nodes}
    ready = [node for node in nodes if not parents[node]]
    while ready:
        node = ready.pop()
        for child in children[node]:
            ranks[child] = max(ranks[child], ranks[node] + 1)
            parents[child].remove(node)
            if not parents[child]:
                ready.append(child)
    return max(ranks.values(), default=0)


def _validate_prelude_frontier(
    plan,
    prelude: list[int],
    evidence_records: list[Any],
    lane_tasks: set[int],
    hard_edges: set[tuple[int, int]],
    contract_edges: set[tuple[int, int]],
    exclusive_resources: list[tuple[str, list[int]]],
    errors: list[str],
) -> None:
    records = {
        item.get("task"): item
        for item in evidence_records
        if isinstance(item, dict) and type(item.get("task")) is int
    }
    task_by_id = {task.task_id: task for task in plan.tasks}
    source_order = {task.task_id: index for index, task in enumerate(plan.tasks)}
    active = (set(prelude) | lane_tasks) & set(task_by_id)
    parents: dict[int, set[int]] = {task_id: set() for task_id in active}
    children: dict[int, set[int]] = {task_id: set() for task_id in active}
    for before, after in hard_edges:
        if before in active and after in active:
            parents[after].add(before)
            children[before].add(after)
    exclusive_pairs: dict[tuple[int, int], set[str]] = defaultdict(set)
    for resource, task_ids in exclusive_resources:
        for index, left in enumerate(task_ids):
            for right in task_ids[index + 1 :]:
                exclusive_pairs[tuple(sorted((left, right)))].add(resource)

    def conflict_evidence(left: int, right: int) -> set[str]:
        result: set[str] = set()
        left_files = {canonical_path_key(path) for path in task_by_id[left].files}
        right_files = {canonical_path_key(path) for path in task_by_id[right].files}
        result.update(f"shared file `{path}`" for path in left_files & right_files)
        result.update(
            f"exclusive resource `{resource}`"
            for resource in exclusive_pairs.get(tuple(sorted((left, right))), set())
        )
        return result

    for task_id in prelude:
        ready = sorted(
            (candidate for candidate in active if not (parents[candidate] & active)),
            key=source_order.__getitem__,
        )
        if task_id not in ready:
            errors.append(f"prelude_evidence Task {task_id} is not dependency-ready")
            active.discard(task_id)
            continue
        safe_pair = next(
            (
                (left, right)
                for index, left in enumerate(ready)
                for right in ready[index + 1 :]
                if not conflict_evidence(left, right)
                and all(
                    consumer not in {left, right}
                    or producer not in active
                    or producer in {left, right}
                    for producer, consumer in contract_edges
                )
            ),
            None,
        )
        if safe_pair:
            errors.append(
                f"prelude_evidence Task {task_id} is unnecessary: Tasks "
                f"{safe_pair[0]} and {safe_pair[1]} already open two safe lanes"
            )
        record = records.get(task_id, {})
        classification = record.get("classification")
        declared = (
            {
                value
                for value in record.get("evidence", [])
                if isinstance(value, str)
            }
            if isinstance(record.get("evidence"), list)
            else set()
        )
        if classification == "frozen-contract":
            errors.append(f"prelude_evidence Task {task_id} cannot cite a frozen contract")
        elif classification in {"hard-implementation", "ordering-only"}:
            after = active - {task_id}
            unlocked = {
                child
                for child in children.get(task_id, set())
                if not (parents[child] & after)
            }
            if unlocked:
                expected = {
                    "unlocks "
                    + ", ".join(f"Task {child}" for child in sorted(unlocked))
                }
            elif len(ready) == 1:
                expected = {"only dependency-ready Task"}
            else:
                expected = set()
            if not expected or declared != expected:
                errors.append(
                    f"prelude_evidence Task {task_id} does not match its hard dependency frontier"
                )
        elif safe_pair is None:
            expected = {
                value
                for other in ready
                if other != task_id
                for value in conflict_evidence(task_id, other)
            }
            expected_class = (
                "exclusive-resource"
                if any(value.startswith("exclusive resource") for value in expected)
                else "shared-file-conflict"
            )
            if classification != expected_class or declared != expected:
                errors.append(
                    f"prelude_evidence Task {task_id} does not match its concurrency conflict"
                )
        active.remove(task_id)


def _validate_contract_record(
    contract: dict[str, Any],
    symbol: str,
    errors: list[str],
    exact_signatures: set[str] | None = None,
    evidence_files: set[str] | None = None,
) -> None:
    if contract.get("frozen_before_parallel") is not True:
        errors.append(f"contract {symbol} must be frozen_before_parallel")
    signature = contract.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        errors.append(f"contract {symbol} requires an exact signature")
    elif _contains_placeholder(signature):
        errors.append(f"contract {symbol} signature contains an unresolved placeholder")
    elif exact_signatures is not None and signature not in exact_signatures:
        errors.append(f"contract {symbol} must match an exact source signature")
    contract_tests = _as_nonempty_string_list(
        contract.get("contract_tests"), f"contract {symbol} contract_tests", errors
    )
    if exact_signatures is not None and not any(
        CONTRACT_TEST_COMMAND_RE.search(command.casefold()) for command in contract_tests
    ):
        errors.append(f"contract {symbol} contract_tests must contain a test command")
    if evidence_files is not None:
        declared_evidence = _as_nonempty_string_list(
            contract.get("evidence_files"), f"contract {symbol} evidence_files", errors
        )
        valid_evidence: set[str] = set()
        for path in declared_evidence:
            try:
                key = canonical_path_key(path)
            except PlanFormatError as exc:
                errors.append(f"contract {symbol} evidence file is invalid: {exc}")
                continue
            if CONTRACT_EVIDENCE_RE.search(key):
                valid_evidence.add(key)
        if declared_evidence and not (valid_evidence & evidence_files):
            errors.append(
                f"contract {symbol} evidence_files must name a producer or consumer test, fixture, or mock"
            )


def _validate_execution_order(
    sequence: list[int],
    source_index: dict[int, int],
    justified_edges: set[tuple[int, int]],
    label: str,
    errors: list[str],
) -> None:
    for left_index, left in enumerate(sequence):
        if left not in source_index:
            continue
        for right in sequence[left_index + 1 :]:
            if right not in source_index:
                continue
            if source_index[left] > source_index[right] and not _has_path(justified_edges, left, right):
                errors.append(
                    f"{label} reorders Task {left} before Task {right} without a declared or source dependency"
                )


def _git_repo_root(source: Path, git_executable: Path | None) -> Path | None:
    if git_executable is None:
        return None
    try:
        result = subprocess.run(
            [str(git_executable), "-C", str(source.parent), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def _lexical_git_root(source: Path) -> Path | None:
    resolved = source.resolve()
    for directory in (resolved.parent, *resolved.parents[1:]):
        if os.path.lexists(directory / ".git"):
            return directory
    return None


def _source_plan_identity(source: Path, git_executable: Path | None) -> str:
    source = source.resolve()
    repo_root = _git_repo_root(source, git_executable)
    if repo_root is None:
        if _lexical_git_root(source) is not None:
            raise ValueError(
                "source plan is inside a Git repository; pass a working trusted absolute "
                "--git-executable to verify repository-relative identity"
            )
        return source.name
    try:
        return source.relative_to(repo_root).as_posix()
    except ValueError:
        return source.name


def _validate_source_plan_identity(
    value: Any,
    source: Path,
    field: str,
    errors: list[str],
    git_executable: Path | None,
) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} is required")
        return
    try:
        normalized = normalize_repo_path(value)
    except PlanFormatError as exc:
        errors.append(f"{field} is invalid: {exc}")
        return
    try:
        expected = _source_plan_identity(source, git_executable)
    except ValueError as exc:
        errors.append(f"{field} cannot be verified: {exc}")
        return
    if canonical_path_key(normalized) != canonical_path_key(expected):
        errors.append(f"{field} must equal repository-relative path {expected}")


def _git_commit_exists(repo_root: Path, commit: str, git_executable: Path | None) -> bool:
    if git_executable is None:
        return False
    try:
        result = subprocess.run(
            [str(git_executable), "-C", str(repo_root), "cat-file", "-e", f"{commit}^{{commit}}"],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _git_commit_paths(
    repo_root: Path, commit: str, git_executable: Path | None
) -> set[str]:
    if git_executable is None:
        return set()
    try:
        result = subprocess.run(
            [
                str(git_executable),
                "-C",
                str(repo_root),
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "-z",
                "-r",
                commit,
            ],
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()
    paths: set[str] = set()
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            paths.add(canonical_path_key(raw.decode("utf-8", errors="surrogateescape")))
        except PlanFormatError:
            continue
    return paths


def _external_path(value: Any, base: Path, field: str, errors: list[str]) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty path")
        return None
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _validate_evidence_list(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must contain at least one evidence path")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field}[{index}] must be a non-empty evidence path")


def _validate_review_state(value: Any, source_ids: set[int], errors: list[str]) -> set[int]:
    if not isinstance(value, list):
        errors.append("review_state must be a list")
        return set()
    seen: set[int] = set()
    for index, record in enumerate(value):
        field = f"review_state[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{field} must be an object")
            continue
        task_id = record.get("task")
        if type(task_id) is not int or task_id not in source_ids:
            errors.append(f"{field}.task must reference a source Task")
        elif task_id in seen:
            errors.append(f"{field}.task duplicates Task {task_id}")
        else:
            seen.add(task_id)
        if record.get("status") not in {
            "NOT_STARTED",
            "READY",
            "CHANGES_REQUIRED",
            "BLOCKED",
            "NEEDS_CONTEXT",
            "REPLAN_REQUIRED",
        }:
            errors.append(f"{field}.status is invalid")
        fix_round = record.get("fix_round")
        if type(fix_round) is not int or not 0 <= fix_round <= 5:
            errors.append(f"{field}.fix_round must be an integer from 0 through 5")
        findings = record.get("open_findings")
        if not isinstance(findings, list):
            errors.append(f"{field}.open_findings must be a list")
        else:
            if record.get("status") == "CHANGES_REQUIRED" and not findings:
                errors.append(f"{field}.open_findings cannot be empty for CHANGES_REQUIRED")
            for finding_index, finding in enumerate(findings):
                finding_field = f"{field}.open_findings[{finding_index}]"
                if not isinstance(finding, dict):
                    errors.append(f"{finding_field} must be an object")
                    continue
                for key in ("id", "summary"):
                    if not isinstance(finding.get(key), str) or not finding[key].strip():
                        errors.append(f"{finding_field}.{key} must be non-empty")
                if finding.get("severity") not in {"Critical", "Important", "Minor"}:
                    errors.append(f"{finding_field}.severity is invalid")
                _validate_evidence_list(
                    finding.get("evidence"), f"{finding_field}.evidence", errors
                )
        reports = record.get("reports")
        if not isinstance(reports, list):
            errors.append(f"{field}.reports must be a list")
        else:
            if record.get("status") not in {"NOT_STARTED", "READY"} and not reports:
                errors.append(f"{field}.reports cannot be empty for {record.get('status')}")
            for report_index, report in enumerate(reports):
                if not isinstance(report, str) or not report.strip():
                    errors.append(f"{field}.reports[{report_index}] must be non-empty")
    return seen


def _validate_replan_handoff(
    manifest: dict[str, Any],
    plan,
    source: Path,
    overlay: Path,
    errors: list[str],
    git_executable: Path | None,
) -> dict[str, Any] | None:
    handoff = manifest.get("replan_handoff")
    if handoff is None:
        if "review_state" in manifest:
            errors.append("review_state requires replan_handoff")
        return None
    if not isinstance(handoff, dict):
        errors.append("replan_handoff must be an object")
        return None
    packet_path = _external_path(
        handoff.get("packet"), overlay.parent, "replan_handoff.packet", errors
    )
    packet_sha = handoff.get("packet_sha256")
    if not isinstance(packet_sha, str) or not SHA256_RE.fullmatch(packet_sha):
        errors.append("replan_handoff.packet_sha256 must be a 64-character SHA-256")
    if packet_path is None:
        return None
    try:
        packet_bytes = packet_path.read_bytes()
        packet = json.loads(packet_bytes, object_pairs_hook=_object_no_duplicates)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read replan_handoff.packet: {exc}")
        return None
    if not isinstance(packet, dict):
        errors.append("replan_handoff.packet root must be an object")
        return None
    if isinstance(packet_sha, str) and hashlib.sha256(packet_bytes).hexdigest() != packet_sha:
        errors.append("replan_handoff.packet_sha256 does not match the packet")

    source_ids = {task.task_id for task in plan.tasks}
    if packet.get("status") != "REPLAN_REQUIRED":
        errors.append("replan packet status must be REPLAN_REQUIRED")
    if packet.get("reason_code") not in REPLAN_REASON_CODES:
        errors.append("replan packet reason_code is invalid")
    if not isinstance(packet.get("reason"), str) or not packet["reason"].strip():
        errors.append("replan packet reason is required")
    _validate_source_plan_identity(
        packet.get("source_plan"),
        source,
        "replan packet source_plan",
        errors,
        git_executable,
    )
    if packet.get("source_sha256") != plan.sha256:
        errors.append("replan packet source_sha256 does not match the source plan")

    old_overlay = _external_path(
        packet.get("overlay_path"), source.parent, "replan packet overlay_path", errors
    )
    old_overlay_sha = packet.get("overlay_sha256")
    if not isinstance(old_overlay_sha, str) or not SHA256_RE.fullmatch(old_overlay_sha):
        errors.append("replan packet overlay_sha256 must be a 64-character SHA-256")
    elif old_overlay is not None:
        try:
            if hashlib.sha256(old_overlay.read_bytes()).hexdigest() != old_overlay_sha:
                errors.append("replan packet overlay_sha256 does not match overlay_path")
        except OSError as exc:
            errors.append(f"cannot read replan packet overlay_path: {exc}")

    recovery = _external_path(
        packet.get("manifest_path"), source.parent, "replan packet manifest_path", errors
    )
    recovery_sha = packet.get("manifest_sha256")
    if not isinstance(recovery_sha, str) or not SHA256_RE.fullmatch(recovery_sha):
        errors.append("replan packet manifest_sha256 must be a 64-character SHA-256")
    elif recovery is not None:
        try:
            if hashlib.sha256(recovery.read_bytes()).hexdigest() != recovery_sha:
                errors.append("replan packet manifest_sha256 does not match manifest_path")
        except OSError as exc:
            errors.append(f"cannot read replan packet manifest_path: {exc}")

    if not isinstance(packet.get("base_branch"), str) or not packet["base_branch"].strip():
        errors.append("replan packet base_branch is required")
    if not isinstance(packet.get("base_commit"), str) or not COMMIT_RE.fullmatch(
        packet["base_commit"]
    ):
        errors.append("replan packet base_commit must be a full commit SHA")
    remaining = _as_int_list(packet.get("remaining_tasks"), "replan packet remaining_tasks", errors)
    if set(remaining) - source_ids:
        errors.append("replan packet remaining_tasks reference unknown Tasks")

    completed_records = packet.get("completed_task_commits")
    if not isinstance(completed_records, list):
        errors.append("replan packet completed_task_commits must be a list")
        completed_records = []
    completed_ids = {
        item.get("task") for item in completed_records if isinstance(item, dict)
    }
    if completed_ids & set(remaining):
        errors.append("replan packet Tasks cannot be both completed and remaining")
    if (completed_ids | set(remaining)) != source_ids:
        errors.append("replan packet must cover every source Task")

    review_state = packet.get("review_state")
    review_tasks = _validate_review_state(review_state, source_ids, errors)
    if review_tasks != set(remaining):
        errors.append("replan packet review_state must cover exactly the remaining Tasks")
    if manifest.get("review_state") != review_state:
        errors.append("manifest review_state must match the replan packet")
    if manifest.get("completed_tasks") != completed_records:
        errors.append("manifest completed_tasks must match the replan packet")
    if manifest.get("sequential_tasks") != remaining:
        errors.append("manifest sequential_tasks must match replan packet remaining_tasks")

    resources = packet.get("resources")
    if not isinstance(resources, list):
        errors.append("replan packet resources must be a list")
    else:
        for index, resource in enumerate(resources):
            field = f"replan packet resources[{index}]"
            if not isinstance(resource, dict):
                errors.append(f"{field} must be an object")
                continue
            for key in ("kind", "path", "state"):
                if not isinstance(resource.get(key), str) or not resource[key].strip():
                    errors.append(f"{field}.{key} must be non-empty")
            if resource.get("kind") in {"worktree", "branch"} and (
                not isinstance(resource.get("branch"), str) or not resource["branch"].strip()
            ):
                errors.append(f"{field}.branch must be non-empty")
            if resource.get("kind") not in {
                "worktree",
                "branch",
                "report",
                "manifest",
                "scratch",
            }:
                errors.append(f"{field}.kind is invalid")
            resource_path = resource.get("path")
            if isinstance(resource_path, str) and resource_path.strip() and not Path(
                resource_path
            ).is_absolute():
                errors.append(f"{field}.path must be absolute")
            if resource.get("state") not in {"preserve", "clean", "merged", "failed"}:
                errors.append(f"{field}.state is invalid")
    if packet.get("recommended_verdict") not in {"sequential", "recompile"}:
        errors.append("replan packet recommended_verdict is invalid")
    if packet.get("reason_code") == "WORKTREE_UNAVAILABLE" and (
        packet.get("recommended_verdict") != "sequential"
        or manifest.get("verdict") != "sequential"
    ):
        errors.append("WORKTREE_UNAVAILABLE requires a SEQUENTIAL replacement")
    if manifest.get("verdict") == "sequential" and packet.get("recommended_verdict") != "sequential":
        errors.append("SEQUENTIAL replan handoff must recommend sequential")
    return packet


def _completed_task_ids(
    manifest: dict[str, Any],
    plan,
    source: Path,
    replan_packet: dict[str, Any] | None,
    errors: list[str],
    git_executable: Path | None,
) -> list[int]:
    raw = manifest.get("completed_tasks")
    if not isinstance(raw, list):
        errors.append("completed_tasks must be a list of evidence objects")
        return []

    task_by_id = {task.task_id: task for task in plan.tasks}
    repo_root = _git_repo_root(source, git_executable) if raw else None
    completed: list[int] = []
    for index, record in enumerate(raw):
        field = f"completed_tasks[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{field} must be an evidence object")
            continue
        task_id = record.get("task")
        if type(task_id) is not int:
            errors.append(f"{field}.task must be an integer task ID")
            continue
        completed.append(task_id)
        task = task_by_id.get(task_id)
        if task is None:
            errors.append(f"{field} references unknown Task {task_id}")
            continue
        runtime_completion = record.get("completion_origin") == "runtime-replan"
        if not task.completed and not (runtime_completion and replan_packet is not None):
            errors.append(f"completed Task {task_id} is not fully checked in the source plan")
        if runtime_completion:
            if replan_packet is None:
                errors.append(f"{field}.completion_origin requires replan_handoff")
            spec_review = record.get("spec_review")
            if not isinstance(spec_review, dict) or spec_review.get("verdict") != "PASS":
                errors.append(f"{field}.spec_review.verdict must be PASS")
            else:
                _validate_evidence_list(
                    spec_review.get("evidence"), f"{field}.spec_review.evidence", errors
                )
            quality_review = record.get("quality_review")
            if not isinstance(quality_review, dict) or quality_review.get("verdict") != "APPROVED":
                errors.append(f"{field}.quality_review.verdict must be APPROVED")
            else:
                _validate_evidence_list(
                    quality_review.get("evidence"),
                    f"{field}.quality_review.evidence",
                    errors,
                )
        elif record.get("completion_origin") is not None:
            errors.append(f"{field}.completion_origin must be runtime-replan when present")

        commits = record.get("commits")
        if not isinstance(commits, list) or not commits:
            errors.append(f"{field}.commits must contain at least one full commit SHA")
            commits = []
        changed_paths: set[str] = set()
        for commit_index, commit in enumerate(commits):
            commit_field = f"{field}.commits[{commit_index}]"
            if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
                errors.append(f"{commit_field} must be a full 40- or 64-character commit SHA")
                continue
            if repo_root is None:
                errors.append(f"{field} cannot verify commits because the source plan is not in a Git repository")
                continue
            if not _git_commit_exists(repo_root, commit, git_executable):
                errors.append(f"{commit_field} does not identify a commit in the source repository")
                continue
            changed_paths.update(_git_commit_paths(repo_root, commit, git_executable))

        _as_nonempty_string_list(record.get("checks"), f"{field}.checks", errors)
        task_paths = {canonical_path_key(path) for path in task.files}
        if not task_paths:
            errors.append(
                f"{field} cannot prove completion because Task {task_id} has no declared file"
            )
        elif commits and repo_root is not None and not (task_paths & changed_paths):
            errors.append(
                f"{field}.commits do not change any declared file for Task {task_id}"
            )

    for task in plan.tasks:
        if task.completed and task.task_id not in completed:
            errors.append(f"completed source Task {task.task_id} must have completed_tasks evidence")
    return completed


def _validate_global_constraints(
    manifest: dict[str, Any], source_constraints: list[str], source_ids: set[int], errors: list[str]
) -> list[tuple[str, list[int]]]:
    raw = manifest.get("global_constraints")
    if not isinstance(raw, list):
        errors.append("global_constraints must be a list that maps every source constraint")
        return []

    mapped: list[str] = []
    exclusive_resources: list[tuple[str, list[int]]] = []
    allowed_kinds = {"policy", "contract", "ordering", "exclusive-resource"}
    for index, record in enumerate(raw):
        field = f"global_constraints[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{field} must be an object")
            continue
        constraint = record.get("constraint")
        if not isinstance(constraint, str) or not constraint.strip():
            errors.append(f"{field}.constraint is required")
            continue
        constraint = constraint.strip()
        mapped.append(constraint)
        kind = record.get("kind")
        if kind not in allowed_kinds:
            errors.append(f"{field}.kind must be policy, contract, ordering, or exclusive-resource")
        tasks = _as_int_list(record.get("tasks"), f"{field}.tasks", errors)
        if not tasks:
            errors.append(f"{field}.tasks must map the constraint to at least one source Task")
        unknown = sorted(set(tasks) - source_ids)
        if unknown:
            errors.append(f"{field}.tasks references unknown Tasks: {', '.join(map(str, unknown))}")
        _as_nonempty_string_list(record.get("checks"), f"{field}.checks", errors)
        if kind == "exclusive-resource":
            resource = record.get("resource")
            if not isinstance(resource, str) or not resource.strip() or _contains_placeholder(resource):
                errors.append(f"{field}.resource must name the exclusive resource")
            else:
                exclusive_resources.append((resource.strip(), tasks))

    expected_counts = Counter(source_constraints)
    mapped_counts = Counter(mapped)
    for constraint, count in expected_counts.items():
        if mapped_counts[constraint] < count:
            errors.append(f"missing global constraint mapping: {constraint}")
    for constraint, count in mapped_counts.items():
        if expected_counts[constraint] < count:
            errors.append(f"global constraint is not present in the source plan: {constraint}")
    return exclusive_resources


def _lane_depends_transitively(
    lane_by_id: dict[str, dict[str, Any]], start: str, target: str
) -> bool:
    stack = [start]
    seen: set[str] = set()
    while stack:
        lane_id = stack.pop()
        if lane_id == target:
            return True
        if lane_id in seen:
            continue
        seen.add(lane_id)
        lane = lane_by_id.get(lane_id, {})
        stack.extend(str(dep) for dep in lane.get("depends_on", []))
    return False


def validate(
    source: Path, overlay: Path, git_executable: Path | None = None
) -> list[str]:
    errors: list[str] = []
    try:
        git_executable = resolve_git_executable(git_executable)
    except ValueError as exc:
        return [str(exc)]
    try:
        plan = parse_plan(source)
    except (OSError, UnicodeError, PlanFormatError) as exc:
        return [f"cannot read source plan: {exc}"]
    errors.extend(validate_bundle_bindings(source))
    try:
        manifest = extract_manifest(overlay)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot read overlay manifest: {exc}"]

    _validate_no_placeholders(manifest, "manifest", errors)

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if manifest.get("source_sha256") != plan.sha256:
        errors.append("source_sha256 does not match the source plan")
    _validate_source_plan_identity(
        manifest.get("source_plan"),
        source.resolve(),
        "source_plan",
        errors,
        git_executable,
    )
    if not plan.tasks:
        errors.append("source plan has no numbered tasks")
        return errors

    source_ids = [task.task_id for task in plan.tasks]
    source_set = set(source_ids)
    source_index = {task_id: index for index, task_id in enumerate(source_ids)}
    task_by_id = {task.task_id: task for task in plan.tasks}
    topology_metrics = manifest.get("topology_metrics")
    current_topology_fields = {
        "prelude_evidence",
        "ordering_constraints",
        "concurrency_conflicts",
        "repair_suggestions",
    }
    critical_path_overlay = manifest.get("verdict") == "parallel" and (
        "topology_metrics" in manifest
        or any(field in manifest for field in current_topology_fields)
    )
    if critical_path_overlay:
        if not isinstance(topology_metrics, dict):
            errors.append("topology_metrics is required for a critical-path overlay")
            topology_metrics = {}
        elif topology_metrics.get("scheduler") != CRITICAL_PATH_SCHEDULER:
            errors.append(
                f"topology_metrics.scheduler must be {CRITICAL_PATH_SCHEDULER}"
            )

    replan_packet = _validate_replan_handoff(
        manifest,
        plan,
        source.resolve(),
        overlay.resolve(),
        errors,
        git_executable,
    )
    completed = _completed_task_ids(
        manifest,
        plan,
        source.resolve(),
        replan_packet,
        errors,
        git_executable,
    )
    exclusive_resources = _validate_global_constraints(
        manifest, plan.global_constraints, source_set, errors
    )

    declared_edges, declared_frozen_edges = _declared_dependencies(
        manifest, source_set, errors, critical_path_overlay
    )
    source_reference_edges = {
        (dependency, task.task_id)
        for task in plan.tasks
        for dependency in task.depends_on_tasks
        if dependency in source_set and dependency != task.task_id
    }
    _validate_review_policy(manifest, errors)

    # Exact producer/consumer identifiers provide an additional contract graph.
    producers: dict[str, set[int]] = defaultdict(set)
    consumers: dict[str, set[int]] = defaultdict(set)
    producer_signatures: dict[tuple[int, str], set[str]] = defaultdict(set)
    consumer_signatures: dict[tuple[int, str], set[str]] = defaultdict(set)
    for task in plan.tasks:
        for symbol in interface_symbols(task.produces):
            producers[symbol].add(task.task_id)
        for symbol, signatures in _quoted_interface_signatures(task.produces).items():
            producer_signatures[(task.task_id, symbol)].update(signatures)
        for symbol in interface_symbols(task.consumes):
            consumers[symbol].add(task.task_id)
        for symbol, signatures in _quoted_interface_signatures(task.consumes).items():
            consumer_signatures[(task.task_id, symbol)].update(signatures)
    contract_edges: set[tuple[int, int]] = set()
    contract_symbols: dict[tuple[int, int], set[str]] = defaultdict(set)
    exact_contract_signatures: dict[tuple[int, int, str], set[str]] = defaultdict(set)
    for symbol in set(producers) & set(consumers):
        for producer in producers[symbol]:
            for consumer in consumers[symbol]:
                if producer != consumer:
                    contract_edges.add((producer, consumer))
                    contract_symbols[(producer, consumer)].add(symbol)
                    exact_contract_signatures[(producer, consumer, symbol)].update(
                        producer_signatures[(producer, symbol)]
                        & consumer_signatures[(consumer, symbol)]
                    )
    relaxable_contract_edges: set[tuple[int, int]] = set()
    verification = manifest.get("integrated_verification")
    verification_commands = (
        verification.get("commands", []) if isinstance(verification, dict) else []
    )
    has_contract_test_command = any(
        isinstance(command, str)
        and CONTRACT_TEST_COMMAND_RE.search(command.casefold())
        for command in verification_commands
    )
    for producer, consumer in contract_edges:
        signatures = {
            signature
            for symbol in contract_symbols[(producer, consumer)]
            for signature in exact_contract_signatures[(producer, consumer, symbol)]
        }
        referenced_lines = [
            line
            for line in task_by_id[consumer].consumes
            if producer
            in {
                int(value)
                for value in re.findall(r"\bTask\s+(\d+)\b", line, re.IGNORECASE)
            }
        ]
        has_contract_evidence = any(
            CONTRACT_EVIDENCE_RE.search(canonical_path_key(file_path))
            for task_id in (producer, consumer)
            for file_path in task_by_id[task_id].files
        )
        if signatures and has_contract_evidence and has_contract_test_command and (
            not referenced_lines
            or all(
                _is_pure_frozen_reference(line, producer, signatures)
                for line in referenced_lines
            )
        ):
            relaxable_contract_edges.add((producer, consumer))
    for before, after in sorted(declared_frozen_edges - relaxable_contract_edges):
        errors.append(
            f"task dependency {before}->{after} cannot be frozen without an exact source contract"
        )
    source_hard_edges = (
        source_reference_edges | contract_edges
    ) - relaxable_contract_edges
    remaining_ids = source_set - set(completed)
    required_hard_edges = {
        edge for edge in source_hard_edges if set(edge).issubset(remaining_ids)
    }
    required_frozen_edges = {
        edge for edge in relaxable_contract_edges if set(edge).issubset(remaining_ids)
    }
    if critical_path_overlay:
        for before, after in sorted(declared_edges - required_hard_edges):
            errors.append(
                f"task dependency {before}->{after} is not source-backed"
            )
        for before, after in sorted(declared_frozen_edges - required_frozen_edges):
            errors.append(
                f"task dependency {before}->{after} is not an active source-backed frozen contract"
            )
        for before, after in sorted(required_hard_edges - declared_edges):
            errors.append(
                f"task dependency {before}->{after} must be classified as hard-implementation"
            )
        for before, after in sorted(required_frozen_edges - declared_frozen_edges):
            errors.append(
                f"task dependency {before}->{after} must be classified as frozen-contract"
            )
    # A source "Consumes ... from Task N" reference is allowed to cross a
    # concurrent lane only when the referenced producer/consumer contract is
    # exact and frozen. References without an identifiable contract remain
    # hard ordering dependencies.
    hard_edges = declared_edges | source_hard_edges
    _dependency_graph_is_acyclic(hard_edges | contract_edges, errors)
    justified_edges = hard_edges | contract_edges

    verdict = manifest.get("verdict")
    assigned: list[int] = list(completed)
    placements: dict[int, dict[str, Any]] = {
        task_id: {"kind": "completed", "rank": -2, "order": index}
        for index, task_id in enumerate(completed)
    }
    lanes: list[dict[str, Any]] = []
    lane_by_id: dict[str, dict[str, Any]] = {}
    integration_order: list[str] = []
    max_wave = 0
    critical_evidence_records: list[Any] = []

    if verdict == "sequential":
        if manifest.get("executor") != SEQUENTIAL_EXECUTOR:
            errors.append(f"SEQUENTIAL executor must be {SEQUENTIAL_EXECUTOR}")
        if manifest.get("approval_required") is not False:
            errors.append("SEQUENTIAL approval_required must be false")
        if manifest.get("continue_without_confirmation") is not True:
            errors.append("SEQUENTIAL continue_without_confirmation must be true")
        if not str(manifest.get("reason", "")).strip():
            errors.append("SEQUENTIAL reason is required")
        sequence = _as_int_list(manifest.get("sequential_tasks", []), "sequential_tasks", errors)
        assigned.extend(sequence)
        for index, task_id in enumerate(sequence):
            placements[task_id] = {"kind": "sequential", "rank": 0, "order": index}
        _validate_execution_order(sequence, source_index, justified_edges, "sequential_tasks", errors)

    elif verdict == "parallel":
        if manifest.get("executor") != PARALLEL_EXECUTOR:
            errors.append(f"PARALLEL executor must be {PARALLEL_EXECUTOR}")
        if manifest.get("approval_required") is not True:
            errors.append("PARALLEL approval_required must be true")
        if manifest.get("continue_without_confirmation") is not False:
            errors.append("PARALLEL continue_without_confirmation must be false")
        isolation = manifest.get("isolation")
        if isolation != "worktree":
            errors.append("isolation must be worktree; shared-checkout is unsupported")

        prelude = _as_int_list(manifest.get("prelude_tasks", []), "prelude_tasks", errors)
        assigned.extend(prelude)
        for index, task_id in enumerate(prelude):
            placements[task_id] = {"kind": "prelude", "rank": -1, "order": index}
        _validate_execution_order(prelude, source_index, justified_edges, "prelude_tasks", errors)

        if critical_path_overlay or prelude or "prelude_evidence" in manifest:
            raw_evidence = manifest.get("prelude_evidence")
            if not isinstance(raw_evidence, list):
                errors.append("prelude_evidence must be a list")
                raw_evidence = []
            evidence_tasks: list[int] = []
            for index, item in enumerate(raw_evidence):
                if not isinstance(item, dict):
                    errors.append(f"prelude_evidence[{index}] must be an object")
                    continue
                task_id = item.get("task")
                if type(task_id) is not int:
                    errors.append(f"prelude_evidence[{index}].task must be an integer")
                    continue
                evidence_tasks.append(task_id)
                if item.get("classification") not in RELATIONSHIP_CLASSIFICATIONS:
                    errors.append(
                        f"prelude_evidence[{index}].classification must be a supported relationship"
                    )
                if not str(item.get("reason", "")).strip():
                    errors.append(f"prelude_evidence[{index}].reason is required")
                evidence = item.get("evidence")
                if (
                    not isinstance(evidence, list)
                    or not evidence
                    or any(not isinstance(value, str) or not value.strip() for value in evidence)
                ):
                    errors.append(
                        f"prelude_evidence[{index}].evidence must be a non-empty list of strings"
                    )
            if Counter(evidence_tasks) != Counter(prelude):
                errors.append("prelude_evidence must cover every prelude Task exactly once")
            critical_evidence_records = raw_evidence

        raw_lanes = manifest.get("lanes")
        if not isinstance(raw_lanes, list):
            errors.append("lanes must be a list")
            raw_lanes = []
        lane_ids: list[str] = []
        active_waves: Counter[int] = Counter()
        for index, raw_lane in enumerate(raw_lanes):
            if not isinstance(raw_lane, dict):
                errors.append(f"lanes[{index}] must be an object")
                continue
            lane = dict(raw_lane)
            lane_id = str(lane.get("id", "")).strip()
            if not lane_id:
                errors.append(f"lanes[{index}].id is required")
                lane_id = f"invalid-{index}"
            lane_ids.append(lane_id)
            wave = lane.get("wave")
            if type(wave) is not int or wave < 1:
                errors.append(f"lane {lane_id} wave must be a positive integer")
                wave = 0
            lane["wave"] = wave
            max_wave = max(max_wave, wave)
            tasks = _as_int_list(lane.get("tasks", []), f"lane {lane_id} tasks", errors)
            lane["tasks"] = tasks
            if not tasks:
                errors.append(f"lane {lane_id} must contain at least one source Task")
            owned_files = _as_path_list(
                lane.get("owned_files", []), f"lane {lane_id} owned_files", errors
            )
            lane["owned_files"] = owned_files
            if tasks:
                active_waves[wave] += 1
            assigned.extend(tasks)
            for task_order, task_id in enumerate(tasks):
                placements[task_id] = {
                    "kind": "lane",
                    "rank": wave,
                    "wave": wave,
                    "lane": lane_id,
                    "order": task_order,
                }
            _validate_execution_order(tasks, source_index, justified_edges, f"lane {lane_id}", errors)
            depends = lane.get("depends_on", [])
            if not isinstance(depends, list) or any(not isinstance(dep, str) for dep in depends):
                errors.append(f"lane {lane_id} depends_on must be a list of lane IDs")
                lane["depends_on"] = []
            lanes.append(lane)

        if len(lane_ids) != len(set(lane_ids)):
            errors.append("lane IDs must be unique")
        nonempty_lane_count = sum(bool(lane.get("tasks")) for lane in lanes)
        if critical_path_overlay and max(active_waves.values(), default=0) > 4:
            errors.append("critical-path waves allow at most four active lanes")
        elif not critical_path_overlay and not 2 <= nonempty_lane_count <= 4:
            errors.append("PARALLEL verdict requires between two and four non-empty lanes")
        if max(active_waves.values(), default=0) < 2:
            errors.append("PARALLEL verdict requires at least two active lanes in one wave")
        lane_by_id = {str(lane.get("id")): lane for lane in lanes}
        for lane in lanes:
            lane_id = str(lane.get("id"))
            wave = int(lane.get("wave", 0))
            for dep in lane.get("depends_on", []):
                if dep not in lane_by_id:
                    errors.append(f"lane {lane_id} depends on unknown lane {dep}")
                elif dep == lane_id:
                    errors.append(f"lane {lane_id} cannot depend on itself")
                elif int(lane_by_id[dep].get("wave", 0)) >= wave:
                    errors.append(f"lane {lane_id} dependency {dep} must be in an earlier wave")
        _lane_graph_is_acyclic(lanes, errors)

        raw_integration = manifest.get("integration_order")
        if not isinstance(raw_integration, list) or any(not isinstance(item, str) for item in raw_integration):
            errors.append("integration_order must be a list of lane IDs")
            raw_integration = []
        integration_order = list(raw_integration)
        if Counter(integration_order) != Counter(lane_ids):
            errors.append("integration_order must contain every lane exactly once")
        order_index = {lane_id: index for index, lane_id in enumerate(integration_order)}
        for lane in lanes:
            lane_id = str(lane.get("id"))
            for dep in lane.get("depends_on", []):
                if dep in order_index and lane_id in order_index and order_index[dep] > order_index[lane_id]:
                    errors.append(f"integration_order places {lane_id} before dependency {dep}")

        epilogue = _as_int_list(manifest.get("epilogue_tasks", []), "epilogue_tasks", errors)
        assigned.extend(epilogue)
        for index, task_id in enumerate(epilogue):
            placements[task_id] = {
                "kind": "epilogue",
                "rank": max_wave + 1,
                "order": index,
            }
        _validate_execution_order(epilogue, source_index, justified_edges, "epilogue_tasks", errors)

        if critical_path_overlay or prelude:
            lane_tasks = {
                task_id for lane in lanes for task_id in lane.get("tasks", [])
            }
            _validate_prelude_frontier(
                plan,
                prelude,
                critical_evidence_records,
                lane_tasks,
                source_hard_edges,
                relaxable_contract_edges,
                exclusive_resources,
                errors,
            )

        if critical_path_overlay:
            wave_durations = {
                wave: max(
                    (
                        len(lane.get("tasks", []))
                        for lane in lanes
                        if lane.get("wave") == wave
                    ),
                    default=0,
                )
                for wave in {lane.get("wave") for lane in lanes if lane.get("wave")}
            }
            expected_ordering_constraints = [
                {
                    "constraint": record.get("constraint"),
                    "tasks": record.get("tasks", []),
                    "checks": record.get("checks", []),
                    "classification": "ordering-only",
                }
                for record in (
                    manifest.get("global_constraints", [])
                    if isinstance(manifest.get("global_constraints"), list)
                    else []
                )
                if isinstance(record, dict) and record.get("kind") == "ordering"
            ]
            if manifest.get("ordering_constraints") != expected_ordering_constraints:
                errors.append(
                    "ordering_constraints must exactly match mapped ordering constraints"
                )

            conflict_evidence: dict[
                tuple[int, int], dict[str, set[str]]
            ] = defaultdict(lambda: defaultdict(set))
            file_owners: dict[str, set[int]] = defaultdict(set)
            for task_id in remaining_ids:
                for file_path in task_by_id[task_id].files:
                    file_owners[canonical_path_key(file_path)].add(task_id)
            for file_path, owners in file_owners.items():
                ordered_owners = sorted(owners)
                for index, left in enumerate(ordered_owners):
                    for right in ordered_owners[index + 1 :]:
                        conflict_evidence[(left, right)]["shared-file-conflict"].add(
                            f"shared file `{file_path}`"
                        )
            for resource, task_ids in exclusive_resources:
                affected = sorted(set(task_ids) & remaining_ids)
                for index, left in enumerate(affected):
                    for right in affected[index + 1 :]:
                        conflict_evidence[(left, right)]["exclusive-resource"].add(
                            f"exclusive resource `{resource}`"
                        )
            expected_conflicts = [
                {
                    "tasks": [left, right],
                    "classification": classification,
                    "evidence": sorted(evidence),
                }
                for (left, right), classifications in sorted(conflict_evidence.items())
                for classification, evidence in sorted(classifications.items())
            ]
            if manifest.get("concurrency_conflicts") != expected_conflicts:
                errors.append(
                    "concurrency_conflicts must exactly match source ownership and resources"
                )

            expected_relationship_counts = {
                "hard-implementation": len(required_hard_edges),
                "ordering-only": len(expected_ordering_constraints),
                "frozen-contract": len(required_frozen_edges),
                "shared-file-conflict": sum(
                    "shared-file-conflict" in classifications
                    for classifications in conflict_evidence.values()
                ),
                "exclusive-resource": sum(
                    "exclusive-resource" in classifications
                    for classifications in conflict_evidence.values()
                ),
            }
            expected_metrics = {
                "task_count": len(source_set - set(completed)),
                "prelude_size": len(prelude),
                "wave_count": len(wave_durations),
                "max_active_lanes": max(active_waves.values(), default=0),
                "source_dag_critical_path": _longest_path_size(
                    remaining_ids, required_hard_edges
                ),
                "scheduled_critical_path": (
                    len(prelude) + sum(wave_durations.values()) + len(epilogue)
                ),
                "relationship_counts": expected_relationship_counts,
            }
            for field, expected in expected_metrics.items():
                if topology_metrics.get(field) != expected:
                    errors.append(f"topology_metrics.{field} must equal {expected}")

        integration_index = {lane_id: index for index, lane_id in enumerate(integration_order)}
        for before, after in sorted(justified_edges):
            before_place = placements.get(before)
            after_place = placements.get(after)
            if not before_place or not after_place:
                continue
            if before_place.get("kind") != "lane" or after_place.get("kind") != "lane":
                continue
            before_lane = str(before_place["lane"])
            after_lane = str(after_place["lane"])
            if before_lane == after_lane:
                continue
            before_wave = int(before_place["wave"])
            after_wave = int(after_place["wave"])
            if before_wave < after_wave and not _lane_depends_transitively(
                lane_by_id, after_lane, before_lane
            ):
                errors.append(
                    f"lane {after_lane} depends_on must include dependency lane {before_lane} "
                    f"for Task {before}->{after}"
                )
            if integration_index.get(before_lane, 10**9) > integration_index.get(after_lane, -1):
                errors.append(
                    f"integration_order must place dependency lane {before_lane} before "
                    f"{after_lane} for Task {before}->{after}"
                )

        # Each lane must have enough file ownership information for safe concurrent writes.
        lane_files: dict[str, set[str]] = {}
        path_display: dict[str, str] = {}
        for lane in lanes:
            lane_id = str(lane.get("id"))
            files: set[str] = set()
            for item in lane.get("owned_files", []):
                key = canonical_path_key(item)
                path_display.setdefault(key, normalize_repo_path(item))
                files.add(key)
            for task_id in lane.get("tasks", []):
                task = task_by_id.get(task_id)
                if task:
                    for item in task.files:
                        key = canonical_path_key(item)
                        path_display.setdefault(key, normalize_repo_path(item))
                        files.add(key)
                    if not task.files and not task.barrier_candidate and not lane.get("owned_files"):
                        errors.append(
                            f"Task {task_id} has no file metadata; repair the plan or declare lane {lane_id} owned_files"
                        )
            lane_files[lane_id] = files

        allowed = manifest.get("allowed_overlaps", [])
        if not isinstance(allowed, list):
            errors.append("allowed_overlaps must be a list")
            allowed = []
        allowed_by_file: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        for index, item in enumerate(allowed):
            if isinstance(item, dict) and isinstance(item.get("file"), str):
                try:
                    normalized = normalize_repo_path(item["file"])
                    key = canonical_path_key(normalized)
                except PlanFormatError as exc:
                    errors.append(f"allowed_overlaps[{index}].file is invalid: {exc}")
                    continue
                path_display.setdefault(key, normalized)
                record_lanes = item.get("lanes")
                if (
                    not isinstance(record_lanes, list)
                    or not record_lanes
                    or any(not isinstance(lane, str) or not lane.strip() for lane in record_lanes)
                ):
                    errors.append(
                        f"allowed_overlaps[{index}].lanes must be a non-empty list of lane IDs"
                    )
                elif len(record_lanes) != len(set(record_lanes)):
                    errors.append(f"allowed_overlaps[{index}].lanes must be unique")
                else:
                    allowed_by_file[key].append((index, item))
            else:
                errors.append(f"allowed_overlaps[{index}] must be an object with file")

        concurrent_surfaces: dict[tuple[int, str], set[str]] = defaultdict(set)
        for lane in lanes:
            lane_id = str(lane.get("id"))
            wave = int(lane.get("wave", 0))
            for key in lane_files.get(lane_id, set()):
                concurrent_surfaces[(wave, key)].add(lane_id)

        used_overlap_records: set[int] = set()
        for (_wave, shared_key), touching_lanes in sorted(concurrent_surfaces.items()):
            if len(touching_lanes) < 2:
                continue
            shared = path_display.get(shared_key, shared_key)
            lane_names = sorted(touching_lanes, key=lambda item: integration_index.get(item, 10**9))
            if _hard_surface(shared):
                errors.append(
                    f"hard shared surface cannot run concurrently: {shared} "
                    f"({', '.join(lane_names)})"
                )
                continue

            records = [
                (index, item)
                for index, item in allowed_by_file.get(shared_key, [])
                if set(item["lanes"]) == touching_lanes
            ]
            if len(records) != 1:
                errors.append(
                    f"worktree overlap {shared} across {', '.join(lane_names)} requires "
                    "exactly one coherent allowed_overlaps record"
                )
                continue

            record_index, record = records[0]
            used_overlap_records.add(record_index)
            if record.get("classification") != "soft":
                errors.append(f"allowed overlap {shared} classification must be soft")
            record_lanes = record.get("lanes", [])
            symbols = record.get("owned_symbols")
            valid_symbols = isinstance(symbols, dict) and set(symbols) == set(record_lanes)
            if valid_symbols:
                for lane_id in record_lanes:
                    owned = symbols.get(lane_id)
                    if (
                        not isinstance(owned, list)
                        or not owned
                        or any(not isinstance(symbol, str) or not symbol.strip() for symbol in owned)
                    ):
                        valid_symbols = False
                        break
            if not valid_symbols:
                errors.append(f"allowed overlap {shared} must name owned_symbols for each lane")
            elif any(
                set(symbols[a]) & set(symbols[b])
                for index, a in enumerate(record_lanes)
                for b in record_lanes[index + 1 :]
            ):
                errors.append(f"allowed overlap {shared} owned_symbols must be disjoint")
            if not str(record.get("integration_owner", "")).strip():
                errors.append(f"allowed overlap {shared} requires integration_owner")
            if not str(record.get("shared_scaffolding_owner", "")).strip():
                errors.append(f"allowed overlap {shared} requires shared_scaffolding_owner")
            merge_order = record.get("merge_order")
            if not isinstance(merge_order, list) or Counter(merge_order) != Counter(record_lanes):
                errors.append(f"allowed overlap {shared} merge_order must contain every overlap lane once")
            elif merge_order != lane_names:
                errors.append(f"allowed overlap {shared} merge_order must match integration_order")
            _as_nonempty_string_list(
                record.get("checks"), f"allowed overlap {shared} checks", errors
            )

        for index, item in enumerate(allowed):
            if isinstance(item, dict) and index not in used_overlap_records:
                errors.append(f"allowed_overlaps[{index}] does not match one concurrent shared surface")

        contracts = _contract_records(manifest, errors)
        for (producer_task, consumer_task), symbols in sorted(contract_symbols.items()):
            producer_place = placements.get(producer_task)
            consumer_place = placements.get(consumer_task)
            if not producer_place or not consumer_place:
                continue
            if producer_place["kind"] == "completed":
                continue
            if producer_place["kind"] == "lane" and consumer_place["kind"] == "lane":
                producer_lane = str(producer_place["lane"])
                consumer_lane = str(consumer_place["lane"])
                if producer_lane == consumer_lane:
                    if producer_place["order"] >= consumer_place["order"]:
                        errors.append(
                            f"lane {producer_lane} executes consumer Task {consumer_task} before producer Task {producer_task}"
                        )
                    continue
                producer_wave = int(producer_place["wave"])
                consumer_wave = int(consumer_place["wave"])
                if producer_wave > consumer_wave:
                    errors.append(
                        f"consumer Task {consumer_task} runs before producer Task {producer_task} across waves"
                    )
                    continue
                if producer_wave == consumer_wave:
                    for symbol in sorted(symbols):
                        contract = _matching_contract(contracts, symbol, producer_lane, consumer_lane)
                        if contract is None:
                            errors.append(
                                f"contract {symbol} crosses concurrent lanes {producer_lane}->{consumer_lane} but is not frozen"
                            )
                        else:
                            exact_signatures = (
                                exact_contract_signatures[(producer_task, consumer_task, symbol)]
                                if critical_path_overlay
                                else None
                            )
                            evidence_files = (
                                {
                                    canonical_path_key(file_path)
                                    for task_id in (producer_task, consumer_task)
                                    for file_path in task_by_id[task_id].files
                                }
                                if critical_path_overlay
                                else None
                            )
                            _validate_contract_record(
                                contract,
                                symbol,
                                errors,
                                exact_signatures,
                                evidence_files,
                            )
                    if integration_index.get(producer_lane, 10**9) > integration_index.get(consumer_lane, -1):
                        errors.append(
                            f"integration_order must merge producer lane {producer_lane} before consumer lane {consumer_lane}"
                        )
            elif producer_place["rank"] > consumer_place["rank"] or (
                producer_place["rank"] == consumer_place["rank"]
                and producer_place.get("order", 0) >= consumer_place.get("order", 0)
            ):
                errors.append(
                    f"consumer Task {consumer_task} is scheduled before producer Task {producer_task}"
                )

        verification = manifest.get("integrated_verification")
        if not isinstance(verification, dict) or verification.get("required") is not True:
            errors.append("integrated_verification.required must be true")
        else:
            commands = _as_nonempty_string_list(
                verification.get("commands"), "integrated verification commands", errors
            )
            if not commands and not any(
                "integrated verification commands" in error for error in errors
            ):
                errors.append("integrated verification commands are required")
        cleanup = manifest.get("cleanup")
        if not isinstance(cleanup, dict):
            errors.append("cleanup policy is required")
        else:
            if cleanup.get("after_merged_verification") is not True:
                errors.append("cleanup.after_merged_verification must be true")
            if cleanup.get("owned_resources_only") is not True:
                errors.append("cleanup.owned_resources_only must be true")

    else:
        errors.append("verdict must be parallel or sequential")

    for resource, task_ids in exclusive_resources:
        for left_index, left_task in enumerate(task_ids):
            left_place = placements.get(left_task)
            if not left_place or left_place.get("kind") != "lane":
                continue
            for right_task in task_ids[left_index + 1 :]:
                right_place = placements.get(right_task)
                if not right_place or right_place.get("kind") != "lane":
                    continue
                if (
                    left_place.get("lane") != right_place.get("lane")
                    and left_place.get("wave") == right_place.get("wave")
                ):
                    errors.append(
                        f"exclusive resource {resource} is used concurrently by "
                        f"Task {left_task} and Task {right_task}"
                    )

    counts = Counter(assigned)
    for task_id, count in sorted(counts.items()):
        if count > 1:
            errors.append(f"duplicate task {task_id} in execution overlay")
    unknown = sorted(set(counts) - source_set)
    if unknown:
        errors.append("unknown tasks: " + ", ".join(map(str, unknown)))
    missing = sorted(source_set - set(counts))
    if missing:
        errors.append("missing tasks: " + ", ".join(map(str, missing)))

    # Hard dependencies must be respected by the final placement graph.
    for before, after in sorted(hard_edges):
        before_place = placements.get(before)
        after_place = placements.get(after)
        if not before_place or not after_place:
            continue
        if before_place["kind"] == "completed":
            continue
        if before_place["kind"] == "lane" and after_place["kind"] == "lane":
            if before_place["lane"] == after_place["lane"]:
                if before_place["order"] >= after_place["order"]:
                    errors.append(f"hard dependency Task {before}->{after} is reversed inside lane {before_place['lane']}")
            elif before_place["wave"] >= after_place["wave"]:
                errors.append(f"hard dependency Task {before}->{after} must cross to a later wave")
        elif before_place["rank"] > after_place["rank"] or (
            before_place["rank"] == after_place["rank"]
            and before_place.get("order", 0) >= after_place.get("order", 0)
        ):
            errors.append(f"hard dependency Task {before}->{after} is scheduled in the wrong order")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_plan", type=Path)
    parser.add_argument("overlay", type=Path)
    parser.add_argument(
        "--git-executable",
        type=Path,
        help="Trusted absolute Git executable. PATH and the project directory are never searched.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    errors = validate(args.source_plan, args.overlay, args.git_executable)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "valid": not errors,
                    "source_plan": str(args.source_plan.resolve()),
                    "overlay": str(args.overlay.resolve()),
                    "diagnostics": [
                        {"code": diagnostic_code(error), "message": error} for error in errors
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if errors else 0
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("VALID: execution overlay is structurally consistent with the source plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
