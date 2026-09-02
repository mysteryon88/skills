#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from string import Template
from typing import Any

from project_companion_common import (
    GENERATED_BY,
    SCHEMA_VERSION,
    SKILL_SUFFIX,
    SUPPORTED_OWNED_SCHEMA_VERSIONS,
    bullet_list,
    choose_skills_dir,
    collect_instruction_files,
    collect_top_level_entries,
    compact_summary,
    detect_excluded_areas,
    detect_explicit_commands,
    detect_project_name,
    detect_sensitive_file_signals,
    detect_stack_signals,
    detect_workspace_signals,
    fingerprint_files,
    get_git_info,
    inventory_sha256,
    package_version,
    relative_posix,
    safe_description,
    scan_high_signal_files,
    sha256_file,
    slugify,
    utc_now,
)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "templates" / "project-companion"
GENERATED_RELATIVE_FILES = [
    "SKILL.md",
    "references/project-map.md",
    "references/commands-and-checks.md",
    "references/architecture-and-flows.md",
    "references/constraints-and-risks.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or refresh metadata for a repository-local project context skill."
    )
    parser.add_argument("project_root", help="Repository or project root")
    parser.add_argument("--project-name", help="Override detected project name")
    parser.add_argument("--slug", help="Override generated project slug")
    parser.add_argument(
        "--skills-dir",
        help="Project-local skills directory, absolute or relative to project root",
    )
    parser.add_argument(
        "--reinitialize",
        action="store_true",
        help="Transactionally regenerate a companion previously created by this tool",
    )
    parser.add_argument(
        "--discard-curated",
        action="store_true",
        help="With --reinitialize, explicitly allow replacing modified or untracked companion content",
    )
    parser.add_argument(
        "--refresh-metadata",
        action="store_true",
        help="Preserve companion content and refresh manifest fingerprints and git metadata",
    )
    parser.add_argument(
        "--state",
        choices=("bootstrap", "hydrated"),
        default=None,
        help="Compatibility option; creation supports bootstrap only and hydration uses hydrate_project_companion.py",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output")
    return parser.parse_args()


def read_template(relative: str) -> Template:
    path = TEMPLATE_DIR / relative
    if not path.is_file():
        raise RuntimeError(f"Template not found: {path}")
    return Template(path.read_text(encoding="utf-8"))


def render_to(template_relative: str, destination: Path, values: dict[str, str]) -> None:
    rendered = read_template(template_relative).substitute(values)
    unresolved = [token for token in ("$project_name", "$skill_name", "$generated_at") if token in rendered]
    if unresolved:
        raise RuntimeError(f"Unresolved template tokens in {template_relative}: {', '.join(unresolved)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered.rstrip() + "\n", encoding="utf-8")


def load_existing_manifest(companion_dir: Path) -> dict[str, Any]:
    path = companion_dir / "manifest.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def is_link_or_junction(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except OSError:
        return True


def load_owned_manifest(
    companion_dir: Path,
    project_root: Path,
    skill_name: str | None = None,
) -> dict[str, Any]:
    if is_link_or_junction(companion_dir) or not companion_dir.is_dir():
        return {}
    manifest_path = companion_dir / "manifest.json"
    if is_link_or_junction(manifest_path) or not manifest_path.is_file():
        return {}
    manifest = load_existing_manifest(companion_dir)
    if (
        manifest.get("schema_version") not in SUPPORTED_OWNED_SCHEMA_VERSIONS
        or manifest.get("generated_by") != GENERATED_BY
    ):
        return {}
    manifest_skill_name = manifest.get("skill_name")
    if not isinstance(manifest_skill_name, str) or manifest_skill_name != companion_dir.name:
        return {}
    if skill_name is not None and manifest_skill_name != skill_name:
        return {}
    relative_root = manifest.get("root_relative_to_companion")
    if not isinstance(relative_root, str) or not relative_root:
        return {}
    if (companion_dir / relative_root).resolve() != project_root.resolve():
        return {}
    return manifest


def find_owned_companions(
    project_root: Path,
    preferred_skills_dir: Path,
) -> list[tuple[Path, dict[str, Any]]]:
    roots = {
        preferred_skills_dir.resolve(),
        (project_root / ".agents" / "skills").resolve(),
        (project_root / ".claude" / "skills").resolve(),
    }
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for skills_root in sorted(roots, key=lambda item: str(item).lower()):
        try:
            skills_root.relative_to(project_root)
        except ValueError:
            continue
        if is_link_or_junction(skills_root) or not skills_root.is_dir():
            continue
        try:
            children = sorted(skills_root.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            continue
        for child in children:
            manifest = load_owned_manifest(child, project_root)
            if manifest:
                candidates.append((child.resolve(), manifest))
    unique: dict[Path, dict[str, Any]] = {path: manifest for path, manifest in candidates}
    return sorted(unique.items(), key=lambda item: str(item[0]).lower())


def build_inventory(project_root: Path) -> dict[str, Any]:
    discovery = scan_high_signal_files(project_root)
    high_signal_paths = discovery.paths
    instruction_paths = collect_instruction_files(project_root)
    discovery_errors = list(discovery.errors)
    fingerprints = fingerprint_files(
        high_signal_paths,
        project_root,
        errors=discovery_errors,
    )
    discovery_record = discovery.manifest_record()
    discovery_record["errors"] = sorted(set(discovery_errors))
    return {
        "instructions": [relative_posix(path, project_root) for path in instruction_paths],
        "high_signal": [relative_posix(path, project_root) for path in high_signal_paths],
        "fingerprints": fingerprints,
        "stack": detect_stack_signals(project_root),
        "top_level": collect_top_level_entries(project_root),
        "workspace": detect_workspace_signals(project_root),
        "commands": detect_explicit_commands(project_root),
        "excluded": detect_excluded_areas(project_root),
        "sensitive": detect_sensitive_file_signals(project_root),
        "discovery": discovery_record,
    }


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def generated_file_fingerprints(
    companion_dir: Path,
    *,
    errors: list[str] | None = None,
) -> list[dict[str, Any]]:
    paths = [companion_dir / relative for relative in GENERATED_RELATIVE_FILES]
    return fingerprint_files(paths, companion_dir, errors=errors)


def write_manifest(
    companion_dir: Path,
    project_root: Path,
    project_name: str,
    skill_name: str,
    state: str,
    inventory: dict[str, Any],
    created_at: str,
    generated_from_inventory: str,
    generated_fingerprints: list[dict[str, Any]],
    accepted_generated_fingerprints: list[dict[str, Any]] | None = None,
    durable_evidence_fingerprints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    git = get_git_info(project_root)
    root_relative = Path(os.path.relpath(project_root, companion_dir)).as_posix()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "generator_version": package_version(),
        "skill_name": skill_name,
        "project_name": project_name,
        "root_relative_to_companion": root_relative,
        "context_state": state,
        "created_at": created_at,
        "last_verified_at": now,
        "git": {
            "branch": git.branch,
            "commit": git.commit,
            "remote_present": git.remote != "not available",
        },
        "high_signal_fingerprints": inventory["fingerprints"],
        "discovery": inventory["discovery"],
        "inventory_sha256": inventory_sha256(inventory),
        "generated_content_inventory_sha256": generated_from_inventory,
        "generated_file_fingerprints": generated_fingerprints,
        "accepted_generated_file_fingerprints": (
            accepted_generated_fingerprints
            if accepted_generated_fingerprints is not None
            else generated_fingerprints
        ),
        "durable_fact_evidence_fingerprints": durable_evidence_fingerprints or [],
        "reference_files": [
            "references/project-map.md",
            "references/commands-and-checks.md",
            "references/architecture-and-flows.md",
            "references/constraints-and-risks.md",
        ],
    }
    write_json_atomic(companion_dir / "manifest.json", manifest)
    return manifest


def create_companion(
    companion_dir: Path,
    project_root: Path,
    project_name: str,
    skill_name: str,
    state: str,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    git = get_git_info(project_root)
    root_relative = Path(os.path.relpath(project_root, companion_dir)).as_posix()
    values = {
        "skill_name": skill_name,
        "description": safe_description(project_name),
        "project_name": project_name,
        "root_relative_to_companion": root_relative,
        "context_state": state,
        "generated_at": now,
        "git_branch": git.branch,
        "git_commit": git.commit,
        "stack_summary": compact_summary(inventory["stack"]),
        "instruction_summary": compact_summary(inventory["instructions"]),
        "high_signal_summary": compact_summary(inventory["high_signal"]),
        "top_level_summary": compact_summary(inventory["top_level"]),
        "instruction_list": bullet_list(inventory["instructions"], code=True),
        "high_signal_list": bullet_list(inventory["high_signal"], code=True),
        "top_level_list": bullet_list(inventory["top_level"], code=True),
        "workspace_list": bullet_list(inventory["workspace"], code=True),
        "command_list": bullet_list(inventory["commands"]),
        "excluded_area_list": bullet_list(inventory["excluded"], code=True),
        "sensitive_file_list": bullet_list(inventory["sensitive"], code=True),
    }

    render_to("SKILL.md.tmpl", companion_dir / "SKILL.md", values)
    render_to(
        "references/project-map.md.tmpl",
        companion_dir / "references" / "project-map.md",
        values,
    )
    render_to(
        "references/commands-and-checks.md.tmpl",
        companion_dir / "references" / "commands-and-checks.md",
        values,
    )
    render_to(
        "references/architecture-and-flows.md.tmpl",
        companion_dir / "references" / "architecture-and-flows.md",
        values,
    )
    render_to(
        "references/constraints-and-risks.md.tmpl",
        companion_dir / "references" / "constraints-and-risks.md",
        values,
    )
    return write_manifest(
        companion_dir=companion_dir,
        project_root=project_root,
        project_name=project_name,
        skill_name=skill_name,
        state=state,
        inventory=inventory,
        created_at=now,
        generated_from_inventory=inventory_sha256(inventory),
        generated_fingerprints=generated_file_fingerprints(companion_dir),
    )


def companion_content_changes(
    companion_dir: Path,
    manifest: dict[str, Any],
) -> tuple[list[str], list[str]]:
    recorded = manifest.get("accepted_generated_file_fingerprints")
    if not isinstance(recorded, list):
        recorded = manifest.get("generated_file_fingerprints")
    recorded_map = {
        entry.get("path"): entry.get("sha256")
        for entry in recorded
        if isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and isinstance(entry.get("sha256"), str)
    } if isinstance(recorded, list) else {}
    known = set(recorded_map) | {"manifest.json"}
    current = {
        path.relative_to(companion_dir).as_posix()
        for path in companion_dir.rglob("*")
        if path.is_file()
    }
    untracked = sorted(current - known)
    modified: list[str] = []
    for relative, expected in sorted(recorded_map.items()):
        path = companion_dir / relative
        if not path.is_file():
            modified.append(relative)
            continue
        try:
            actual = sha256_file(path)
        except OSError:
            modified.append(relative)
            continue
        if actual != expected:
            modified.append(relative)
    return untracked, modified


def validate_staged_companion(staging_dir: Path, project_root: Path) -> None:
    validator = SCRIPT_DIR / "validate_project_companion.py"
    result = subprocess.run(
        [
            sys.executable,
            str(validator),
            str(staging_dir),
            "--project-root",
            str(project_root),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stdout.strip() or result.stderr.strip() or "unknown validation failure"
        raise RuntimeError(f"Generated companion failed validation: {details}")


def install_staged_companion(staging_dir: Path, companion_dir: Path) -> None:
    if not companion_dir.exists():
        staging_dir.replace(companion_dir)
        return

    backup_dir = companion_dir.parent / f".{companion_dir.name}.backup-{uuid.uuid4().hex}"
    companion_dir.replace(backup_dir)
    installed = False
    try:
        staging_dir.replace(companion_dir)
        installed = True
    except BaseException:
        if companion_dir.exists():
            shutil.rmtree(companion_dir)
        backup_dir.replace(companion_dir)
        raise
    finally:
        if installed and backup_dir.exists():
            shutil.rmtree(backup_dir)


def create_transactionally(
    companion_dir: Path,
    project_root: Path,
    project_name: str,
    skill_name: str,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    companion_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = companion_dir.parent / f".{companion_dir.name}.staging-{uuid.uuid4().hex}"
    try:
        staging_dir.mkdir(parents=False, exist_ok=False)
        manifest = create_companion(
            companion_dir=staging_dir,
            project_root=project_root,
            project_name=project_name,
            skill_name=skill_name,
            state="bootstrap",
            inventory=inventory,
        )
        validate_staged_companion(staging_dir, project_root)
        install_staged_companion(staging_dir, companion_dir)
        return manifest
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    if not project_root.is_dir():
        print(f"Project root does not exist or is not a directory: {project_root}", file=sys.stderr)
        return 2

    project_name = detect_project_name(project_root, args.project_name)
    project_slug = slugify(args.slug or project_name)
    skill_name = f"{project_slug}{SKILL_SUFFIX}"
    skills_dir = choose_skills_dir(project_root, args.skills_dir)
    try:
        skills_dir.relative_to(project_root)
    except ValueError:
        print(
            f"Project companion skills directory must be inside the project root: {skills_dir}",
            file=sys.stderr,
        )
        return 2
    companion_dir = skills_dir / skill_name

    if args.refresh_metadata and args.reinitialize:
        print("--refresh-metadata and --reinitialize cannot be combined", file=sys.stderr)
        return 2
    if args.discard_curated and not args.reinitialize:
        print("--discard-curated requires --reinitialize", file=sys.stderr)
        return 2
    if args.state == "hydrated":
        print(
            "Cannot create a hydrated companion; add evidence-backed durable facts and use hydrate_project_companion.py.",
            file=sys.stderr,
        )
        return 2

    owned_candidates = find_owned_companions(project_root, skills_dir)
    if len(owned_candidates) > 1:
        paths = ", ".join(str(path) for path, _manifest in owned_candidates)
        print(
            "Multiple owned project companions match this project root; select one explicitly "
            f"or resolve the duplicate before continuing: {paths}",
            file=sys.stderr,
        )
        return 2
    if owned_candidates:
        owned_path, owned_manifest = owned_candidates[0]
        if not companion_dir.exists() or companion_dir.resolve() == owned_path:
            companion_dir = owned_path
            skill_name = str(owned_manifest["skill_name"])

    inventory = build_inventory(project_root)
    discovery_errors = inventory.get("discovery", {}).get("errors", [])
    if discovery_errors:
        print(
            "Project inventory is indeterminate because high-signal inputs could not be read: "
            + "; ".join(str(item) for item in discovery_errors),
            file=sys.stderr,
        )
        return 3

    if args.refresh_metadata:
        if not companion_dir.is_dir():
            print(f"Project companion does not exist: {companion_dir}", file=sys.stderr)
            return 2
        existing = load_owned_manifest(companion_dir, project_root, skill_name)
        if not existing:
            print(
                f"Refusing to refresh companion not owned by this tool: {companion_dir}",
                file=sys.stderr,
            )
            return 2
        state = str(existing.get("context_state") or "bootstrap")
        if state not in {"bootstrap", "hydrated"}:
            state = "bootstrap"
        created_at = str(existing.get("created_at") or utc_now())
        existing_generated_fingerprints = (
            existing.get("generated_file_fingerprints")
            if isinstance(existing.get("generated_file_fingerprints"), list)
            and existing.get("generated_file_fingerprints")
            else generated_file_fingerprints(companion_dir)
        )
        existing_accepted_fingerprints = (
            existing.get("accepted_generated_file_fingerprints")
            if isinstance(existing.get("accepted_generated_file_fingerprints"), list)
            and existing.get("accepted_generated_file_fingerprints")
            else existing_generated_fingerprints
        )
        manifest = write_manifest(
            companion_dir=companion_dir,
            project_root=project_root,
            project_name=project_name,
            skill_name=skill_name,
            state=state,
            inventory=inventory,
            created_at=created_at,
            generated_from_inventory=str(
                existing.get("generated_content_inventory_sha256") or "legacy-unverified"
            ),
            generated_fingerprints=existing_generated_fingerprints,
            accepted_generated_fingerprints=existing_accepted_fingerprints,
            durable_evidence_fingerprints=(
                existing.get("durable_fact_evidence_fingerprints")
                if isinstance(existing.get("durable_fact_evidence_fingerprints"), list)
                else []
            ),
        )
        action = "refreshed"
    else:
        if companion_dir.exists() and not args.reinitialize:
            print(
                f"Project companion already exists: {companion_dir}. Use --refresh-metadata or deliberate --reinitialize.",
                file=sys.stderr,
            )
            return 2
        if companion_dir.exists():
            existing = load_owned_manifest(companion_dir, project_root, skill_name)
            if not existing:
                print(
                    f"Refusing to replace companion not owned by this tool: {companion_dir}",
                    file=sys.stderr,
                )
                return 2
            if existing.get("context_state") == "hydrated" and not args.discard_curated:
                print(
                    "Refusing to reinitialize a hydrated companion because it contains curated durable facts. "
                    "Preserve it or repeat with --discard-curated for explicit data loss.",
                    file=sys.stderr,
                )
                return 2
            untracked, modified = companion_content_changes(companion_dir, existing)
            if untracked and not args.discard_curated:
                print(
                    "Refusing to reinitialize because untracked companion files exist: "
                    + ", ".join(untracked)
                    + ". Preserve them or repeat with --discard-curated.",
                    file=sys.stderr,
                )
                return 2
            if modified and not args.discard_curated:
                print(
                    "Refusing to reinitialize because modified generated files exist: "
                    + ", ".join(modified)
                    + ". Preserve them or repeat with --discard-curated.",
                    file=sys.stderr,
                )
                return 2
        manifest = create_transactionally(
            companion_dir=companion_dir,
            project_root=project_root,
            project_name=project_name,
            skill_name=skill_name,
            inventory=inventory,
        )
        action = "reinitialized" if args.reinitialize else "created"

    payload = {
        "action": action,
        "companion_dir": str(companion_dir.resolve()),
        "skill_name": skill_name,
        "project_name": project_name,
        "context_state": manifest["context_state"],
        "fingerprint_count": len(manifest["high_signal_fingerprints"]),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Project companion {action}: {companion_dir}")
        print(f"Skill name: {skill_name}")
        print(f"Context state: {manifest['context_state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
