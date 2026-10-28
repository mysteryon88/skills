#!/usr/bin/env python3
"""Install the orchestrator skill, custom agents, and safe Codex flags."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from orchestrator_lib import included_files
from orchestrator_lib import load_install_profiles, load_role_registry, package_tree_files

PACKAGE_NAME = "codex-worker-orchestrator"
MANAGED_MARKER = f"# managed-by: {PACKAGE_NAME}"
SOURCE = Path(__file__).resolve().parents[1]
VERSION_FILE = SOURCE / "VERSION"
VERSION_PATTERN = re.compile(r"^[0-9]$")


def load_install_role_specs(source: Path) -> dict[str, tuple[str, str, str, str]]:
    registry = load_role_registry(source)
    role_dir = source / "assets" / "agent-configs"
    missing = [spec.filename for spec in registry.values() if not (role_dir / spec.filename).is_file()]
    if missing:
        raise ValueError("Role registry references missing template(s): " + ", ".join(missing))
    return {
        spec.filename: (
            spec.name,
            spec.sandbox_mode,
            spec.model,
            spec.model_reasoning_effort,
        )
        for spec in registry.values()
    }


try:
    ROLE_REGISTRY = load_role_registry(SOURCE)
    ROLE_SPECS = load_install_role_specs(SOURCE)
    INSTALL_PROFILES = load_install_profiles(SOURCE, ROLE_REGISTRY)
    ROLE_REGISTRY_ERROR: str | None = None
    PROFILE_REGISTRY_ERROR: str | None = None
except ValueError as exc:
    ROLE_REGISTRY = {}
    ROLE_SPECS = {}
    INSTALL_PROFILES = {}
    ROLE_REGISTRY_ERROR = str(exc)
    PROFILE_REGISTRY_ERROR = str(exc)
ROLE_FILES = tuple(ROLE_SPECS)
RETIRED_ROLE_FILES = (
    "gap-analyzer.toml",
    "plan-reviewer.toml",
    "luna-worker-lite.toml",
    "luna-escalation.toml",
    "test-worker.toml",
    "terra-reviewer.toml",
)
RETIRED_ROLE_NAMES = {
    "gap_analyzer": "gap-analyzer.toml",
    "plan_reviewer": "plan-reviewer.toml",
    "luna_worker_lite": "luna-worker-lite.toml",
    "luna_escalation": "luna-escalation.toml",
    "test_worker": "test-worker.toml",
    "terra_reviewer": "terra-reviewer.toml",
}
ALL_MANAGED_ROLE_FILES = tuple(dict.fromkeys((*ROLE_FILES, *RETIRED_ROLE_FILES)))


@dataclass(frozen=True)
class RoleAction:
    """One role-template decision and the actual destination selected by name."""

    template_filename: str
    destination: Path
    action: str


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def normalized(path: Path) -> Path:
    """Return an absolute lexical path without dereferencing the final symlink."""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def package_version(source: Path = SOURCE) -> str:
    path = source / "VERSION"
    try:
        version = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Package VERSION is unreadable: {path}: {exc}") from exc
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Package VERSION must contain one digit: {version!r}")
    return version


def reject_package_symlinks(root: Path) -> None:
    package_tree_files(root)


def parse_toml(text: str, label: str) -> dict[str, object]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in {label}: {exc}") from exc


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    try:
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def is_filesystem_root(path: Path) -> bool:
    return path == Path(path.anchor)


def resolve_existing_symlink(path: Path, label: str, expected_kind: str) -> Path:
    """Resolve an existing final symlink while preserving it on disk during writes."""
    if not path.is_symlink():
        return path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"Broken {label} symlink: {path}: {exc}") from exc
    if expected_kind == "directory" and not resolved.is_dir():
        raise ValueError(f"{label} symlink does not point to a directory: {path} -> {resolved}")
    if expected_kind == "file" and not resolved.is_file():
        raise ValueError(f"{label} symlink does not point to a file: {path} -> {resolved}")
    return normalized(resolved)


def installed_skill_name(path: Path) -> str | None:
    """Read only the simple YAML frontmatter name used by Agent Skills."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        return None
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "name":
            return value.strip().strip('"').strip("'")
    return None


