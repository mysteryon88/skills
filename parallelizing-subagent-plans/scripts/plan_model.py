#!/usr/bin/env python3
"""Parse numbered implementation plans into a stable inventory."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable

TASK_RE = re.compile(r"^(#{2,4})\s+Task\s+(\d+)\s*:\s*(.+?)\s*$", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"^\s*- \[([ xX])\]")
BOLD_SECTION_RE = re.compile(r"^\*\*[^*]+:\*\*\s*$")
PATH_LINE_RANGE_RE = re.compile(r":\d+(?:-\d+)?$")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]*")
FILE_ENTRY_RE = re.compile(r"^-\s+(?:Create|Modify|Delete|Test)\s*:\s*(.+?)\s*$", re.IGNORECASE)
EXECUTION_RE = re.compile(r"^\*\*Execution:\*\*\s*Epilogue\s*$", re.IGNORECASE)
EPILOGUE_TITLES = {"integrated verification", "release acceptance"}


class PlanFormatError(ValueError):
    """The source plan cannot be represented safely as an execution graph."""


@dataclass(frozen=True)
class TaskRecord:
    task_id: int
    title: str
    line_start: int
    line_end: int
    files: list[str]
    produces: list[str]
    consumes: list[str]
    depends_on_tasks: list[int]
    step_count: int
    completed_steps: int
    completed: bool
    barrier_candidate: bool

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["id"] = payload.pop("task_id")
        return payload


@dataclass(frozen=True)
class PlanRecord:
    source_plan: str
    title: str
    sha256: str
    global_constraints: list[str]
    tasks: list[TaskRecord]
    overlaps: dict[str, list[int]]
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "source_plan": self.source_plan,
            "title": self.title,
            "sha256": self.sha256,
            "global_constraints": self.global_constraints,
            "tasks": [task.to_dict() for task in self.tasks],
            "overlaps": self.overlaps,
            "warnings": self.warnings,
        }


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _looks_like_path(value: str) -> bool:
    value = value.strip()
    if not value or value.startswith("#"):
        return False
    basename = Path(value.replace("\\", "/")).name
    known_names = {
        "Cargo.lock",
        "Gemfile.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "yarn.lock",
        "go.sum",
    }
    return (
        "/" in value
        or "\\" in value
        or "*" in value
        or "{" in value
        or basename in known_names
        or bool(re.search(r"\.[A-Za-z0-9]{1,12}$", basename))
    )


def normalize_repo_path(value: str) -> str:
    """Return a canonical repository-relative POSIX path or fail closed."""
    value = value.strip()
    value = PATH_LINE_RANGE_RE.sub("", value)
    value = value.replace("\\", "/")
    if not value:
        raise PlanFormatError("file path must not be empty")
    if value.startswith(("/", "//")) or WINDOWS_DRIVE_RE.match(value):
        raise PlanFormatError(f"file path must be repository-relative: {value}")

    parts: list[str] = []
    for part in value.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise PlanFormatError(f"file path resolves outside the repository: {value}")
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise PlanFormatError(f"file path must identify a repository file: {value}")
    return "/".join(parts)


def canonical_path_key(value: str) -> str:
    """Return a conservative cross-platform ownership and overlap key."""
    return normalize_repo_path(value).casefold()


def semantic_text(raw: bytes) -> str:
    """Decode plan text and canonicalize line endings without changing content."""
    return raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def semantic_sha256(raw: bytes) -> str:
    """Hash canonical UTF-8 plan text so checkout line endings do not matter."""
    return sha256(semantic_text(raw).encode("utf-8")).hexdigest()


def _extract_paths(lines: list[str]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for line in lines:
        quoted = re.findall(r"`([^`]+)`", line)
        match = FILE_ENTRY_RE.match(line.strip())
        values = quoted or ([match.group(1).strip()] if match else [])
        for value in values:
            normalized = normalize_repo_path(value)
            key = canonical_path_key(normalized)
            if _looks_like_path(normalized) and key not in seen:
                seen.add(key)
                paths.append(normalized)
    return paths


def _extract_interface_lines(lines: list[str], prefix: str) -> list[str]:
    result: list[str] = []
    active = False
    lowered_prefix = prefix.lower()
    for line in lines:
        stripped = line.strip()
        if re.match(rf"^-\s+{re.escape(prefix)}\s*:", stripped, re.IGNORECASE):
            result.append(stripped)
            active = True
            continue
        if active and stripped and not stripped.startswith("-") and not CHECKBOX_RE.match(line):
            result[-1] += " " + stripped
            continue
        active = False
    return result


def _extract_task_dependencies(consumes: Iterable[str]) -> list[int]:
    """Extract explicit source-plan dependencies such as "added in Task 3"."""
    dependencies: list[int] = []
    for line in consumes:
        dependencies.extend(int(value) for value in re.findall(r"\bTask\s+(\d+)\b", line, re.IGNORECASE))
    return _unique(dependencies)


def interface_symbols(lines: Iterable[str]) -> set[str]:
    """Return stable contract-like identifiers mentioned in backticks."""
    symbols: set[str] = set()
    for line in lines:
        for quoted in re.findall(r"`([^`]+)`", line):
            match = IDENTIFIER_RE.search(quoted)
            if match:
                symbols.add(match.group(0))
    return symbols


def _global_constraints(lines: list[str]) -> list[str]:
    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip().lower() == "## global constraints":
            start = index + 1
            break
    if start is None:
        return []
    result: list[str] = []
    for line in lines[start:]:
        if line.startswith("## ") or line.strip() == "---" or TASK_RE.match(line):
            break
        if line.strip().startswith("-"):
            result.append(line.strip())
    return result


def global_constraints_from_text(text: str) -> list[str]:
    return _global_constraints(text.splitlines())


def parse_plan(path: Path) -> PlanRecord:
    resolved = path.expanduser().resolve()
    raw = resolved.read_bytes()
    text = semantic_text(raw)
    lines = text.splitlines()

    title = resolved.stem
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    starts: list[tuple[int, int, str]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else marker if fence is None else fence
            continue
        if fence is not None:
            continue
        match = TASK_RE.match(line)
        if match:
            starts.append((index, int(match.group(2)), match.group(3).strip()))

    warnings: list[str] = []
    if not starts:
        raise PlanFormatError("No numbered Task headings were found; repair the source plan before execution.")

    tasks: list[TaskRecord] = []
    for position, (start, task_id, task_title) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body = lines[start + 1 : end]

        files_section: list[str] = []
        in_files = False
        for line in body:
            stripped = line.strip()
            if stripped.lower() == "**files:**":
                in_files = True
                continue
            if in_files and (BOLD_SECTION_RE.match(stripped) or CHECKBOX_RE.match(line)):
                break
            if in_files:
                files_section.append(line)

        files = _extract_paths(files_section)
        produces = _extract_interface_lines(body, "Produces")
        consumes = _extract_interface_lines(body, "Consumes")
        depends_on_tasks = _extract_task_dependencies(consumes)
        marks = [match.group(1).lower() for line in body if (match := CHECKBOX_RE.match(line))]
        completed_steps = sum(mark == "x" for mark in marks)
        completed = bool(marks) and completed_steps == len(marks)
        barrier = task_title.strip().casefold() in EPILOGUE_TITLES or any(
            EXECUTION_RE.match(line.strip()) for line in body
        )

        if not files and not barrier:
            warnings.append(f"Task {task_id} has no parseable file ownership metadata.")
        if not produces and not consumes:
            warnings.append(f"Task {task_id} has no explicit Interfaces block.")

        tasks.append(
            TaskRecord(
                task_id=task_id,
                title=task_title,
                line_start=start + 1,
                line_end=end,
                files=files,
                produces=produces,
                consumes=consumes,
                depends_on_tasks=depends_on_tasks,
                step_count=len(marks),
                completed_steps=completed_steps,
                completed=completed,
                barrier_candidate=barrier,
            )
        )

    task_ids = [task.task_id for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        duplicates = sorted(task_id for task_id in set(task_ids) if task_ids.count(task_id) > 1)
        raise PlanFormatError(
            "Task identifiers are not unique: " + ", ".join(map(str, duplicates))
        )
    task_id_set = set(task_ids)
    for task in tasks:
        for dependency in task.depends_on_tasks:
            if dependency == task.task_id:
                raise PlanFormatError(f"Task {task.task_id} cannot depend on itself")
            if dependency not in task_id_set:
                raise PlanFormatError(
                    f"Task {task.task_id} references unknown Task {dependency}"
                )

    owners: dict[str, list[int]] = defaultdict(list)
    displayed_paths: dict[str, str] = {}
    for task in tasks:
        for file_path in task.files:
            key = canonical_path_key(file_path)
            displayed_paths.setdefault(key, file_path)
            owners[key].append(task.task_id)
    overlaps = {
        displayed_paths[key]: ids
        for key, ids in owners.items()
        if len(ids) > 1
    }

    return PlanRecord(
        source_plan=str(resolved),
        title=title,
        sha256=semantic_sha256(raw),
        global_constraints=_global_constraints(lines),
        tasks=tasks,
        overlaps=overlaps,
        warnings=_unique(warnings),
    )
