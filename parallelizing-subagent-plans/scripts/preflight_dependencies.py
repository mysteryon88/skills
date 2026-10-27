#!/usr/bin/env python3
"""Report required skill dependencies and non-mutating Git worktree signals."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


REQUIRED = {
    "orchestrating-parallel-worktree-changes-v2": "orchestrating-parallel-worktree-changes-v2",
}
REQUIRED_MAJOR_VERSIONS = {"orchestrating-parallel-worktree-changes-v2": 2}
OPTIONAL_COMPANIONS = {
    "codex-worker-orchestrator": "codex-worker-orchestrator",
}
OPTIONAL_MAJOR_VERSIONS = {"codex-worker-orchestrator": (2, 3)}
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
NAME_RE = re.compile(r"^name:\s*([a-z0-9-]+)\s*$", re.MULTILINE)
VERSION_RE = re.compile(r"^([0-9])$")
EXCLUDED_TREE_NAMES = {"_publish", ".git", "__pycache__", ".pytest_cache"}


def default_roots() -> list[Path]:
    roots: list[Path] = []
    codex_dir = os.environ.get("CODEX_HOME")
    if codex_dir:
        roots.append(Path(codex_dir) / "skills")
    roots.extend(
        [
            Path.home() / ".codex" / "skills",
            Path.home() / ".agents" / "skills",
            Path.home() / ".codex" / "plugins" / "cache",
        ]
    )
    result: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def frontmatter_name(text: str) -> str | None:
    match = FRONTMATTER_RE.match(text)
    if match is None:
        return None
    names = NAME_RE.findall(match.group(1))
    return names[0] if len(names) == 1 else None


def discover(
    roots: list[Path], *, shallow_roots: set[Path] | None = None
) -> dict[str, Path]:
    discovered: dict[str, Path] = {}
    target_names = set(REQUIRED.values()) | set(OPTIONAL_COMPANIONS.values())
    shallow_roots = shallow_roots or set()
    for root in roots:
        if not root.is_dir():
            continue
        skill_files = (
            list(root.glob("*/SKILL.md"))
            if root in shallow_roots
            else root.rglob("SKILL.md")
        )
        for skill_file in skill_files:
            if set(skill_file.relative_to(root).parts) & EXCLUDED_TREE_NAMES:
                continue
            try:
                head = skill_file.read_text(encoding="utf-8")[:2048]
            except (OSError, UnicodeError):
                continue
            name = frontmatter_name(head)
            if name in target_names:
                discovered.setdefault(name, skill_file.parent.resolve())
                if target_names.issubset(discovered):
                    return discovered
    return discovered


def git_preflight(
    project: Path,
    git_executable: Path | None = None,
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "git_executable": None,
        "git_available": None,
        "repository": False,
        "worktree_command_available": False,
        "capability": "unverified",
        "probe_error": None,
    }
    if git_executable is None:
        result["probe_error"] = (
            "Git was not probed; pass --git-executable with a trusted absolute path."
        )
        return result

    if not git_executable.is_absolute():
        result["git_available"] = False
        result["capability"] = "unavailable"
        result["probe_error"] = "--git-executable must be an absolute path"
        return result
    try:
        git_path = git_executable.resolve(strict=True)
    except OSError as exc:
        result["git_available"] = False
        result["capability"] = "unavailable"
        result["probe_error"] = f"cannot resolve --git-executable: {exc}"
        return result
    if not git_path.is_file():
        result["git_available"] = False
        result["capability"] = "unavailable"
        result["probe_error"] = "--git-executable must resolve to a regular file"
        return result

    result["git_executable"] = str(git_path)
    try:
        version = subprocess.run(
            [str(git_path), "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["git_available"] = False
        result["capability"] = "unavailable"
        result["probe_error"] = f"Git version probe failed: {exc}"
        return result
    if version.returncode != 0:
        result["git_available"] = False
        result["capability"] = "unavailable"
        result["probe_error"] = "--git-executable did not pass the Git version probe"
        return result

    result["git_available"] = True
    try:
        repo = subprocess.run(
            [str(git_path), "-C", str(project), "rev-parse", "--is-inside-work-tree"],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["git_available"] = False
        result["capability"] = "unavailable"
        result["probe_error"] = f"Git probe failed: {exc}"
        return result
    result["repository"] = repo.returncode == 0 and repo.stdout.strip() == "true"
    if result["repository"]:
        try:
            worktrees = subprocess.run(
                [str(git_path), "-C", str(project), "worktree", "list", "--porcelain"],
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["git_available"] = False
            result["capability"] = "unavailable"
            result["probe_error"] = f"Git worktree probe failed: {exc}"
            return result
        result["worktree_command_available"] = worktrees.returncode == 0
    return result


def build_report(
    roots: list[Path],
    project: Path,
    *,
    shallow_roots: set[Path] | None = None,
    git_executable: Path | None = None,
    git_timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    discovered = discover(roots, shallow_roots=shallow_roots)
    dependencies: list[dict[str, Any]] = []
    missing: list[str] = []
    incompatible: list[str] = []
    for logical_name, skill_name in REQUIRED.items():
        path = discovered.get(skill_name)
        version: str | None = None
        if path is not None and (path / "VERSION").is_file():
            try:
                version = (path / "VERSION").read_text(encoding="utf-8").strip() or None
            except (OSError, UnicodeError):
                version = None
        found = path is not None
        required_major = REQUIRED_MAJOR_VERSIONS.get(logical_name)
        version_match = VERSION_RE.fullmatch(version) if version is not None else None
        compatible = found and (
            required_major is None
            or (version_match is not None and int(version_match.group(1)) == required_major)
        )
        if not found:
            missing.append(logical_name)
        elif not compatible:
            incompatible.append(logical_name)
        dependencies.append(
            {
                "logical_name": logical_name,
                "skill_name": skill_name,
                "found": found,
                "compatible": compatible,
                "path": str(path) if path is not None else None,
                "version": version,
                "version_requirement": (
                    f"major == {required_major}" if required_major is not None else None
                ),
            }
        )
    companions: list[dict[str, Any]] = []
    for logical_name, skill_name in OPTIONAL_COMPANIONS.items():
        path = discovered.get(skill_name)
        version: str | None = None
        if path is not None and (path / "VERSION").is_file():
            try:
                version = (path / "VERSION").read_text(encoding="utf-8").strip() or None
            except (OSError, UnicodeError):
                version = None
        found = path is not None
        supported_majors = OPTIONAL_MAJOR_VERSIONS.get(logical_name)
        version_match = VERSION_RE.fullmatch(version) if version is not None else None
        compatible = found and (
            supported_majors is None
            or (version_match is not None and int(version_match.group(1)) in supported_majors)
        )
        companions.append(
            {
                "logical_name": logical_name,
                "skill_name": skill_name,
                "found": found,
                "compatible": compatible,
                "path": str(path) if path is not None else None,
                "version": version,
                "version_requirement": (
                    "major in {" + ", ".join(map(str, supported_majors)) + "}"
                    if supported_majors is not None else None
                ),
                "required": False,
            }
        )
    worktree = git_preflight(
        project.resolve(),
        git_executable,
        timeout_seconds=git_timeout_seconds,
    )
    return {
        "schema_version": 1,
        "ready": (
            not missing
            and not incompatible
            and (git_executable is None or worktree["git_available"] is True)
        ),
        "roots": [str(root) for root in roots],
        "dependencies": dependencies,
        "companions": companions,
        "missing": missing,
        "incompatible": incompatible,
        "worktree_preflight": worktree,
        "note": "Worktree creation remains unverified until the harness or executor preflight confirms it.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", action="append", type=Path)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument(
        "--git-executable",
        type=Path,
        help="Trusted absolute Git executable. PATH and the project directory are never searched.",
    )
    parser.add_argument("--git-timeout", type=float, default=10.0)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    if args.skill_root:
        roots = [path.expanduser().resolve() for path in args.skill_root]
        shallow_roots: set[Path] = set()
    else:
        roots = [
            project,
            project / ".codex" / "skills",
            project / ".agents" / "skills",
            *default_roots(),
        ]
        shallow_roots = {project}
    roots = list(dict.fromkeys(roots))
    if args.git_timeout <= 0:
        parser.error("--git-timeout must be greater than zero")
    report = build_report(
        roots,
        project,
        shallow_roots=shallow_roots,
        git_executable=args.git_executable,
        git_timeout_seconds=args.git_timeout,
    )
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Dependency preflight: {'READY' if report['ready'] else 'NOT READY'}")
        for item in report["dependencies"]:
            state = item["path"] or "missing"
            version = f" (version {item['version']})" if item["version"] else ""
            compatibility = " [INCOMPATIBLE]" if item["found"] and not item["compatible"] else ""
            print(f"- {item['logical_name']}: {state}{version}{compatibility}")
        for item in report["companions"]:
            state = item["path"] or "not installed"
            version = f" (version {item['version']})" if item["version"] else ""
            compatibility = " [INCOMPATIBLE]" if item["found"] and not item["compatible"] else ""
            print(f"- optional {item['logical_name']}: {state}{version}{compatibility}")
        print(f"- worktree creation: {report['worktree_preflight']['capability']}")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