def validate_install_paths(
    codex_home: Path,
    skill_target: Path,
    agents_target: Path,
    config_path: Path,
) -> None:
    physical_target = skill_target.resolve()
    if is_filesystem_root(physical_target) or physical_target == Path.home().resolve():
        raise ValueError(f"Refusing dangerous skill target: {skill_target}")
    if skill_target.is_symlink():
        raise ValueError(f"Refusing to replace a symlinked skill target: {skill_target}")
    if skill_target.exists() and not skill_target.is_dir():
        raise ValueError(f"Skill target exists and is not a directory: {skill_target}")
    if skill_target.is_dir():
        skill_file = skill_target / "SKILL.md"
        if not skill_file.is_file():
            raise ValueError(
                "Refusing to replace a directory that is not a recognizable "
                f"{PACKAGE_NAME} installation: {skill_target}"
            )
        existing_name = installed_skill_name(skill_file)
        if existing_name != PACKAGE_NAME:
            raise ValueError(
                f"Refusing to replace unrelated skill {existing_name!r} at {skill_target}; "
                f"expected {PACKAGE_NAME!r}"
            )
    if codex_home.exists() and not codex_home.is_dir():
        raise ValueError(f"Codex home exists and is not a directory: {codex_home}")
    if agents_target.is_symlink():
        raise ValueError(f"Refusing a symlinked custom-agent directory: {agents_target}")
    if agents_target.exists() and not agents_target.is_dir():
        raise ValueError(
            f"Custom-agent target exists and is not a directory: {agents_target}"
        )
    if config_path.exists() and not config_path.is_file():
        raise ValueError(f"Config path exists and is not a file: {config_path}")

    protected = {
        "Codex home": codex_home,
        "custom-agent directory": agents_target,
        "config file": config_path,
    }
    for label, path in protected.items():
        try:
            nested = path.resolve().is_relative_to(physical_target)
        except ValueError:
            nested = False
        if nested:
            raise ValueError(
                f"Refusing skill target {skill_target}: it would contain and delete the {label} {path}"
            )


def unique_backup_dir(codex_home: Path, now: str) -> Path:
    root = codex_home / "backups"
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / f"{PACKAGE_NAME}-{now}"
    counter = 1
    while candidate.exists():
        candidate = root / f"{PACKAGE_NAME}-{now}-{counter}"
        counter += 1
    return candidate


