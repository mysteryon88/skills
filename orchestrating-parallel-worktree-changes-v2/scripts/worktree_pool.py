#!/usr/bin/env python3
"""Create and safely clean a pool of Git worktrees for parallel agent lanes.

The script deliberately does not merge branches, force-delete branches, or
remove dirty/unmerged worktrees. Integration remains the coordinator's job.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = 1
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
CLEANUP_STATUSES = {"pending", "removing", "removed"}


class WorktreePoolError(RuntimeError):
    """Expected, actionable failure."""


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class WorktreeRegistration:
    path: Path
    locked: bool
    prunable: bool


def _run(command: Sequence[str], *, cwd: Path, check: bool = True) -> GitResult:
    try:
        process = subprocess.run(
            list(command),
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise WorktreePoolError(f"Cannot run {' '.join(command)}: {error}") from error
    result = GitResult(process.returncode, process.stdout.strip(), process.stderr.strip())
    if check and result.returncode != 0:
        detail = result.stderr or result.stdout or "unknown Git error"
        raise WorktreePoolError(f"Command failed: {' '.join(command)}\n{detail}")
    return result


def _git(repo: Path, *args: str, check: bool = True) -> GitResult:
    return _run(("git", "-C", str(repo), *args), cwd=repo, check=check)


def _repo_root(repo: Path) -> Path:
    candidate = repo.expanduser().resolve()
    result = _run(("git", "-C", str(candidate), "rev-parse", "--show-toplevel"), cwd=candidate)
    return Path(result.stdout).resolve()


def _common_dir(root: Path) -> Path:
    value = _git(root, "rev-parse", "--git-common-dir").stdout
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _state_path(root: Path, run_id: str) -> Path:
    return _common_dir(root) / "parallel-orchestrator" / f"{run_id}.json"


def _validate_identifier(value: str, label: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise WorktreePoolError(
            f"Invalid {label} {value!r}. Use 1-80 ASCII letters, numbers, dots, "
            "underscores, or hyphens; start with a letter or number."
        )
    return value


def _assert_clean(root: Path) -> None:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if status:
        raise WorktreePoolError(
            "Repository has uncommitted or untracked changes. Preserve or commit them "
            "before creating parallel worktrees."
        )


def _assert_worktree_root_ignored(root: Path) -> None:
    probe = ".worktrees/__parallel_orchestrator_probe__"
    result = _git(root, "check-ignore", "-q", "--", probe, check=False)
    if result.returncode != 0:
        raise WorktreePoolError(
            ".worktrees/ is not ignored. Add '.worktrees/' to .gitignore and commit "
            "that setup change, or use a native worktree tool."
        )


def _branch_exists(root: Path, branch: str) -> bool:
    result = _git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    return result.returncode == 0


def _assert_valid_branch(root: Path, branch: str) -> None:
    result = _git(root, "check-ref-format", "--branch", branch, check=False)
    if result.returncode != 0:
        raise WorktreePoolError(f"Generated branch name is invalid: {branch}")


def _resolve_commit(root: Path, ref: str) -> str:
    return _git(root, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").stdout


def _current_branch(root: Path) -> str | None:
    result = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    return result.stdout if result.returncode == 0 and result.stdout else None


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_state_ownership(root: Path, run_id: str, state: dict[str, Any]) -> None:
    expected_common = _common_dir(root)
    expected_run_root = (root / ".worktrees" / "parallel" / run_id).resolve()
    if state.get("run_id") != run_id:
        raise WorktreePoolError("Invalid state ownership: run id mismatch")
    git_common_dir = state.get("git_common_dir")
    if not isinstance(git_common_dir, str) or not git_common_dir:
        raise WorktreePoolError("Invalid state ownership: Git common directory is missing or invalid")
    if Path(git_common_dir).resolve() != expected_common:
        raise WorktreePoolError("Invalid state ownership: Git common directory mismatch")
    worktree_root = state.get("worktree_root")
    if not isinstance(worktree_root, str) or not worktree_root:
        raise WorktreePoolError("Invalid state ownership: worktree root is missing or invalid")
    if Path(worktree_root).resolve() != expected_run_root:
        raise WorktreePoolError("Invalid state ownership: worktree root mismatch")

    integration = state.get("integration")
    lanes = state.get("lanes")
    if not isinstance(integration, dict) or not isinstance(lanes, list):
        raise WorktreePoolError("Invalid state ownership: missing integration or lane records")

    expected_integration_branch = f"parallel/{run_id}/integration"
    expected_integration_path = (expected_run_root / "integration").resolve()
    if integration.get("name") != "integration":
        raise WorktreePoolError("Invalid state ownership: integration name mismatch")
    if integration.get("branch") != expected_integration_branch:
        raise WorktreePoolError("Invalid state ownership: integration branch mismatch")
    raw_integration_path = integration.get("path")
    if not isinstance(raw_integration_path, str) or Path(raw_integration_path).resolve() != expected_integration_path:
        raise WorktreePoolError("Invalid state ownership: integration path mismatch")

    names: set[str] = set()
    branches: set[str] = {expected_integration_branch}
    paths: set[Path] = {expected_integration_path}
    for entry in lanes:
        if not isinstance(entry, dict):
            raise WorktreePoolError("Invalid state ownership: malformed lane entry")
        name = entry.get("name")
        branch = entry.get("branch")
        raw_path = entry.get("path")
        if not isinstance(name, str):
            raise WorktreePoolError("Invalid state ownership: lane name is missing")
        _validate_identifier(name, "lane name")
        normalized_name = name.casefold()
        if normalized_name == "integration" or normalized_name in names:
            raise WorktreePoolError("Invalid state ownership: duplicate or reserved lane name")
        expected_branch = f"parallel/{run_id}/{name}"
        expected_path = (expected_run_root / "lanes" / name).resolve()
        if branch != expected_branch:
            raise WorktreePoolError("Invalid state ownership: lane branch mismatch")
        if not isinstance(raw_path, str) or Path(raw_path).resolve() != expected_path:
            raise WorktreePoolError("Invalid state ownership: lane path mismatch")
        if expected_branch in branches or expected_path in paths:
            raise WorktreePoolError("Invalid state ownership: duplicate branch or path")
        names.add(normalized_name)
        branches.add(expected_branch)
        paths.add(expected_path)

    cleanup = state.get("cleanup_journal")
    if cleanup is not None:
        if not isinstance(cleanup, dict):
            raise WorktreePoolError("Invalid state ownership: cleanup journal must be an object")
        if not isinstance(cleanup.get("merged_into"), str) or not cleanup["merged_into"]:
            raise WorktreePoolError("Invalid state ownership: cleanup destination is missing")
        if not isinstance(cleanup.get("merged_commit"), str) or not cleanup["merged_commit"]:
            raise WorktreePoolError("Invalid state ownership: cleanup destination commit is missing")
        operations = cleanup.get("operations")
        if not isinstance(operations, list):
            raise WorktreePoolError("Invalid state ownership: cleanup operations must be a list")
        expected_operations = [
            {"kind": "worktree", "branch": entry["branch"], "path": entry["path"]}
            for entry in [*lanes, integration]
        ] + [
            {"kind": "branch", "branch": entry["branch"], "path": entry["path"]}
            for entry in [*lanes, integration]
        ]
        if len(operations) != len(expected_operations):
            raise WorktreePoolError("Invalid state ownership: cleanup operation count mismatch")
        for index, (operation, expected) in enumerate(zip(operations, expected_operations)):
            if not isinstance(operation, dict):
                raise WorktreePoolError("Invalid state ownership: malformed cleanup operation")
            if any(operation.get(key) != value for key, value in expected.items()):
                raise WorktreePoolError(
                    f"Invalid state ownership: cleanup operation {index} targets an unexpected resource"
                )
            if operation.get("status") not in CLEANUP_STATUSES:
                raise WorktreePoolError(
                    f"Invalid state ownership: cleanup operation {index} has an invalid status"
                )


def _load_state(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    run_id = _validate_identifier(run_id, "run id")
    path = _state_path(root, run_id)
    if not path.is_file():
        raise WorktreePoolError(f"No worktree-pool state found for run {run_id!r}: {path}")
    try:
        state = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise WorktreePoolError(f"Cannot read state file {path}: {error}") from error
    if not isinstance(state, dict):
        raise WorktreePoolError(f"Cannot read state file {path}: state must be a JSON object")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise WorktreePoolError(f"Unsupported state schema in {path}")
    repo_root = state.get("repo_root")
    if not isinstance(repo_root, str) or not repo_root:
        raise WorktreePoolError(f"Cannot read state file {path}: repository root is missing or invalid")
    if Path(repo_root).resolve() != root:
        raise WorktreePoolError(f"State file belongs to another repository: {repo_root}")
    _validate_state_ownership(root, run_id, state)
    return path, state


def _owned_entries(state: dict[str, Any]) -> list[dict[str, str]]:
    return [*state.get("lanes", []), state["integration"]]


def _rollback_entries(root: Path, entries: Iterable[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for entry in reversed(list(entries)):
        path = Path(entry["path"])
        if path.exists():
            remove_result = _git(root, "worktree", "remove", str(path), check=False)
            if remove_result.returncode != 0:
                errors.append(f"remove {path}: {remove_result.stderr or remove_result.stdout}")
        if _branch_exists(root, entry["branch"]):
            delete_result = _git(root, "branch", "-d", entry["branch"], check=False)
            if delete_result.returncode != 0:
                errors.append(f"delete {entry['branch']}: {delete_result.stderr or delete_result.stdout}")
    _git(root, "worktree", "prune", check=False)
    return errors


def _remove_owned_empty_directories(run_root: Path, worktree_root: Path) -> None:
    candidates = [run_root / "lanes", run_root, run_root.parent]
    for candidate in candidates:
        if candidate == worktree_root:
            continue
        try:
            candidate.rmdir()
        except OSError:
            pass


def create_pool(root: Path, run_id: str, base_ref: str, lanes: Iterable[str]) -> dict[str, Any]:
    run_id = _validate_identifier(run_id, "run id")
    lane_names = [_validate_identifier(value, "lane name") for value in lanes]
    if not lane_names:
        raise WorktreePoolError("At least one --lane is required")
    normalized_lanes = [name.casefold() for name in lane_names]
    if len(set(normalized_lanes)) != len(normalized_lanes):
        raise WorktreePoolError("Lane names must be unique, including case-insensitive filesystems")
    if "integration" in normalized_lanes:
        raise WorktreePoolError("Lane name 'integration' is reserved")

    _assert_clean(root)
    _assert_worktree_root_ignored(root)

    state_path = _state_path(root, run_id)
    if state_path.exists():
        raise WorktreePoolError(f"Run {run_id!r} already exists: {state_path}")

    base_commit = _resolve_commit(root, base_ref)
    head_commit = _resolve_commit(root, "HEAD")
    if base_commit != head_commit:
        raise WorktreePoolError(
            f"The frozen base {base_ref!r} resolves to {base_commit}, but it must "
            f"match the current checkout HEAD {head_commit}."
        )
    base_branch = _current_branch(root)
    if base_branch is None:
        raise WorktreePoolError(
            "Parallel worktree creation requires a checkout on a named branch; "
            "detached HEAD is unsupported."
        )
    run_root = root / ".worktrees" / "parallel" / run_id
    integration_branch = f"parallel/{run_id}/integration"
    entries: list[dict[str, str]] = [
        {
            "name": "integration",
            "branch": integration_branch,
            "path": str((run_root / "integration").resolve()),
        }
    ]
    entries.extend(
        {
            "name": lane,
            "branch": f"parallel/{run_id}/{lane}",
            "path": str((run_root / "lanes" / lane).resolve()),
        }
        for lane in lane_names
    )

    for entry in entries:
        _assert_valid_branch(root, entry["branch"])
        if _branch_exists(root, entry["branch"]):
            raise WorktreePoolError(f"Branch already exists: {entry['branch']}")
        if Path(entry["path"]).exists():
            raise WorktreePoolError(f"Worktree path already exists: {entry['path']}")

    created: list[dict[str, str]] = []
    try:
        for entry in entries:
            Path(entry["path"]).parent.mkdir(parents=True, exist_ok=True)
            created.append(entry)
            _git(root, "worktree", "add", "-b", entry["branch"], entry["path"], base_commit)
    except (Exception, KeyboardInterrupt) as error:
        rollback_errors = _rollback_entries(root, created)
        if isinstance(error, KeyboardInterrupt) and not rollback_errors:
            raise
        message = (
            "Interrupted while creating the worktree pool"
            if isinstance(error, KeyboardInterrupt)
            else str(error)
        )
        if rollback_errors:
            message += "\nRollback was incomplete:\n" + "\n".join(rollback_errors)
        raise WorktreePoolError(message) from error

    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "git_common_dir": str(_common_dir(root)),
        "base_ref": base_ref,
        "base_branch": base_branch,
        "base_commit": base_commit,
        "worktree_root": str(run_root.resolve()),
        "integration": entries[0],
        "lanes": entries[1:],
    }
    try:
        _write_state(state_path, state)
    except (Exception, KeyboardInterrupt) as error:
        rollback_errors = _rollback_entries(root, created)
        temporary = state_path.with_suffix(state_path.suffix + ".tmp")
        try:
            temporary.unlink()
        except OSError:
            pass
        if isinstance(error, KeyboardInterrupt) and not rollback_errors:
            raise
        message = (
            "Interrupted before worktree-pool state was persisted"
            if isinstance(error, KeyboardInterrupt)
            else f"Cannot persist worktree-pool state: {error}"
        )
        if rollback_errors:
            message += "\nRollback was incomplete:\n" + "\n".join(rollback_errors)
        raise WorktreePoolError(message) from error
    return state


def _registered_worktrees(root: Path) -> dict[str, WorktreeRegistration]:
    output = _git(root, "worktree", "list", "--porcelain").stdout
    registrations: dict[str, WorktreeRegistration] = {}
    for block in output.split("\n\n"):
        path: Path | None = None
        branch: str | None = None
        locked = False
        prunable = False
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = Path(line.removeprefix("worktree ")).resolve()
            elif line.startswith("branch refs/heads/"):
                branch = line.removeprefix("branch refs/heads/")
            elif line == "locked" or line.startswith("locked "):
                locked = True
            elif line == "prunable" or line.startswith("prunable "):
                prunable = True
        if path is not None and branch is not None:
            registrations[branch] = WorktreeRegistration(path=path, locked=locked, prunable=prunable)
    return registrations


def _entry_status(root: Path, entry: dict[str, str]) -> dict[str, Any]:
    path = Path(entry["path"])
    branch_exists = _branch_exists(root, entry["branch"])
    commit = _resolve_commit(root, entry["branch"]) if branch_exists else None
    dirty: bool | None = None
    if path.is_dir():
        status = _git(path, "status", "--porcelain=v1", "--untracked-files=all", check=False)
        dirty = bool(status.stdout) if status.returncode == 0 else None
    return {**entry, "path_exists": path.exists(), "branch_exists": branch_exists, "commit": commit, "dirty": dirty}


def pool_status(root: Path, run_id: str) -> dict[str, Any]:
    _, state = _load_state(root, run_id)
    return {
        "run_id": run_id,
        "base_branch": state.get("base_branch"),
        "base_commit": state["base_commit"],
        "integration": _entry_status(root, state["integration"]),
        "lanes": [_entry_status(root, entry) for entry in state["lanes"]],
    }


def _new_cleanup_journal(
    entries: list[dict[str, str]], merged_into: str, merged_commit: str
) -> dict[str, Any]:
    return {
        "merged_into": merged_into,
        "merged_commit": merged_commit,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "operations": [
            {**entry, "kind": "worktree", "status": "pending"} for entry in entries
        ]
        + [{**entry, "kind": "branch", "status": "pending"} for entry in entries],
    }


def _reconcile_cleanup_journal(
    root: Path,
    state_path: Path,
    state: dict[str, Any],
    registrations: dict[str, WorktreeRegistration],
) -> None:
    changed = False
    for operation in state["cleanup_journal"]["operations"]:
        branch = operation["branch"]
        path = Path(operation["path"]).resolve()
        if operation["kind"] == "worktree":
            registration = registrations.get(branch)
            present = registration is not None or path.exists()
        else:
            present = _branch_exists(root, branch)

        if operation["status"] == "removing":
            operation["status"] = "pending" if present else "removed"
            changed = True
        elif operation["status"] == "removed" and present:
            raise WorktreePoolError(
                "Cleanup refused: a resource recorded as removed was recreated: "
                f"{branch} ({path})"
            )
    if changed:
        _write_state(state_path, state)


def _cleanup_preflight_problems(
    root: Path,
    state: dict[str, Any],
    merged_commit: str,
    registrations: dict[str, WorktreeRegistration],
) -> list[str]:
    problems: list[str] = []
    worktree_status = {
        operation["branch"]: operation["status"]
        for operation in state["cleanup_journal"]["operations"]
        if operation["kind"] == "worktree"
    }
    branch_status = {
        operation["branch"]: operation["status"]
        for operation in state["cleanup_journal"]["operations"]
        if operation["kind"] == "branch"
    }
    for entry in _owned_entries(state):
        branch = entry["branch"]
        path = Path(entry["path"]).resolve()
        registration = registrations.get(branch)
        registered_path = registration.path if registration is not None else None
        branch_exists = _branch_exists(root, branch)

        if branch_status[branch] != "removed":
            if not branch_exists:
                problems.append(f"Recorded branch is missing: {branch}")
            else:
                ancestor = _git(root, "merge-base", "--is-ancestor", branch, merged_commit, check=False)
                if ancestor.returncode != 0:
                    problems.append(
                        f"Branch {branch} is not an ancestor of the destination; it is not safely merged"
                    )

        if worktree_status[branch] == "removed":
            continue
        if registration is None:
            problems.append(f"Recorded worktree is missing: {path}")
        if registered_path is not None and registered_path != path:
            problems.append(f"Branch {branch} is checked out at unexpected path {registered_path}")
        if path.exists() and registered_path != path:
            problems.append(f"Recorded path {path} exists but is not the registered worktree for {branch}")
        if not path.exists() and registered_path == path:
            problems.append(f"Registered worktree path is missing on disk: {path}")
        if registration is not None and registration.locked:
            problems.append(f"Worktree {path} is locked; unlock it before cleanup")
        if registration is not None and registration.prunable:
            problems.append(f"Worktree {path} is marked prunable; repair or prune it explicitly before cleanup")
        if path.exists() and registered_path == path:
            status = _git(path, "status", "--porcelain=v1", "--untracked-files=all", check=False)
            if status.returncode != 0:
                problems.append(f"Cannot inspect worktree {path}: {status.stderr or status.stdout}")
            elif status.stdout:
                problems.append(f"Worktree {path} has uncommitted changes")
    return problems


def cleanup_pool(root: Path, run_id: str, merged_into: str) -> dict[str, Any]:
    state_path, state = _load_state(root, run_id)
    entries = _owned_entries(state)
    owned_branches = {entry["branch"] for entry in entries}
    if merged_into in owned_branches:
        raise WorktreePoolError(
            "--merged-into must name the final destination branch, not an owned lane "
            "or integration branch"
        )
    if not _branch_exists(root, merged_into):
        raise WorktreePoolError(f"--merged-into must name an existing local branch: {merged_into}")

    current_branch = _current_branch(root)
    if current_branch != merged_into:
        raise WorktreePoolError(
            f"Checkout branch {merged_into!r} before cleanup; the current checkout is "
            f"{current_branch or 'detached HEAD'!r}."
        )
    destination_status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if destination_status:
        raise WorktreePoolError("Cleanup refused: destination checkout has uncommitted or untracked changes")

    merged_commit = _resolve_commit(root, merged_into)
    root_head = _resolve_commit(root, "HEAD")
    if merged_commit != root_head:
        raise WorktreePoolError(f"Checkout branch {merged_into!r} at its current tip before cleanup")

    registrations = _registered_worktrees(root)
    journal = state.get("cleanup_journal")
    if journal is None:
        state["cleanup_journal"] = _new_cleanup_journal(entries, merged_into, merged_commit)
        problems = _cleanup_preflight_problems(root, state, merged_commit, registrations)
        if problems:
            del state["cleanup_journal"]
            raise WorktreePoolError("Cleanup refused:\n" + "\n".join(f"- {problem}" for problem in problems))
        _write_state(state_path, state)
    else:
        if journal["merged_into"] != merged_into:
            raise WorktreePoolError(
                "Cleanup refused: retry must use the recorded destination branch "
                f"{journal['merged_into']!r}"
            )
        recorded_commit = journal["merged_commit"]
        if _git(root, "merge-base", "--is-ancestor", recorded_commit, merged_commit, check=False).returncode != 0:
            raise WorktreePoolError(
                "Cleanup refused: current destination no longer contains the recorded cleanup commit"
            )
        _reconcile_cleanup_journal(root, state_path, state, registrations)
        registrations = _registered_worktrees(root)
        problems = _cleanup_preflight_problems(root, state, merged_commit, registrations)
        if problems:
            raise WorktreePoolError("Cleanup refused:\n" + "\n".join(f"- {problem}" for problem in problems))

    for operation in state["cleanup_journal"]["operations"]:
        if operation["status"] == "removed":
            continue
        operation["status"] = "removing"
        _write_state(state_path, state)
        if operation["kind"] == "worktree":
            _git(root, "worktree", "remove", operation["path"])
        else:
            _git(root, "branch", "-d", operation["branch"])
        operation["status"] = "removed"
        _write_state(state_path, state)

    removed_worktrees = [
        operation["path"]
        for operation in state["cleanup_journal"]["operations"]
        if operation["kind"] == "worktree" and operation["status"] == "removed"
    ]
    removed_branches = [
        operation["branch"]
        for operation in state["cleanup_journal"]["operations"]
        if operation["kind"] == "branch" and operation["status"] == "removed"
    ]

    _git(root, "worktree", "prune")
    state_path.unlink()
    _remove_owned_empty_directories(Path(state["worktree_root"]), root / ".worktrees")
    try:
        state_path.parent.rmdir()
    except OSError:
        pass

    return {
        "run_id": run_id,
        "merged_into": merged_into,
        "merged_commit": merged_commit,
        "removed_worktrees": removed_worktrees,
        "removed_branches": removed_branches,
    }


def _print_result(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
        return
    if "removed_worktrees" in value:
        print(f"Cleaned run {value['run_id']} after merge into {value['merged_into']}")
        print(f"Removed worktrees: {len(value['removed_worktrees'])}")
        print(f"Removed branches: {len(value['removed_branches'])}")
    elif "integration" in value and "base_commit" in value and "created_at_utc" in value:
        print(f"Created run {value['run_id']} from {value['base_commit']}")
        print(f"Integration: {value['integration']['path']} ({value['integration']['branch']})")
        for lane in value["lanes"]:
            print(f"Lane {lane['name']}: {lane['path']} ({lane['branch']})")
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create integration and lane worktrees from one frozen base commit")
    create.add_argument("--repo", default=".", help="Path inside the Git repository")
    create.add_argument("--run-id", required=True)
    create.add_argument("--base-ref", default="HEAD")
    create.add_argument("--lane", action="append", default=[], help="Repeat once per independent lane")
    create.add_argument("--json", action="store_true")

    status = subparsers.add_parser("status", help="Show recorded branches, paths, commits, and dirty state")
    status.add_argument("--repo", default=".")
    status.add_argument("--run-id", required=True)
    status.add_argument("--json", action="store_true")

    cleanup = subparsers.add_parser("cleanup", help="Remove only clean, recorded worktrees whose branches are merged")
    cleanup.add_argument("--repo", default=".")
    cleanup.add_argument("--run-id", required=True)
    cleanup.add_argument("--merged-into", required=True, help="Ref that must contain every owned branch")
    cleanup.add_argument("--json", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = _repo_root(Path(args.repo))
        if args.command == "create":
            result = create_pool(root, args.run_id, args.base_ref, args.lane)
        elif args.command == "status":
            result = pool_status(root, args.run_id)
        elif args.command == "cleanup":
            result = cleanup_pool(root, args.run_id, args.merged_into)
        else:  # pragma: no cover - argparse enforces commands
            parser.error(f"Unknown command: {args.command}")
            return 2
        _print_result(result, args.json)
        return 0
    except WorktreePoolError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        if args.command == "create":
            message = "error: creation interrupted; newly created resources were rolled back when possible"
        else:
            message = "error: operation interrupted; inspect recorded state before retrying"
        print(message, file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
