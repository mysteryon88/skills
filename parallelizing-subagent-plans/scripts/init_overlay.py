#!/usr/bin/env python3
"""Create and validate a conservative execution overlay from explicit plan metadata."""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from plan_model import canonical_path_key, interface_symbols, parse_plan
from validate_parallel_plan import (
    PARALLEL_EXECUTOR,
    SEQUENTIAL_EXECUTOR,
    resolve_git_executable,
    validate,
)


REVIEW_POLICY = {
    "per_task": True,
    "per_lane": True,
    "spec_and_quality": True,
    "max_fix_rounds": 5,
    "scoped_rereview_each_round": True,
    "final_whole_branch": True,
    "final_fix_waves": 1,
}
TEST_EVIDENCE_RE = re.compile(r"(^|/)(tests?|fixtures?|mocks?)(/|$)|(^|[._-])test([._-]|$)")
TEST_COMMAND_RE = re.compile(r"\b(?:test|tests|pytest|unittest|vitest|jest)\b")


class OverlayInitError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _lexical_git_root(source: Path) -> Path | None:
    for directory in (source.resolve().parent, *source.resolve().parents[1:]):
        if os.path.lexists(directory / ".git"):
            return directory
    return None


def _repo_relative_source(source: Path, git_executable: Path | None) -> str:
    source = source.resolve()
    lexical_root = _lexical_git_root(source)
    if git_executable is None:
        if lexical_root is not None:
            raise OverlayInitError(
                "GIT_EXECUTABLE_REQUIRED",
                "source plan is inside a Git repository; pass a trusted absolute --git-executable",
            )
        return source.name
    try:
        result = subprocess.run(
            [str(git_executable), "-C", str(source.parent), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if lexical_root is not None:
            raise OverlayInitError(
                "GIT_REPOSITORY_IDENTITY_UNVERIFIED",
                f"cannot verify repository-relative source identity: {exc}",
            ) from exc
        return source.name
    if result.returncode == 0 and result.stdout.strip():
        try:
            return source.relative_to(Path(result.stdout.strip()).resolve()).as_posix()
        except ValueError:
            if lexical_root is not None:
                raise OverlayInitError(
                    "GIT_REPOSITORY_IDENTITY_UNVERIFIED",
                    "Git repository root does not contain the source plan",
                )
    if lexical_root is not None:
        raise OverlayInitError(
            "GIT_REPOSITORY_IDENTITY_UNVERIFIED",
            "Git rev-parse did not return a repository root for the source plan",
        )
    return source.name


def _load_list(path: Path | None, field: str) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OverlayInitError("INPUT_JSON_INVALID", f"cannot read {field}: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise OverlayInitError("INPUT_JSON_INVALID", f"{field} must be a JSON array of objects")
    return value


def _ordering_edges(plan, task_ids: set[int]) -> set[tuple[int, int]]:
    edges = {
        (dependency, task.task_id)
        for task in plan.tasks
        if task.task_id in task_ids
        for dependency in task.depends_on_tasks
        if dependency in task_ids
    }
    producers: dict[str, list[int]] = defaultdict(list)
    consumers: dict[str, list[int]] = defaultdict(list)
    for task in plan.tasks:
        if task.task_id not in task_ids:
            continue
        for symbol in interface_symbols(task.produces):
            producers[symbol].append(task.task_id)
        for symbol in interface_symbols(task.consumes):
            consumers[symbol].append(task.task_id)
    for symbol in set(producers) & set(consumers):
        edges.update(
            (producer, consumer)
            for producer in producers[symbol]
            for consumer in consumers[symbol]
            if producer != consumer
        )
    return edges


def _quoted_signatures(lines: list[str]) -> set[str]:
    return {
        match.strip()
        for line in lines
        for match in re.findall(r"`([^`]+)`", line)
        if match.strip()
    }


def _is_pure_frozen_reference(line: str, producer: int, signatures: set[str]) -> bool:
    if producer not in {
        int(value) for value in re.findall(r"\bTask\s+(\d+)\b", line, re.IGNORECASE)
    }:
        return True
    quoted = _quoted_signatures([line])
    if not quoted or not quoted.issubset(signatures):
        return False
    remainder = re.sub(r"^[\s-]*Consumes\s*:\s*", "", line, flags=re.IGNORECASE)
    remainder = re.sub(r"`[^`]+`", "", remainder)
    remainder = re.sub(
        r"\b(?:from\s+)?Task\s+\d+\b", "", remainder, flags=re.IGNORECASE
    )
    return not re.sub(r"[\s.,;:()\-]+", "", remainder)


def _frozen_contract_edges(
    plan,
    task_ids: set[int],
    checks: list[str],
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    if not any(TEST_COMMAND_RE.search(check.casefold()) for check in checks):
        return {}
    task_by_id = {task.task_id: task for task in plan.tasks}
    producers: dict[str, list[int]] = defaultdict(list)
    consumers: dict[str, list[int]] = defaultdict(list)
    for task_id in task_ids:
        task = task_by_id[task_id]
        for signature in _quoted_signatures(task.produces):
            producers[signature].append(task_id)
        for signature in _quoted_signatures(task.consumes):
            consumers[signature].append(task_id)

    frozen: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for signature in sorted(set(producers) & set(consumers)):
        symbol = next(iter(interface_symbols([f"`{signature}`"])), "")
        if not symbol:
            continue
        for producer in producers[signature]:
            for consumer in consumers[signature]:
                if producer == consumer:
                    continue
                evidence_files = sorted(
                    {
                        file_path
                        for task_id in (producer, consumer)
                        for file_path in task_by_id[task_id].files
                        if TEST_EVIDENCE_RE.search(canonical_path_key(file_path))
                    }
                )
                if evidence_files:
                    frozen[(producer, consumer)].append(
                        {
                            "name": symbol,
                            "signature": signature,
                            "evidence_files": evidence_files,
                        }
                    )
    for (producer, consumer), records in list(frozen.items()):
        signatures = {record["signature"] for record in records}
        referenced_lines = [
            line
            for line in task_by_id[consumer].consumes
            if producer
            in {
                int(value)
                for value in re.findall(r"\bTask\s+(\d+)\b", line, re.IGNORECASE)
            }
        ]
        if referenced_lines and not all(
            _is_pure_frozen_reference(line, producer, signatures)
            for line in referenced_lines
        ):
            del frozen[(producer, consumer)]
    return frozen


def _topological_order(plan, task_ids: set[int]) -> list[int]:
    source_order = {task.task_id: index for index, task in enumerate(plan.tasks)}
    edges = _ordering_edges(plan, task_ids)
    children: dict[int, set[int]] = defaultdict(set)
    indegree = {task_id: 0 for task_id in task_ids}
    for before, after in edges:
        if after not in children[before]:
            children[before].add(after)
            indegree[after] += 1
    ready = sorted(
        (task_id for task_id, degree in indegree.items() if degree == 0),
        key=source_order.__getitem__,
    )
    result: list[int] = []
    while ready:
        task_id = ready.pop(0)
        result.append(task_id)
        for child in sorted(children.get(task_id, set()), key=source_order.__getitem__):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=source_order.__getitem__)
    if len(result) != len(task_ids):
        raise OverlayInitError(
            "TASK_DEPENDENCY_CYCLE", "explicit Task and contract dependencies contain a cycle"
        )
    return result


def _dependency_graph(
    plan,
    task_ids: set[int],
    edges: set[tuple[int, int]],
) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    children = {task_id: set() for task_id in task_ids}
    parents = {task_id: set() for task_id in task_ids}
    for before, after in edges:
        children[before].add(after)
        parents[after].add(before)
    return children, parents


def _descendants(starts: set[int], children: dict[int, set[int]]) -> set[int]:
    result = set(starts)
    stack = list(starts)
    while stack:
        current = stack.pop()
        for child in children.get(current, set()):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


def _critical_ranks(
    plan,
    task_ids: set[int],
    children: dict[int, set[int]],
) -> dict[int, int]:
    ranks: dict[int, int] = {}
    for task_id in reversed(_topological_order(plan, task_ids)):
        ranks[task_id] = 1 + max(
            (ranks[child] for child in children.get(task_id, set())),
            default=0,
        )
    return ranks


def _concurrency_conflicts(
    plan,
    task_ids: set[int],
    global_constraints: list[dict[str, Any]],
) -> dict[tuple[int, int], list[dict[str, str]]]:
    conflicts: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    task_by_id = {task.task_id: task for task in plan.tasks}
    file_owners: dict[str, list[int]] = defaultdict(list)
    for task_id in task_ids:
        for file_path in task_by_id[task_id].files:
            file_owners[canonical_path_key(file_path)].append(task_id)
    for file_path, owners in file_owners.items():
        for left, right in combinations(sorted(set(owners)), 2):
            conflicts[(left, right)].append(
                {
                    "classification": "shared-file-conflict",
                    "evidence": f"shared file `{file_path}`",
                }
            )

    for constraint in global_constraints:
        if constraint.get("kind") != "exclusive-resource":
            continue
        affected = sorted(
            {
                task_id
                for task_id in constraint.get("tasks", [])
                if type(task_id) is int and task_id in task_ids
            }
        )
        resource = str(constraint.get("resource", "exclusive resource")).strip()
        for left, right in combinations(affected, 2):
            conflicts[(left, right)].append(
                {
                    "classification": "exclusive-resource",
                    "evidence": f"exclusive resource `{resource}`",
                }
            )
    return conflicts


def _select_wave(
    ready: list[int],
    ranks: dict[int, int],
    source_order: dict[int, int],
    conflicts: dict[tuple[int, int], list[dict[str, str]]],
    contract_edges: set[tuple[int, int]],
    active: set[int],
    minimum_size: int,
) -> list[int]:
    candidates: list[tuple[int, ...]] = []
    for size in range(min(4, len(ready)), minimum_size - 1, -1):
        candidates.extend(
            group
            for group in combinations(ready, size)
            if all(tuple(sorted(pair)) not in conflicts for pair in combinations(group, 2))
            and all(
                consumer not in group or producer not in active or producer in group
                for producer, consumer in contract_edges
            )
        )
    if not candidates:
        return []

    def score(group: tuple[int, ...]) -> tuple[Any, ...]:
        ranked = sorted((ranks[task_id] for task_id in group), reverse=True)
        return (
            tuple(ranked + [-1] * (4 - len(ranked))),
            len(group),
            tuple(-source_order[task_id] for task_id in group),
        )

    return list(max(candidates, key=score))


def _prelude_record(
    task_id: int,
    ready: list[int],
    children: dict[int, set[int]],
    parents: dict[int, set[int]],
    active: set[int],
    conflicts: dict[tuple[int, int], list[dict[str, str]]],
) -> dict[str, Any]:
    conflict_records = [
        record
        for other in ready
        if other != task_id
        for record in conflicts.get(tuple(sorted((task_id, other))), [])
    ]
    if conflict_records:
        classification = (
            "exclusive-resource"
            if any(record["classification"] == "exclusive-resource" for record in conflict_records)
            else "shared-file-conflict"
        )
        evidence = sorted({record["evidence"] for record in conflict_records})
        reason = "No two dependency-ready Tasks can run concurrently until this conflict clears."
    else:
        successors = sorted(
            successor
            for successor in children.get(task_id, set())
            if not ((parents[successor] & active) - {task_id})
        )
        classification = "hard-implementation"
        evidence = [
            "unlocks " + ", ".join(f"Task {successor}" for successor in successors)
            if successors
            else "only dependency-ready Task"
        ]
        reason = "No second Task is dependency-ready before this Task completes."
    return {
        "task": task_id,
        "classification": classification,
        "reason": reason,
        "evidence": evidence,
    }


def _critical_path_schedule(
    plan,
    task_ids: set[int],
    global_constraints: list[dict[str, Any]],
    checks: list[str],
) -> tuple[
    list[int],
    list[list[int]],
    list[int],
    list[dict[str, Any]],
    dict[str, int],
    dict[tuple[int, int], list[dict[str, Any]]],
]:
    """Schedule the hard DAG in bounded waves; conflicts apply only within a wave."""
    if not task_ids:
        return [], [], [], [], {"source_dag_critical_path": 0, "scheduled_critical_path": 0}, {}
    all_edges = _ordering_edges(plan, task_ids)
    frozen_contracts = _frozen_contract_edges(plan, task_ids, checks)
    contract_edges = set(frozen_contracts)
    edges = all_edges - contract_edges
    children, parents = _dependency_graph(plan, task_ids, edges)
    all_children, _ = _dependency_graph(plan, task_ids, all_edges)
    ranks = _critical_ranks(plan, task_ids, children)
    source_order = {task.task_id: index for index, task in enumerate(plan.tasks)}
    conflicts = _concurrency_conflicts(plan, task_ids, global_constraints)

    explicit_epilogue = {
        task.task_id
        for task in plan.tasks
        if task.task_id in task_ids and task.barrier_candidate
    }
    epilogue_ids = _descendants(explicit_epilogue, all_children)
    active = set(task_ids) - epilogue_ids
    prelude: list[int] = []
    prelude_evidence: list[dict[str, Any]] = []
    waves: list[list[int]] = []
    parallel_started = False

    while active:
        ready = sorted(
            (task_id for task_id in active if not (parents[task_id] & active)),
            key=source_order.__getitem__,
        )
        if not ready:
            raise OverlayInitError(
                "TASK_DEPENDENCY_CYCLE", "explicit Task and contract dependencies contain a cycle"
            )
        selected = _select_wave(
            ready,
            ranks,
            source_order,
            conflicts,
            contract_edges,
            active,
            1 if parallel_started else 2,
        )
        if not selected:
            selected = _select_wave(
                ready, ranks, source_order, conflicts, contract_edges, active, 1
            )
            task_id = selected[0]
            prelude.append(task_id)
            prelude_evidence.append(
                _prelude_record(task_id, ready, children, parents, active, conflicts)
            )
            active.remove(task_id)
            continue
        parallel_started = True
        waves.append(selected)
        active.difference_update(selected)

    epilogue = _topological_order(plan, epilogue_ids) if epilogue_ids else []
    metrics = {
        "source_dag_critical_path": max(ranks.values(), default=0),
        "scheduled_critical_path": len(prelude) + len(waves) + len(epilogue),
    }
    return prelude, waves, epilogue, prelude_evidence, metrics, frozen_contracts


def _compact_wave_chains(
    waves: list[list[int]],
    hard_edges: set[tuple[int, int]],
    conflicts: dict[tuple[int, int], list[dict[str, str]]],
) -> list[list[list[int]]]:
    """Keep dependent steps with their owner without adding cross-lane barriers."""
    parents: dict[int, set[int]] = defaultdict(set)
    for before, after in hard_edges:
        parents[after].add(before)
    packed: list[list[list[int]]] = []
    for wave in waves:
        if packed:
            previous = packed[-1]
            owners = {task: index for index, lane in enumerate(previous) for task in lane}
            extensions: dict[int, int] = {}
            for task in wave:
                parent_owners = {owners[parent] for parent in parents[task] if parent in owners}
                if len(parent_owners) != 1:
                    break
                owner = next(iter(parent_owners))
                if owner in extensions:
                    break
                extensions[owner] = task
            else:
                candidate = [
                    lane + ([extensions[index]] if index in extensions else [])
                    for index, lane in enumerate(previous)
                ]
                if all(
                    tuple(sorted((left, right))) not in conflicts
                    for left_lane, right_lane in combinations(candidate, 2)
                    for left in left_lane
                    for right in right_lane
                ):
                    packed[-1] = candidate
                    continue
        packed.append([[task] for task in wave])
    return packed


def _repair_suggestions(
    plan,
    waves: list[list[int]],
    hard_edges: set[tuple[int, int]],
    checks: list[str],
) -> list[dict[str, Any]]:
    task_by_id = {task.task_id: task for task in plan.tasks}
    successors: dict[int, set[int]] = defaultdict(set)
    for before, after in hard_edges:
        successors[before].add(after)
    suggestions: list[dict[str, Any]] = []
    for wave in waves:
        if len(wave) != 1:
            continue
        task_id = wave[0]
        task = task_by_id[task_id]
        blocked = sorted(successors.get(task_id, set()))
        if len(task.files) < 8 or len(blocked) < 2:
            continue
        test_files = [
            path for path in task.files if TEST_EVIDENCE_RE.search(canonical_path_key(path))
        ]
        write_files = [path for path in task.files if path not in test_files]
        if len(write_files) < 2 or len(test_files) < 2:
            continue
        suggestions.append(
            {
                "task": task_id,
                "blocked_successors": blocked,
                "write_files": write_files,
                "test_files": test_files,
                "draft_owner": "coordinator",
                "required_split_count": 2,
                "required_split": {
                    "outcomes": "Draft two independently testable outcomes from repository evidence.",
                    "file_ownership": "Assign every write file to exactly one replacement Task.",
                    "interfaces": "Name every produced and consumed interface for each replacement Task.",
                    "test_ownership": "Assign explicit tests or fixtures to each replacement Task.",
                    "checks": checks,
                    "commit_boundaries": 2,
                    "mapping": f"Map each replacement to source Task {task_id}.",
                },
                "mapping_requirement": (
                    f"Both replacements must map back to source Task {task_id} without changing its outcome."
                ),
                "approval_required": True,
                "status": "coordinator-draft-and-human-approval-required",
            }
        )
    return suggestions


def build_manifest(
    source: Path,
    isolation: str,
    checks: list[str],
    global_constraints: list[dict[str, Any]],
    completed_tasks: list[dict[str, Any]],
    git_executable: Path | None = None,
) -> tuple[dict[str, Any], str]:
    plan = parse_plan(source)
    if plan.global_constraints and not global_constraints:
        raise OverlayInitError(
            "GLOBAL_CONSTRAINT_MAPPING_REQUIRED",
            "source plan has Global Constraints; provide --constraint-map",
        )
    completed_ids = {
        item.get("task") for item in completed_tasks if type(item.get("task")) is int
    }
    checked_ids = {task.task_id for task in plan.tasks if task.completed}
    if checked_ids != completed_ids:
        raise OverlayInitError(
            "COMPLETION_EVIDENCE_REQUIRED",
            "checked source Tasks must match --completed-tasks evidence exactly",
        )

    remaining = [task for task in plan.tasks if task.task_id not in completed_ids]
    remaining_ids = {task.task_id for task in remaining}
    (
        prelude,
        waves,
        epilogue,
        prelude_evidence,
        topology,
        frozen_contracts,
    ) = _critical_path_schedule(plan, remaining_ids, global_constraints, checks)
    ordering_edges = _ordering_edges(plan, remaining_ids)
    can_parallel = (
        isolation == "worktree"
        and any(len(wave) >= 2 for wave in waves)
    )
    explicit_edges = {
        (dependency, task.task_id)
        for task in plan.tasks
        for dependency in task.depends_on_tasks
    }
    task_dependencies = [
        {
            "before": before,
            "after": after,
            "classification": (
                "frozen-contract" if (before, after) in frozen_contracts else "hard-implementation"
            ),
            "reason": (
                f"Task {after} explicitly consumes work from Task {before}"
                if (before, after) in explicit_edges
                else f"Task {after} consumes an interface produced by Task {before}"
            ),
        }
        for before, after in sorted(ordering_edges)
    ]
    ordering_constraints = [
        {
            "constraint": record.get("constraint"),
            "tasks": record.get("tasks", []),
            "checks": record.get("checks", []),
            "classification": "ordering-only",
        }
        for record in global_constraints
        if record.get("kind") == "ordering"
    ]
    common = {
        "schema_version": 2,
        "source_plan": _repo_relative_source(source, git_executable),
        "source_sha256": plan.sha256,
        "completed_tasks": completed_tasks,
        "global_constraints": global_constraints,
        "task_dependencies": task_dependencies,
        "ordering_constraints": ordering_constraints,
        "review_policy": dict(REVIEW_POLICY),
    }

    if not can_parallel:
        reason = (
            "Worktree isolation is unavailable or unverified."
            if isolation != "worktree"
            else "Explicit constraints or the dependency graph leave fewer than two safe lanes."
        )
        return (
            {
                **common,
                "verdict": "sequential",
                "executor": SEQUENTIAL_EXECUTOR,
                "approval_required": False,
                "continue_without_confirmation": True,
                "reason": reason,
                "sequential_tasks": _topological_order(plan, remaining_ids),
            },
            reason,
        )

    if not checks:
        raise OverlayInitError(
            "INTEGRATED_CHECK_REQUIRED",
            "a parallel overlay requires at least one --check command",
        )
    task_by_id = {task.task_id: task for task in plan.tasks}
    hard_edges = ordering_edges - set(frozen_contracts)
    conflict_records = _concurrency_conflicts(plan, remaining_ids, global_constraints)
    packed_waves = (
        [[[task] for task in wave] for wave in waves]
        if frozen_contracts
        else _compact_wave_chains(waves, hard_edges, conflict_records)
    )
    lane_id_by_task = {
        task_id: f"wave-{wave_index}-task-{chain[0]}"
        for wave_index, wave in enumerate(packed_waves, start=1)
        for chain in wave
        for task_id in chain
    }
    parents: dict[int, set[int]] = defaultdict(set)
    for before, after in ordering_edges - set(frozen_contracts):
        parents[after].add(before)
    lanes = [
        {
            "id": lane_id_by_task[chain[0]],
            "wave": wave_index,
            "tasks": chain,
            "depends_on": sorted(
                {
                    lane_id_by_task[parent]
                    for task_id in chain
                    for parent in parents.get(task_id, set())
                    if parent in lane_id_by_task and parent not in chain
                }
            ),
            "owned_files": sorted({path for task_id in chain for path in task_by_id[task_id].files}),
        }
        for wave_index, wave in enumerate(packed_waves, start=1)
        for chain in wave
    ]
    topology_metrics = {
        "scheduler": "critical-path-v1",
        "task_count": len(remaining_ids),
        "prelude_size": len(prelude),
        "wave_count": len(packed_waves),
        "max_active_lanes": max((len(wave) for wave in packed_waves), default=0),
        **topology,
        "scheduled_critical_path": len(prelude) + sum(
            max(len(chain) for chain in wave) for wave in packed_waves
        ) + len(epilogue),
    }
    concurrency_conflicts = [
        {
            "tasks": [left, right],
            "classification": classification,
            "evidence": sorted(
                {
                    record["evidence"]
                    for record in records
                    if record["classification"] == classification
                }
            ),
        }
        for (left, right), records in sorted(conflict_records.items())
        for classification in sorted({record["classification"] for record in records})
    ]
    topology_metrics["relationship_counts"] = {
        "hard-implementation": len(hard_edges),
        "ordering-only": len(ordering_constraints),
        "frozen-contract": len(frozen_contracts),
        "shared-file-conflict": sum(
            record["classification"] == "shared-file-conflict"
            for record in concurrency_conflicts
        ),
        "exclusive-resource": sum(
            record["classification"] == "exclusive-resource"
            for record in concurrency_conflicts
        ),
    }
    lane_wave_by_task = {
        task_id: wave_index
        for wave_index, wave in enumerate(packed_waves, start=1)
        for chain in wave
        for task_id in chain
    }
    contracts = [
        {
            **contract,
            "producer_lane": lane_id_by_task[producer],
            "consumer_lanes": [lane_id_by_task[consumer]],
            "frozen_before_parallel": True,
            "contract_tests": checks,
        }
        for (producer, consumer), records in sorted(frozen_contracts.items())
        if producer in lane_id_by_task
        and consumer in lane_id_by_task
        and lane_wave_by_task[producer] == lane_wave_by_task[consumer]
        for contract in records
    ]
    reason = (
        f"Scheduled {len(remaining_ids)} Tasks in {len(lanes)} lanes across {len(packed_waves)} bounded waves "
        f"after a {len(prelude)}-Task dependency prelude."
    )
    return (
        {
            **common,
            "verdict": "parallel",
            "executor": PARALLEL_EXECUTOR,
            "approval_required": True,
            "continue_without_confirmation": False,
            "isolation": "worktree",
            "prelude_tasks": prelude,
            "prelude_evidence": prelude_evidence,
            "lanes": lanes,
            "epilogue_tasks": epilogue,
            "allowed_overlaps": [],
            "contracts": contracts,
            "integration_order": [lane["id"] for lane in lanes],
            "topology_metrics": topology_metrics,
            "concurrency_conflicts": concurrency_conflicts,
            "repair_suggestions": _repair_suggestions(plan, waves, hard_edges, checks),
            "integrated_verification": {"required": True, "commands": checks},
            "cleanup": {"after_merged_verification": True, "owned_resources_only": True},
        },
        reason,
    )


def render_overlay(source: Path, manifest: dict[str, Any], reason: str) -> str:
    verdict = str(manifest["verdict"]).upper()
    return (
        f"# {source.stem} Execution Overlay\n\n"
        f"**Source plan:** `{manifest['source_plan']}` at SHA-256 `{manifest['source_sha256']}`\n"
        f"**Verdict:** `{verdict}`\n"
        f"**Reason:** {reason}\n\n"
        "<!-- parallel-execution-manifest\n"
        + json.dumps(manifest, ensure_ascii=False, indent=2)
        + "\nparallel-execution-manifest -->\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--isolation", choices=("worktree", "unavailable", "unknown"), default="unknown")
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--constraint-map", type=Path)
    parser.add_argument("--completed-tasks", type=Path)
    parser.add_argument(
        "--git-executable",
        type=Path,
        help="Trusted absolute Git executable. PATH and the project directory are never searched.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    source = args.source_plan.expanduser().resolve()
    output = args.output.expanduser().resolve()
    input_paths = {source}
    input_paths.update(
        path.expanduser().resolve()
        for path in (args.constraint_map, args.completed_tasks)
        if path is not None
    )
    if output in input_paths:
        print(
            "ERROR OUTPUT_INPUT_CONFLICT: output must not replace the source plan or a JSON input",
            file=sys.stderr,
        )
        return 2
    if output.exists() and not args.force:
        print("ERROR OUTPUT_EXISTS: output already exists; pass --force to replace it", file=sys.stderr)
        return 2
    try:
        git_executable = resolve_git_executable(args.git_executable)
        constraints = _load_list(args.constraint_map, "constraint map")
        completed = _load_list(args.completed_tasks, "completed tasks")
        manifest, reason = build_manifest(
            source,
            args.isolation,
            args.check,
            constraints,
            completed,
            git_executable,
        )
        rendered = render_overlay(source, manifest, reason)
    except (OSError, UnicodeError, ValueError) as exc:
        code = exc.code if isinstance(exc, OverlayInitError) else "OVERLAY_INIT_FAILED"
        print(f"ERROR {code}: {exc}", file=sys.stderr)
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        temp_path.write_text(rendered, encoding="utf-8", newline="\n")
        validation_errors = validate(source, temp_path, git_executable)
        if validation_errors:
            raise OverlayInitError(
                "GENERATED_OVERLAY_INVALID", "; ".join(validation_errors)
            )
        os.replace(temp_path, output)
    except Exception as exc:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        code = exc.code if isinstance(exc, OverlayInitError) else "OVERLAY_WRITE_FAILED"
        print(f"ERROR {code}: {exc}", file=sys.stderr)
        return 2

    report = {
        "schema_version": 1,
        "source_plan": str(source),
        "output": str(output),
        "verdict": manifest["verdict"],
        "lane_count": len(manifest.get("lanes", [])),
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {manifest['verdict'].upper()} overlay to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