def create_unified_backup(
    codex_home: Path,
    skill_target: Path,
    agents_target: Path,
    config_path: Path,
    now: str,
) -> Path | None:
    existing_roles = [
        agents_target / name for name in ALL_MANAGED_ROLE_FILES if (agents_target / name).is_file()
    ]
    anything_exists = skill_target.is_dir() or bool(existing_roles) or config_path.is_file()
    if not anything_exists:
        return None

    backup = unique_backup_dir(codex_home, now)
    backup.mkdir(parents=True)
    manifest: dict[str, object] = {
        "package_version": package_version(),
        "created_at_utc": now,
        "skill_source": str(skill_target),
        "agents_source": str(agents_target),
        "config_source": str(config_path),
        "roles": [path.name for path in existing_roles],
    }

    if skill_target.is_dir():
        shutil.copytree(skill_target, backup / "skill", symlinks=True)
    if existing_roles:
        (backup / "agents").mkdir()
        for path in existing_roles:
            shutil.copy2(path, backup / "agents" / path.name)
    if config_path.is_file():
        shutil.copy2(config_path, backup / "config.toml")

    (backup / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return backup


def stage_source() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    reject_package_symlinks(SOURCE)
    temp = tempfile.TemporaryDirectory(prefix=f"{PACKAGE_NAME}-")
    staged = Path(temp.name) / "package"
    staged.mkdir(parents=True)
    for source in included_files(SOURCE):
        relative = source.relative_to(SOURCE)
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return temp, staged


def install_skill(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.install-", dir=target.parent)
    )
    staged_target = stage_root / "payload"
    try:
        shutil.copytree(source, staged_target)
        if target.exists():
            if not target.is_dir() or target.is_symlink():
                raise ValueError(f"Skill target is not a replaceable directory: {target}")
            shutil.rmtree(target)
        os.replace(staged_target, target)
    finally:
        # Clean only the randomized directory created by this invocation.
        remove_path(stage_root)


def render_role(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    if not text.startswith(MANAGED_MARKER + "\n"):
        raise ValueError(f"Managed marker missing from {source.name}")
    parse_toml(text, source.name)
    return text


def select_install_mode(
    requested: str | None,
    *,
    input_stream: object = sys.stdin,
    output_stream: object = sys.stdout,
) -> str:
    if requested is not None:
        return requested
    if not getattr(input_stream, "isatty", lambda: False)():
        raise ValueError(
            "--mode is required when stdin is not interactive; choose lite or hard"
        )
    print("Choose codex-worker-orchestrator mode:", file=output_stream)
    for index, profile in enumerate(INSTALL_PROFILES.values(), start=1):
        print(f"  {index}. {profile.name}: {profile.description}", file=output_stream)
    while True:
        print("Mode [lite/hard]: ", end="", file=output_stream, flush=True)
        value = getattr(input_stream, "readline")().strip().lower()
        if value in {"1", "lite"}:
            return "lite"
        if value in {"2", "hard"}:
            return "hard"
        if not value:
            raise ValueError("installation mode was not selected")
        print("Enter lite, hard, 1, or 2.", file=output_stream)


def role_specs_for_mode(mode: str) -> dict[str, tuple[str, str, str, str]]:
    selected_names = set(INSTALL_PROFILES[mode].roles)
    return {
        spec.filename: ROLE_SPECS[spec.filename]
        for name, spec in ROLE_REGISTRY.items()
        if name in selected_names
    }

def validate_existing_role_safety(
    path: Path,
    expected_name: str,
    expected_sandbox: str,
    expected_model: str,
    expected_effort: str,
) -> None:
    text = path.read_text(encoding="utf-8")
    data = parse_toml(text, str(path))
    for key in ("name", "description", "developer_instructions"):
        if not isinstance(data.get(key), str) or not str(data[key]).strip():
            raise ValueError(f"Cannot keep {path}: required field `{key}` is missing")
    if data.get("name") != expected_name:
        raise ValueError(
            f"Cannot keep {path}: name is {data.get('name')!r}, expected {expected_name!r}"
        )
    if data.get("sandbox_mode") != expected_sandbox:
        raise ValueError(
            f"Cannot keep {path}: sandbox is {data.get('sandbox_mode')!r}, "
            f"expected {expected_sandbox!r}"
        )
    if data.get("model") != expected_model:
        raise ValueError(
            f"Cannot keep {path}: model is {data.get('model')!r}, expected {expected_model!r}"
        )
    if data.get("model_reasoning_effort") != expected_effort:
        raise ValueError(
            f"Cannot keep {path}: model reasoning effort is "
            f"{data.get('model_reasoning_effort')!r}, expected {expected_effort!r}"
        )
    if data.get("approval_policy") is not None:
        raise ValueError(f"Cannot keep {path}: role overrides approval_policy")
    instructions = str(data["developer_instructions"])
    for phrase in (
        "Do not invoke codex-worker-orchestrator",
        "Do not spawn agents",
        "The parent workflow owns",
        "If the brief supplies an output or report contract",
    ):
        if phrase not in instructions:
            raise ValueError(f"Cannot keep {path}: safety guard `{phrase}` is missing")
    if expected_sandbox == "read-only":
        if "Do not edit files" not in instructions:
            raise ValueError(f"Cannot keep {path}: read-only edit guard is missing")
        lowered = instructions.lower()
        if (
            "return the full structured report in your final response" not in lowered
            or "do not write a report file" not in lowered
        ):
            raise ValueError(
                f"Cannot keep {path}: read-only report contract must return the full "
                "structured report in the final response without writing a report file"
            )


def discover_custom_agents_by_name(agents_target: Path) -> dict[str, list[Path]]:
    """Index parseable top-level custom-agent TOML files by their declared name."""
    discovered: dict[str, list[Path]] = {}
    if not agents_target.is_dir():
        return discovered

    for path in sorted(agents_target.glob("*.toml"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        try:
            data = parse_toml(path.read_text(encoding="utf-8"), str(path))
        except (OSError, ValueError):
            # Canonical conflicts are validated below. An unrelated malformed file
            # cannot be indexed safely because it has no trustworthy identity.
            continue
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            discovered.setdefault(name, []).append(path)
    return discovered


def plan_role_actions(
    agents_target: Path,
    role_specs: dict[str, tuple[str, str, str, str]],
    keep_existing: bool,
    replace_existing: bool,
) -> list[RoleAction]:
    actions: list[RoleAction] = []
    discovered = discover_custom_agents_by_name(agents_target)
    selected_filenames = set(role_specs)
    for retired_name, canonical_filename in RETIRED_ROLE_NAMES.items():
        canonical_path = agents_target / canonical_filename
        for retired_path in discovered.get(retired_name, []):
            safely_removable = (
                retired_path == canonical_path
                and not retired_path.is_symlink()
                and retired_path.is_file()
                and retired_path.read_text(encoding="utf-8").startswith(
                    MANAGED_MARKER + "\n"
                )
            )
            if safely_removable:
                continue
            raise ValueError(
                f"Retired custom-agent name {retired_name!r} found at {retired_path}. "
                "Move or remove it explicitly before installing. The installer will "
                "not delete an alternate, symlinked, or unmanaged custom-agent file."
            )
    for filename, (
        expected_name,
        expected_sandbox,
        expected_model,
        expected_effort,
    ) in role_specs.items():
        destination = agents_target / filename
        matching_paths = discovered.get(expected_name, [])
        if len(matching_paths) > 1:
            locations = ", ".join(str(path) for path in matching_paths)
            raise ValueError(
                f"Duplicate custom-agent name {expected_name!r}: {locations}. "
                "Codex identifies a custom agent by its `name` field, not by filename. "
                "Remove or rename the duplicate role before installing."
            )
        if matching_paths and matching_paths[0] != destination:
            alternate = matching_paths[0]
            if keep_existing:
                validate_existing_role_safety(
                    alternate, expected_name, expected_sandbox, expected_model, expected_effort
                )
                actions.append(RoleAction(filename, alternate, "keep"))
                continue
            raise ValueError(
                f"Custom-agent name {expected_name!r} already exists at {alternate}; "
                f"the packaged filename would be {destination}. Codex uses the `name` "
                "field as the role identity. Use --keep-existing-agents when the "
                "existing role is compatible, or move/remove it explicitly. "
                "--replace-existing-agents never deletes an arbitrary alternate file."
            )
        if destination.is_symlink():
            if keep_existing:
                validate_existing_role_safety(
                    destination, expected_name, expected_sandbox, expected_model, expected_effort
                )
                actions.append(RoleAction(filename, destination, "keep"))
                continue
            raise ValueError(
                f"Symlinked custom agent will not be replaced: {destination}. "
                "Use --keep-existing-agents when the linked role is compatible, "
                "or remove the symlink explicitly before installing a package-managed role."
            )
        if destination.exists() and not destination.is_file():
            raise ValueError(f"Agent target exists and is not a file: {destination}")
        if not destination.exists():
            actions.append(RoleAction(filename, destination, "install"))
            continue
        if keep_existing:
            validate_existing_role_safety(
                destination, expected_name, expected_sandbox, expected_model, expected_effort
            )
            actions.append(RoleAction(filename, destination, "keep"))
            continue
        if replace_existing:
            actions.append(RoleAction(filename, destination, "install"))
            continue
        existing = destination.read_text(encoding="utf-8")
        if existing.startswith(MANAGED_MARKER + "\n"):
            actions.append(RoleAction(filename, destination, "install"))
            continue
        raise ValueError(
            f"Unmanaged custom agent already exists: {destination}. "
            "Use --keep-existing-agents after making it compatible, or "
            "--replace-existing-agents to back it up and replace it explicitly."
        )

    for filename in ALL_MANAGED_ROLE_FILES:
        if filename in selected_filenames:
            continue
        destination = agents_target / filename
        if destination.is_symlink() or not destination.is_file():
            continue
        existing = destination.read_text(encoding="utf-8")
        if existing.startswith(MANAGED_MARKER + "\n"):
            actions.append(RoleAction(filename, destination, "remove"))
    return actions

def install_roles(
    source_root: Path,
    agents_target: Path,
    actions: list[RoleAction],
) -> tuple[list[Path], list[Path], list[Path]]:
    role_source = source_root / "assets" / "agent-configs"
    agents_target.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    kept: list[Path] = []
    removed: list[Path] = []

    for role_action in actions:
        if role_action.action == "keep":
            kept.append(role_action.destination)
            continue
        if role_action.action == "remove":
            remove_path(role_action.destination)
            removed.append(role_action.destination)
            continue
        text = render_role(role_source / role_action.template_filename)
        atomic_write(role_action.destination, text)
        installed.append(role_action.destination)
    return installed, kept, removed

def table_header_pattern(table: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*\[{re.escape(table)}\]\s*(?:#.*)?(?:\r?\n)?$")


def has_explicit_table(text: str, table: str) -> bool:
    return any(table_header_pattern(table).match(line) for line in text.splitlines(keepends=True))


def root_region_end(lines: list[str]) -> int:
    header = re.compile(r"^\s*\[")
    for index, line in enumerate(lines):
        if header.match(line):
            return index
    return len(lines)


def root_uses_dotted_table(text: str, table: str) -> bool:
    lines = text.splitlines(keepends=True)
    end = root_region_end(lines)
    pattern = re.compile(rf"^\s*{re.escape(table)}\.[A-Za-z0-9_-]+\s*=")
    return any(pattern.match(line) for line in lines[:end])


def root_uses_inline_table(text: str, table: str) -> bool:
    lines = text.splitlines(keepends=True)
    end = root_region_end(lines)
    pattern = re.compile(rf"^\s*{re.escape(table)}\s*=\s*\{{")
    return any(pattern.match(line) for line in lines[:end])


def set_root_dotted_key(text: str, table: str, key: str, value: str) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    end = root_region_end(lines)
    key_line = re.compile(
        rf"^(\s*{re.escape(table)}\.{re.escape(key)}\s*=\s*)"
        rf"([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n)?$"
    )
    for index in range(end):
        match = key_line.match(lines[index])
        if not match:
            continue
        ending = match.group(4) or ""
        lines[index] = f"{match.group(1)}{value}{match.group(3)}{ending}"
        return "".join(lines)

    if end > 0 and not lines[end - 1].endswith(("\n", "\r")):
        lines[end - 1] += newline
    lines.insert(end, f"{table}.{key} = {value}{newline}")
    return "".join(lines)


def set_table_key(text: str, table: str, key: str, value: str) -> str:
    """Set one scalar key in an explicit TOML table while preserving other text."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    header = table_header_pattern(table)
    any_header = re.compile(r"^\s*\[")
    key_line = re.compile(
        rf"^(\s*{re.escape(key)}\s*=\s*)([^#\r\n]+?)(\s*(?:#.*)?)(\r?\n)?$"
    )

    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        if header.match(line):
            if start is not None:
                raise ValueError(f"Duplicate [{table}] tables in config.toml")
            start = index
            continue
        if start is not None and index > start and any_header.match(line):
            end = index
            break

    if start is None:
        updated = text
        if updated and not updated.endswith(("\n", "\r")):
            updated += newline
        if updated and not updated.endswith(newline * 2):
            updated += newline
        return updated + f"[{table}]{newline}{key} = {value}{newline}"

    for index in range(start + 1, end):
        match = key_line.match(lines[index])
        if not match:
            continue
        ending = match.group(4) or ""
        lines[index] = f"{match.group(1)}{value}{match.group(3)}{ending}"
        return "".join(lines)

    lines.insert(start + 1, f"{key} = {value}{newline}")
    return "".join(lines)


def set_config_key(text: str, table: str, key: str, value: str) -> str:
    if has_explicit_table(text, table):
        return set_table_key(text, table, key, value)
    if root_uses_dotted_table(text, table):
        return set_root_dotted_key(text, table, key, value)
    if root_uses_inline_table(text, table):
        raise ValueError(
            f"config.toml uses an inline `{table} = {{...}}` table. Convert it to "
            f"`[{table}]` or dotted keys before running the installer so comments and "
            "unrelated values are not rewritten."
        )
    parsed = parse_toml(text, "config.toml") if text else {}
    if table in parsed:
        raise ValueError(
            f"Cannot safely determine the textual representation of `{table}` in config.toml"
        )
    return set_table_key(text, table, key, value)


def build_config(
    original: str,
    max_threads: int | None,
    default_max_threads: int,
) -> str:
    original_config = parse_toml(original, "config.toml") if original else {}
    original_agents = original_config.get("agents", {})
    existing_thread_limit = isinstance(original_agents, dict) and any(
        key in original_agents
        for key in ("max_concurrent_threads_per_session", "max_threads")
    )
    effective_max_threads = max_threads
    if effective_max_threads is None and not existing_thread_limit:
        effective_max_threads = default_max_threads
    updated = set_config_key(original, "features", "multi_agent", "true")
    updated = set_config_key(updated, "agents", "enabled", "true")
    if effective_max_threads is not None:
        updated = set_config_key(
            updated,
            "agents",
            "max_concurrent_threads_per_session",
            str(effective_max_threads),
        )

    parsed = parse_toml(updated, "updated config.toml")
    features = parsed.get("features")
    agents = parsed.get("agents")
    if not isinstance(features, dict) or features.get("multi_agent") is not True:
        raise ValueError("Failed to set [features].multi_agent = true")
    if not isinstance(agents, dict) or agents.get("enabled") is not True:
        raise ValueError("Failed to set [agents].enabled = true")
    if (
        effective_max_threads is not None
        and agents.get("max_concurrent_threads_per_session") != effective_max_threads
    ):
        raise ValueError("Failed to set max_concurrent_threads_per_session")
    return updated

def rollback_installation(
    backup: Path | None,
    skill_target: Path,
    agents_target: Path,
    config_path: Path,
    role_actions: list[RoleAction],
    original_skill_exists: bool,
    original_role_files: set[str],
    original_config_exists: bool,
    config_was_in_scope: bool,
) -> list[str]:
    errors: list[str] = []

    try:
        remove_path(skill_target)
        if original_skill_exists:
            if backup is None or not (backup / "skill").is_dir():
                raise OSError("skill backup is missing")
            skill_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(backup / "skill", skill_target, symlinks=True)
    except (OSError, shutil.Error) as exc:
        errors.append(f"skill rollback failed: {exc}")

    for role_action in role_actions:
        if role_action.action == "keep":
            continue
        filename = role_action.template_filename
        destination = role_action.destination
        try:
            remove_path(destination)
            if filename in original_role_files:
                source = backup / "agents" / filename if backup is not None else None
                if source is None or not source.is_file():
                    raise OSError(f"backup missing for {filename}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        except (OSError, shutil.Error) as exc:
            errors.append(f"role rollback failed for {filename}: {exc}")

    if config_was_in_scope:
        try:
            remove_path(config_path)
            if original_config_exists:
                source = backup / "config.toml" if backup is not None else None
                if source is None or not source.is_file():
                    raise OSError("config backup is missing")
                config_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, config_path)
        except (OSError, shutil.Error) as exc:
            errors.append(f"config rollback failed: {exc}")

    return errors

def verify_installed_files(
    skill_target: Path,
    role_actions: list[RoleAction],
    config_path: Path,
    config_changed: bool,
) -> None:
    if not (skill_target / "SKILL.md").is_file():
        raise ValueError(f"Installed skill is missing SKILL.md: {skill_target}")
    installed_version = package_version(skill_target)
    expected_version = package_version()
    if installed_version != expected_version:
        raise ValueError(
            f"Installed VERSION is {installed_version!r}, expected {expected_version!r}"
        )
    for role_action in role_actions:
        if role_action.action == "remove":
            if role_action.destination.exists() or role_action.destination.is_symlink():
                raise ValueError(
                    f"Post-install check: managed role was not removed: {role_action.destination}"
                )
            continue
        expected_name, expected_sandbox, expected_model, expected_effort = ROLE_SPECS[
            role_action.template_filename
        ]
        validate_existing_role_safety(
            role_action.destination,
            expected_name,
            expected_sandbox,
            expected_model,
            expected_effort,
        )
    if config_changed:
        data = parse_toml(config_path.read_text(encoding="utf-8"), str(config_path))
        if not isinstance(data.get("features"), dict) or data["features"].get("multi_agent") is not True:
            raise ValueError("Post-install check: features.multi_agent is not true")
        if not isinstance(data.get("agents"), dict) or data["agents"].get("enabled") is not True:
            raise ValueError("Post-install check: agents.enabled is not true")

def display_command(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)

def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Install {PACKAGE_NAME} in Lite or Hard mode."
    )
    parser.add_argument("--mode", choices=tuple(INSTALL_PROFILES) or ("lite", "hard"))
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".agents" / "skills" / PACKAGE_NAME,
        help="Skill installation directory. Existing targets must contain SKILL.md.",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        help="Codex home directory. Defaults to CODEX_HOME or ~/.codex.",
    )
    parser.add_argument("--agents-target", type=Path, help="Override custom-agent directory.")
    parser.add_argument("--config", type=Path, help="Override config.toml path.")
    parser.add_argument(
        "--max-threads",
        type=int,
        help=(
            "Set agents.max_concurrent_threads_per_session; an existing value is "
            "preserved when omitted, otherwise the selected profile default is used."
        ),
    )
    conflict = parser.add_mutually_exclusive_group()
    conflict.add_argument(
        "--keep-existing-agents",
        action="store_true",
        help="Keep compatible custom agents with the expected TOML name, even under alternate filenames.",
    )
    conflict.add_argument(
        "--replace-existing-agents",
        action="store_true",
        help="Explicitly replace unmanaged agents at packaged canonical filenames after backup.",
    )
    parser.add_argument("--skip-agents", action="store_true", help="Install only the skill.")
    parser.add_argument(
        "--no-config-change",
        action="store_true",
        help="Do not write [features] or [agents] flags.",
    )
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args()

    if ROLE_REGISTRY_ERROR is not None:
        return fail(f"Invalid role registry: {ROLE_REGISTRY_ERROR}")
    if PROFILE_REGISTRY_ERROR is not None:
        return fail(f"Invalid install profiles: {PROFILE_REGISTRY_ERROR}")
    try:
        mode = select_install_mode(args.mode)
    except ValueError as exc:
        return fail(str(exc))
    profile = INSTALL_PROFILES[mode]
    selected_specs = role_specs_for_mode(mode)

    if args.max_threads is not None and args.max_threads < 1:
        return fail("--max-threads must be at least 1")
    if args.no_config_change and args.max_threads is not None:
        return fail("--max-threads cannot be used with --no-config-change")
    if args.skip_agents and (args.keep_existing_agents or args.replace_existing_agents):
        return fail(
            "--keep-existing-agents and --replace-existing-agents cannot be used "
            "with --skip-agents"
        )

    try:
        current_package_version = package_version()
    except ValueError as exc:
        return fail(str(exc))

    if not args.no_validate:
        result = subprocess.run(
            [sys.executable, str(SOURCE / "scripts" / "validate_skill.py")], check=False
        )
        if result.returncode != 0:
            return result.returncode

    codex_home = normalized(args.codex_home or default_codex_home())
    skill_target = normalized(args.target)
    requested_agents_target = normalized(args.agents_target or codex_home / "agents")
    requested_config_path = normalized(args.config or codex_home / "config.toml")
    now = stamp()
    backup: Path | None = None
    installed_roles: list[Path] = []
    kept_roles: list[Path] = []
    removed_roles: list[Path] = []

    try:
        agents_target = resolve_existing_symlink(
            requested_agents_target, "custom-agent directory", "directory"
        )
        config_path = resolve_existing_symlink(
            requested_config_path, "config file", "file"
        )
        validate_install_paths(codex_home, skill_target, agents_target, config_path)
        original_config_exists = config_path.is_file()
        original_config = config_path.read_text(encoding="utf-8") if original_config_exists else ""
        updated_config = original_config
        if not args.no_config_change:
            updated_config = build_config(
                original_config,
                args.max_threads,
                profile.default_max_threads,
            )
        config_changed = not args.no_config_change and updated_config != original_config

        staged_context, staged_source = stage_source()
        try:
            role_actions = (
                []
                if args.skip_agents
                else plan_role_actions(
                    agents_target,
                    selected_specs,
                    args.keep_existing_agents,
                    args.replace_existing_agents,
                )
            )
            original_skill_exists = skill_target.is_dir()
            original_role_files = {
                filename
                for filename in ALL_MANAGED_ROLE_FILES
                if (agents_target / filename).is_file()
            }
            backup = create_unified_backup(
                codex_home, skill_target, agents_target, config_path, now
            )
            try:
                install_skill(staged_source, skill_target)
                if not args.skip_agents:
                    installed_roles, kept_roles, removed_roles = install_roles(
                        staged_source,
                        agents_target,
                        role_actions,
                    )
                if config_changed:
                    atomic_write(config_path, updated_config)
                verify_installed_files(
                    skill_target,
                    role_actions,
                    config_path,
                    config_changed,
                )
            except (OSError, ValueError) as exc:
                rollback_errors = rollback_installation(
                    backup,
                    skill_target,
                    agents_target,
                    config_path,
                    role_actions,
                    original_skill_exists,
                    original_role_files,
                    original_config_exists,
                    config_changed,
                )
                if rollback_errors:
                    message = f"Installation failed. Rollback incomplete: {exc}"
                    message += "; " + "; ".join(rollback_errors)
                    if backup is not None:
                        message += f"; manual backup: {backup}"
                else:
                    message = f"Installation failed. Rollback completed: {exc}"
                raise ValueError(message) from exc
        finally:
            staged_context.cleanup()
    except (OSError, ValueError) as exc:
        return fail(str(exc))

    print(f"Package version: {current_package_version}")
    print(f"Installation mode: {mode}")
    print(f"Skill installed: {skill_target}")
    if args.skip_agents:
        print("Custom agents: skipped")
    else:
        print(f"Custom agents installed: {len(installed_roles)} in {agents_target}")
        for path in installed_roles:
            print(f"  + {path.name}")
        for path in kept_roles:
            print(f"  = kept {path.name}")
        for path in removed_roles:
            print(f"  - removed managed {path.name}")
    if args.no_config_change:
        print(f"Config unchanged: {config_path}")
    else:
        print(f"Multi-agent flags enabled: {config_path}")
        if args.max_threads is not None:
            print(f"Maximum spawned threads: {args.max_threads}")
        else:
            print(f"Profile default threads when unset: {profile.default_max_threads}")
    if backup is not None:
        print(f"Backup: {backup}")
    doctor = [
        sys.executable,
        str(skill_target / "scripts" / "preflight.py"),
        "--codex-home",
        str(codex_home),
        "--skill",
        str(skill_target / "SKILL.md"),
    ]
    print("Invoke: $codex-worker-orchestrator <task>")
    print(f"Run doctor: {display_command(doctor)}")
    print("Restart Codex if the skill or custom roles are not discovered immediately.")
    print("Model and effort availability must be confirmed in the local /model picker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
