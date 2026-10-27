#!/usr/bin/env python3
"""Flatten one explicitly linked plan bundle into a deterministic numbered plan."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

from plan_model import (
    BOLD_SECTION_RE,
    CHECKBOX_RE,
    PlanFormatError,
    TASK_RE,
    global_constraints_from_text,
    normalize_repo_path,
    parse_plan,
    semantic_sha256,
    semantic_text,
)


BUNDLE_START = "<!-- plan-bundle-manifest"
BUNDLE_END = "plan-bundle-manifest -->"
SUBPLANS_HEADING = "## subplans"


class BundleError(ValueError):
    pass


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _atomic_write(path: Path, text: str, force: bool) -> None:
    if path.exists() and not force:
        if semantic_text(path.read_bytes()) == text:
            return
        raise BundleError(f"output already exists: {path}; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def _subplan_value(line: str) -> str | None:
    if not line.strip().startswith("-"):
        return None
    quoted = re.findall(r"`([^`]+)`", line)
    if quoted:
        if len(quoted) != 1:
            raise BundleError(f"subplan entry must contain exactly one path: {line.strip()}")
        return quoted[0]
    value = re.sub(r"^\s*-\s*(?:Plan\s*:\s*)?", "", line, flags=re.IGNORECASE).strip()
    return value if value.lower().endswith(".md") else None


def _master_parts(master: Path) -> tuple[str, list[str], str]:
    text = semantic_text(master.read_bytes())
    lines = text.splitlines()
    task_lines = [line for line in lines if TASK_RE.match(line)]
    if task_lines:
        raise BundleError("a bundle master must list subplans instead of defining numbered Tasks")

    start = next(
        (index for index, line in enumerate(lines) if line.strip().casefold() == SUBPLANS_HEADING),
        None,
    )
    if start is None:
        raise BundleError("master plan requires an explicit ## Subplans section")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## ") or lines[index].strip() == "---":
            end = index
            break
    values = [value for line in lines[start + 1 : end] if (value := _subplan_value(line))]
    if not values:
        raise BundleError("## Subplans must list at least one Markdown plan")
    preamble_lines = lines[:start] + lines[end:]
    constraints_start = next(
        (
            index
            for index, line in enumerate(preamble_lines)
            if line.strip().casefold() == "## global constraints"
        ),
        None,
    )
    if constraints_start is not None:
        constraints_end = len(preamble_lines)
        for index in range(constraints_start + 1, len(preamble_lines)):
            if preamble_lines[index].startswith("## ") or preamble_lines[index].strip() == "---":
                constraints_end = index
                break
        preamble_lines = preamble_lines[:constraints_start] + preamble_lines[constraints_end:]
    preamble = "\n".join(preamble_lines).strip()
    return text, values, preamble


def _resolve_subplans(master: Path, project: Path, values: list[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for raw_value in values:
        normalized = normalize_repo_path(raw_value)
        candidates = [project / normalized, master.parent / normalized]
        existing = {candidate.resolve() for candidate in candidates if candidate.is_file()}
        if len(existing) != 1:
            reason = "is ambiguous" if existing else "does not exist"
            raise BundleError(f"subplan {raw_value!r} {reason}")
        source = existing.pop()
        if not _within(source, project):
            raise BundleError(f"subplan resolves outside the project: {raw_value}")
        if source in seen:
            raise BundleError(f"subplan is listed more than once: {raw_value}")
        seen.add(source)
        result.append(source)
    return result


def bundle_source_paths(master: Path, project: Path) -> list[Path]:
    """Return the exact subplan files declared by a bundle master."""
    _, values, _ = _master_parts(master.resolve())
    return _resolve_subplans(master.resolve(), project.resolve(), values)


def _replace_task_references(text: str, task_map: dict[int, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        source_id = int(match.group(1))
        return f"Task {task_map.get(source_id, source_id)}"

    result: list[str] = []
    consumes_continuation = False
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else marker if fence is None else fence
            consumes_continuation = False
            result.append(line)
            continue
        if fence is not None:
            result.append(line)
            continue
        is_consumes = bool(re.match(r"^-\s+Consumes\s*:", stripped, re.IGNORECASE))
        is_continuation = (
            consumes_continuation
            and bool(stripped)
            and not stripped.startswith("-")
            and not BOLD_SECTION_RE.match(stripped)
            and not CHECKBOX_RE.match(line)
        )
        if is_consumes or is_continuation:
            line = re.sub(r"\bTask\s+(\d+)\b", replace, line, flags=re.IGNORECASE)
        consumes_continuation = is_consumes or is_continuation
        result.append(line)
    return "\n".join(result)


def build_normalized_bundle(master: Path, project: Path, output: Path) -> tuple[str, dict[str, Any]]:
    master = master.expanduser().resolve()
    project = project.expanduser().resolve()
    output = output.expanduser().resolve()
    if not master.is_file() or not _within(master, project):
        raise BundleError("master plan must be a file inside --project")
    if not _within(output, project):
        raise BundleError("normalized output must stay inside --project")

    master_text, values, preamble = _master_parts(master)
    subplans = _resolve_subplans(master, project, values)
    parsed = [(source, parse_plan(source)) for source in subplans]
    next_id = 1
    task_maps: dict[Path, dict[int, int]] = {}
    for source, plan in parsed:
        task_maps[source] = {}
        for task in plan.tasks:
            task_maps[source][task.task_id] = next_id
            next_id += 1

    constraints = global_constraints_from_text(master_text)
    for _, plan in parsed:
        constraints.extend(plan.global_constraints)

    bindings: list[dict[str, Any]] = []
    task_blocks: list[str] = []
    for source, plan in parsed:
        source_text = semantic_text(source.read_bytes())
        source_lines = source_text.splitlines()
        source_path = source.relative_to(project).as_posix()
        task_map = task_maps[source]
        for task in plan.tasks:
            normalized_id = task_map[task.task_id]
            namespaced_id = f"{source_path}#Task {task.task_id}"
            block = source_lines[task.line_start - 1 : task.line_end]
            block[0] = f"### Task {normalized_id}: [{namespaced_id}] {task.title}"
            body = _replace_task_references("\n".join(block[1:]).rstrip(), task_map)
            task_blocks.append(block[0] + ("\n" + body if body else ""))
            bindings.append(
                {
                    "normalized_task": normalized_id,
                    "namespaced_id": namespaced_id,
                    "source_plan": source_path,
                    "source_task": task.task_id,
                    "files": task.files,
                }
            )

    manifest = {
        "schema_version": 1,
        "project_root": Path(os.path.relpath(project, output.parent)).as_posix(),
        "master_plan": master.relative_to(project).as_posix(),
        "master_sha256": semantic_sha256(master.read_bytes()),
        "sources": [
            {
                "path": source.relative_to(project).as_posix(),
                "sha256": plan.sha256,
            }
            for source, plan in parsed
        ],
        "task_bindings": bindings,
    }
    sections = [preamble] if preamble else [f"# {master.stem} Normalized Implementation Plan"]
    if constraints:
        sections.append("## Global Constraints\n\n" + "\n".join(constraints))
    sections.append(
        BUNDLE_START
        + "\n"
        + json.dumps(manifest, ensure_ascii=False, indent=2)
        + "\n"
        + BUNDLE_END
    )
    sections.extend(task_blocks)
    return "\n\n".join(section.strip() for section in sections if section.strip()) + "\n", manifest


def extract_bundle_manifest(path: Path) -> dict[str, Any] | None:
    text = semantic_text(path.read_bytes())
    if BUNDLE_START not in text:
        return None
    if text.count(BUNDLE_START) != 1 or text.count(BUNDLE_END) != 1:
        raise BundleError("normalized plan has malformed bundle manifest markers")
    payload = text.split(BUNDLE_START, 1)[1].split(BUNDLE_END, 1)[0].strip()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise BundleError("plan bundle manifest must be a JSON object")
    return value


def validate_bundle_bindings(path: Path) -> list[str]:
    try:
        manifest = extract_bundle_manifest(path)
    except (OSError, UnicodeError, json.JSONDecodeError, BundleError) as exc:
        return [f"cannot read plan bundle manifest: {exc}"]
    if manifest is None:
        return []
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("plan bundle schema_version must be 1")
    root_value = manifest.get("project_root")
    if not isinstance(root_value, str) or not root_value.strip():
        return ["plan bundle project_root is required"]
    project = (path.resolve().parent / root_value).resolve()
    if not _within(path.resolve(), project):
        return ["plan bundle project_root does not contain the normalized plan"]

    def source_path(value: object, label: str) -> Path | None:
        if not isinstance(value, str):
            errors.append(f"{label} path is required")
            return None
        try:
            normalized = normalize_repo_path(value)
        except PlanFormatError as exc:
            errors.append(f"{label} path is invalid: {exc}")
            return None
        resolved = (project / normalized).resolve()
        if not _within(resolved, project):
            errors.append(f"{label} resolves outside the project")
            return None
        return resolved

    master = source_path(manifest.get("master_plan"), "bundle master")
    if master is None or not master.is_file():
        errors.append("bundle master plan does not exist")
    elif manifest.get("master_sha256") != semantic_sha256(master.read_bytes()):
        errors.append("bundle master hash does not match the bound source")

    source_records = manifest.get("sources")
    if not isinstance(source_records, list):
        return errors + ["plan bundle sources must be a list"]
    source_plans: dict[str, Any] = {}
    for index, record in enumerate(source_records):
        if not isinstance(record, dict):
            errors.append(f"bundle source {index} must be an object")
            continue
        source = source_path(record.get("path"), f"bundle source {index}")
        if source is None or not source.is_file():
            errors.append(f"bundle source {index} does not exist")
            continue
        try:
            plan = parse_plan(source)
        except (OSError, UnicodeError, PlanFormatError) as exc:
            errors.append(f"cannot parse bundle source {index}: {exc}")
            continue
        if record.get("sha256") != plan.sha256:
            errors.append(f"bundle source {record.get('path')} hash does not match")
        source_plans[str(record.get("path"))] = plan

    try:
        normalized_plan = parse_plan(path)
    except (OSError, UnicodeError, PlanFormatError) as exc:
        return errors + [f"cannot parse normalized bundle: {exc}"]
    normalized_tasks = {task.task_id: task for task in normalized_plan.tasks}
    bindings = manifest.get("task_bindings")
    if not isinstance(bindings, list):
        return errors + ["plan bundle task_bindings must be a list"]
    seen: set[int] = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            errors.append(f"bundle binding {index} must be an object")
            continue
        normalized_id = binding.get("normalized_task")
        source_id = binding.get("source_task")
        source_name = binding.get("source_plan")
        if type(normalized_id) is not int or normalized_id in seen:
            errors.append(f"bundle binding {index} has an invalid normalized Task")
            continue
        seen.add(normalized_id)
        normalized_task = normalized_tasks.get(normalized_id)
        source_plan = source_plans.get(source_name)
        source_task = next(
            (task for task in source_plan.tasks if task.task_id == source_id), None
        ) if source_plan is not None and type(source_id) is int else None
        if normalized_task is None or source_task is None:
            errors.append(f"bundle binding {index} references a missing Task")
            continue
        if binding.get("files") != source_task.files or normalized_task.files != source_task.files:
            errors.append(f"bundle binding {index} file set does not match its source Task")
    if seen != set(normalized_tasks):
        errors.append("plan bundle bindings must cover every normalized Task exactly once")
    if master is not None and master.is_file():
        try:
            expected, _ = build_normalized_bundle(master, project, path)
            actual = semantic_text(path.read_bytes())
            if actual != expected:
                errors.append("normalized plan content does not match its bound master and subplans")
        except (OSError, UnicodeError, PlanFormatError, BundleError) as exc:
            errors.append(f"cannot reconstruct normalized plan bundle: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("master_plan", type=Path)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        rendered, manifest = build_normalized_bundle(
            args.master_plan, args.project, args.output
        )
        output = args.output.expanduser().resolve()
        inputs = {
            args.master_plan.expanduser().resolve(),
            *(
                args.project.expanduser().resolve() / item["path"]
                for item in manifest["sources"]
            ),
        }
        if output in inputs:
            raise BundleError("output must not replace the master plan or a subplan")
        _atomic_write(output, rendered, args.force)
    except (OSError, UnicodeError, json.JSONDecodeError, PlanFormatError, BundleError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    report = {
        "schema_version": 1,
        "master_plan": str(args.master_plan.expanduser().resolve()),
        "output": str(output),
        "source_count": len(manifest["sources"]),
        "task_count": len(manifest["task_bindings"]),
    }
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {report['task_count']} normalized Tasks to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
