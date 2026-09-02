#!/usr/bin/env python3
"""Inspect the installed orchestrator, role files, and locally visible Codex state."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import tomllib
from pathlib import Path

from orchestrator_lib import (
    is_link_junction_or_reparse,
    load_capability_packs,
    load_install_profiles,
    load_role_registry,
)

PACKAGE_NAME = "codex-worker-orchestrator"
PARALLEL_COMPANION = "parallelizing-subagent-plans"
PARALLEL_COMPANION_MAJOR = 2
VERSION_PATTERN = re.compile(r"^([0-9])$")

RUNTIME_MODEL_STATUS = "unverified; confirm with /model in Codex"
RUNTIME_SPAWN_SCHEMA = "unverified; inspect the live Codex tool schema"
RUNTIME_AGENT_ALLOWLIST = "unverified; confirm with a fresh spawn"
RUNTIME_PERMISSION_MODE = (
    "unverified; live parent/session overrides and managed policy may supersede config and role defaults"
)
RUNTIME_SKILLS = "unverified; inspect the skills loaded in the live Codex session"
RUNTIME_THREAD_SLOTS = "unverified; inspect active agent threads in the live Codex session"
SKILL_SCAN_EXCLUDES = {".git", ".pytest_cache", "__pycache__", "_publish"}


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def skill_frontmatter_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        return None
    names: list[str] = []
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() == "name":
            names.append(value.strip().strip('"').strip("'"))
    return names[0] if len(names) == 1 and names[0] else None


def read_package_version(skill_path: Path) -> str:
    version_path = skill_path.parent / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Package VERSION is unreadable: {version_path}: {exc}") from exc
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Package VERSION must contain one digit: {version!r}")
    return version


def absolute_lexical(path: Path) -> Path:
    """Return an absolute normalized path without resolving filesystem links."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def trusted_discovery_root(candidate: Path, trust_anchor: Path) -> Path | None:
    """Reject scan roots redirected by a link/reparse component."""

    root = absolute_lexical(candidate)
    anchor = absolute_lexical(trust_anchor)
    try:
        relative = root.relative_to(anchor)
    except ValueError:
        return None

    current = anchor
    components = [anchor]
    for part in relative.parts:
        current /= part
        components.append(current)
    if any(is_link_junction_or_reparse(component) for component in components):
        return None
    return root


def discover_parallel_companion(project: Path, codex_home: Path) -> dict[str, object]:
    """Discover the effective project/global compiler with project precedence."""

    project = absolute_lexical(project)
    codex_home = absolute_lexical(codex_home)
    user_home = absolute_lexical(Path.home())
    candidates: list[tuple[str, Path, Path]] = [
        ("project", project / ".codex" / "skills" / PARALLEL_COMPANION, project),
        ("project", project / ".agents" / "skills" / PARALLEL_COMPANION, project),
        ("project", project / PARALLEL_COMPANION, project),
        ("global", codex_home / "skills" / PARALLEL_COMPANION, codex_home),
        (
            "global",
            user_home / ".codex" / "skills" / PARALLEL_COMPANION,
            user_home,
        ),
        (
            "global",
            user_home / ".agents" / "skills" / PARALLEL_COMPANION,
            user_home,
        ),
    ]
    seen: set[Path] = set()
    for scope, candidate, trust_anchor in candidates:
        trusted = trusted_discovery_root(candidate, trust_anchor)
        if trusted is None or trusted in seen:
            continue
        seen.add(trusted)
        skill_file = trusted / "SKILL.md"
        version_path = trusted / "VERSION"
        if (
            is_link_junction_or_reparse(skill_file)
            or is_link_junction_or_reparse(version_path)
            or not skill_file.is_file()
        ):
            continue
        detected_name = skill_frontmatter_name(skill_file)
        try:
            version = version_path.read_text(encoding="utf-8").strip()
        except OSError:
            version = None
        version_match = VERSION_PATTERN.fullmatch(version or "")
        compatible = (
            detected_name == PARALLEL_COMPANION
            and version_match is not None
            and int(version_match.group(1)) == PARALLEL_COMPANION_MAJOR
        )
        if detected_name != PARALLEL_COMPANION:
            reason = f"frontmatter name is {detected_name!r}"
        elif version_match is None:
            reason = "VERSION is missing or invalid"
        elif not compatible:
            reason = (
                f"version {version} is incompatible; required major is "
                f"{PARALLEL_COMPANION_MAJOR}"
            )
        else:
            reason = "compatible project/global companion discovered"
        return {
            "name": PARALLEL_COMPANION,
            "found": True,
            "compatible": compatible,
            "scope": scope,
            "path": str(trusted),
            "version": version,
            "reason": reason,
        }
    return {
        "name": PARALLEL_COMPANION,
        "found": False,
        "compatible": False,
        "scope": None,
        "path": None,
        "version": None,
        "reason": "not found in project or global skill roots",
    }


def _skill_files(root: Path, *, recursive: bool) -> list[Path]:
    """Find SKILL.md files without following links, junctions, or reparse points."""
    if is_link_junction_or_reparse(root) or not root.is_dir():
        return []
    found: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as scanned:
                entries = sorted(scanned, key=lambda entry: entry.name.lower())
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if (
                entry.is_symlink()
                or getattr(path, "is_junction", lambda: False)()
                or bool(getattr(info, "st_file_attributes", 0) & 0x400)
            ):
                continue
            if stat.S_ISREG(info.st_mode) and entry.name == "SKILL.md":
                if directory != root:
                    found.append(path)
            elif stat.S_ISDIR(info.st_mode) and entry.name not in SKILL_SCAN_EXCLUDES:
                if recursive or directory == root:
                    pending.append(path)
        if not recursive and directory != root:
            pending.clear()
    return sorted(found)


def discover_skill_inventory(
    project: Path,
    codex_home: Path,
    skill_path: Path,
    *,
    include_default_globals: bool,
) -> list[str]:
    """Discover project/global capability skills with project roots first."""
    project = absolute_lexical(project)
    codex_home = absolute_lexical(codex_home)
    package_neighbor_root = absolute_lexical(skill_path).parent.parent
    user_home = absolute_lexical(Path.home())
    root_specs: list[tuple[Path, Path, bool]] = [
        (project / ".codex" / "skills", project, True),
        (project / ".agents" / "skills", project, True),
        (project, project, False),
        (codex_home / "skills", codex_home, True),
        (package_neighbor_root, package_neighbor_root, False),
    ]
    if include_default_globals:
        root_specs.extend(
            [
                (user_home / ".codex" / "skills", user_home, True),
                (user_home / ".agents" / "skills", user_home, True),
                (user_home / ".codex" / "plugins" / "cache", user_home, True),
            ]
        )
    seen_roots: set[Path] = set()
    discovered: set[str] = set()
    for candidate, trust_anchor, recursive in root_specs:
        root = trusted_discovery_root(candidate, trust_anchor)
        if root is None or root in seen_roots:
            continue
        seen_roots.add(root)
        for skill_file in _skill_files(root, recursive=recursive):
            name = skill_frontmatter_name(skill_file)
            if name and name != PACKAGE_NAME:
                discovered.add(name)

    package_root = skill_path.parent
    try:
        alternatives = {
            alternative
            for pack in load_capability_packs(package_root).values()
            for alternative in pack.skill_alternatives
        }
    except ValueError:
        alternatives = set()
    for alternative in alternatives:
        short_name = alternative.rsplit(":", 1)[-1]
        if short_name in discovered:
            discovered.add(alternative)
    return sorted(discovered)


def configured_skill_state(
    config: dict[str, object],
    config_path: Path,
    skill_path: Path,
) -> tuple[bool | None, list[str], list[str], list[str]]:
    """Return effective explicit skill override and diagnostics for this skill."""
    errors: list[str] = []
    warnings: list[str] = []
    matched_paths: list[str] = []
    raw_skills = config.get("skills")
    if raw_skills is None:
        return None, matched_paths, errors, warnings
    if not isinstance(raw_skills, dict):
        errors.append("[skills] must be a TOML table")
        return None, matched_paths, errors, warnings
    raw_entries = raw_skills.get("config")
    if raw_entries is None:
        return None, matched_paths, errors, warnings
    if not isinstance(raw_entries, list):
        errors.append("skills.config must be an array of tables")
        return None, matched_paths, errors, warnings

    target_file = skill_path.resolve()
    target_directory = target_file.parent
    matches: list[tuple[Path, bool]] = []
    for index, raw_entry in enumerate(raw_entries, start=1):
        label = f"skills.config entry {index}"
        if not isinstance(raw_entry, dict):
            errors.append(f"{label} must be a TOML table")
            continue
        raw_path = raw_entry.get("path")
        enabled = raw_entry.get("enabled")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"{label}.path must be a non-empty string")
            continue
        if not isinstance(enabled, bool):
            errors.append(f"{label}.enabled must be boolean")
            continue
        configured_path = Path(raw_path).expanduser()
        if not configured_path.is_absolute():
            configured_path = config_path.parent / configured_path
        configured_path = configured_path.resolve()
        if configured_path in {target_file, target_directory}:
            matched_paths.append(str(configured_path))
            matches.append((configured_path, enabled))

    if not matches:
        return None, matched_paths, errors, warnings
    effective = matches[-1][1]
    if len(matches) > 1:
        values = {enabled for _, enabled in matches}
        if len(values) > 1:
            warnings.append(
                "Multiple skills.config entries target this skill with conflicting "
                "enabled values; the last matching entry is treated as effective"
            )
        else:
            warnings.append(
                "Multiple skills.config entries target this skill; remove duplicates "
                "to keep discovery unambiguous"
            )
    if effective is False:
        errors.append(
            f"Skill {PACKAGE_NAME!r} is explicitly disabled by [[skills.config]]"
        )
    return effective, matched_paths, errors, warnings


def scan_custom_agents(
    agents_dir: Path,
) -> tuple[
    dict[Path, tuple[str | None, dict[str, object] | None, str | None]],
    dict[str, list[Path]],
]:
    """Read top-level role files once and index parseable agents by declared name."""
    records: dict[Path, tuple[str | None, dict[str, object] | None, str | None]] = {}
    by_name: dict[str, list[Path]] = {}
    if not agents_dir.is_dir():
        return records, by_name

    for path in sorted(agents_dir.glob("*.toml"), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        try:
            role_text = path.read_text(encoding="utf-8")
            data = tomllib.loads(role_text)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            records[path] = (None, None, str(exc))
            continue
        records[path] = (role_text, data, None)
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            by_name.setdefault(name, []).append(path)
    return records, by_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Codex orchestrator installation.")
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--agents-target", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
        help="Project root used for project-before-global companion discovery.",
    )
    parser.add_argument(
        "--skill",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "SKILL.md",
        help="Skill entrypoint to inspect. Defaults to the package containing this helper.",
    )
    parser.add_argument("--allow-missing-codex", action="store_true")
    parser.add_argument(
        "--codex-executable",
        type=Path,
        help=(
            "Explicit absolute Codex executable to probe. Unqualified PATH lookup is "
            "intentionally disabled to prevent project-local executable shadowing."
        ),
    )
    parser.add_argument(
        "--codex-version-timeout",
        type=float,
        default=10.0,
        help="Seconds allowed for `codex --version` before the probe fails.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.codex_version_timeout <= 0:
        parser.error("--codex-version-timeout must be greater than zero")

    home_input = absolute_lexical(args.codex_home or default_codex_home())
    home = home_input.resolve()
    agents_dir = (args.agents_target or home / "agents").expanduser().resolve()
    config_path = (args.config or home / "config.toml").expanduser().resolve()
    skill_path = args.skill.expanduser().resolve()
    project = absolute_lexical(args.project)

    errors: list[str] = []
    warnings: list[str] = []
    roles: list[dict[str, object]] = []
    package_version: str | None = None
    expected_roles = {}
    expected_profiles = {}

    if not skill_path.is_file():
        errors.append(f"Skill not found: {skill_path}")
    else:
        detected_skill_name = skill_frontmatter_name(skill_path)
        if detected_skill_name != "codex-worker-orchestrator":
            errors.append(
                "Skill frontmatter name is "
                f"{detected_skill_name!r}, expected 'codex-worker-orchestrator': {skill_path}"
            )
        try:
            package_version = read_package_version(skill_path)
        except ValueError as exc:
            errors.append(str(exc))
        try:
            expected_roles = load_role_registry(skill_path.parent)
            expected_profiles = load_install_profiles(skill_path.parent, expected_roles)
        except ValueError as exc:
            errors.append(f"Invalid installed role/profile registry: {exc}")

    agent_records, agents_by_name = scan_custom_agents(agents_dir)

    installed_known_roles = set(agents_by_name) & set(expected_roles)
    matching_profiles = [
        profile.name
        for profile in expected_profiles.values()
        if set(profile.roles) == installed_known_roles
    ]
    install_mode: str | None = matching_profiles[0] if len(matching_profiles) == 1 else None
    if expected_profiles and install_mode is None:
        errors.append(
            "Installed package role set does not match the Lite or Hard profile: "
            + (", ".join(sorted(installed_known_roles)) or "no registered roles found")
        )
    active_role_names = (
        list(expected_profiles[install_mode].roles)
        if install_mode is not None
        else list(expected_roles)
    )

    for expected_name in active_role_names:
        spec = expected_roles[expected_name]
        filename = spec.filename
        model = spec.model
        effort = spec.model_reasoning_effort
        sandbox = spec.sandbox_mode
        expected_path = agents_dir / filename
        role_errors: list[str] = []
        role_warnings: list[str] = []
        row: dict[str, object] = {
            "name": expected_name,
            "expected_file": str(expected_path),
            "file": str(expected_path),
            "matching_files": [],
            "exists": False,
            "discovered_by_name": False,
            "managed_by_package": None,
            "model": None,
            "effort": None,
            "sandbox": None,
            "valid": False,
            "errors": role_errors,
            "warnings": role_warnings,
        }

        matching_paths = agents_by_name.get(expected_name, [])
        row["matching_files"] = [str(path) for path in matching_paths]
        if len(matching_paths) > 1:
            row["exists"] = True
            row["file"] = str(matching_paths[0])
            row["discovered_by_name"] = any(
                path != expected_path for path in matching_paths
            )
            locations = ", ".join(str(path) for path in matching_paths)
            message = (
                f"Duplicate custom-agent name {expected_name!r}: {locations}. "
                "Codex role identity comes from the `name` field, not the filename."
            )
            role_errors.append(message)
            errors.append(message)
            roles.append(row)
            continue

        if matching_paths:
            path = matching_paths[0]
            row["file"] = str(path)
            row["exists"] = True
            row["discovered_by_name"] = path != expected_path
            if path != expected_path:
                role_warnings.append(
                    f"{path.name}: role {expected_name!r} was discovered by name in a "
                    f"noncanonical file; packaged filename is {filename}"
                )
            role_text, data, parse_error = agent_records[path]
        else:
            path = expected_path
            canonical_record = agent_records.get(path)
            if canonical_record is None:
                message = f"Missing custom agent named {expected_name!r} in {agents_dir}"
            elif canonical_record[2] is not None:
                message = f"Invalid custom agent {filename}: {canonical_record[2]}"
            else:
                declared = canonical_record[1].get("name") if canonical_record[1] else None
                message = (
                    f"Missing custom agent named {expected_name!r}; canonical file "
                    f"{path} declares {declared!r}"
                )
            role_errors.append(message)
            errors.append(message)
            roles.append(row)
            continue

        if parse_error is not None or role_text is None or data is None:
            message = f"Invalid custom agent {path.name}: {parse_error or 'unknown parse error'}"
            role_errors.append(message)
            errors.append(message)
            roles.append(row)
            continue

        managed_by_package = role_text.startswith(
            "# managed-by: codex-worker-orchestrator\n"
        )
        row.update(
            managed_by_package=managed_by_package,
            model=data.get("model"),
            effort=data.get("model_reasoning_effort"),
            sandbox=data.get("sandbox_mode"),
        )
        if not managed_by_package:
            role_warnings.append(
                f"{path.name}: user-managed role; verify its custom model and instructions deliberately"
            )

        required = ("name", "description", "developer_instructions")
        missing = [
            key
            for key in required
            if not isinstance(data.get(key), str) or not str(data.get(key)).strip()
        ]
        if missing:
            role_errors.append(f"{path.name}: missing {', '.join(missing)}")
        if data.get("name") != expected_name:
            role_errors.append(
                f"{path.name}: name is {data.get('name')!r}, expected {expected_name!r}"
            )
        if data.get("model") != model:
            role_warnings.append(
                f"{path.name}: model override {data.get('model')!r}, packaged default is {model!r}"
            )
        if data.get("model_reasoning_effort") != effort:
            role_warnings.append(
                f"{path.name}: effort override {data.get('model_reasoning_effort')!r}, packaged default is {effort!r}"
            )
        if data.get("sandbox_mode") != sandbox:
            role_errors.append(
                f"{path.name}: sandbox is {data.get('sandbox_mode')!r}, expected {sandbox!r}"
            )
        if data.get("sandbox_mode") == "danger-full-access":
            role_errors.append(f"{path.name}: danger-full-access is forbidden")
        if data.get("approval_policy") is not None:
            role_errors.append(f"{path.name}: must not override approval_policy")

        instructions = str(data.get("developer_instructions", ""))
        if "Do not invoke codex-worker-orchestrator" not in instructions:
            role_errors.append(f"{path.name}: orchestrator recursion guard missing")
        if "Do not spawn agents" not in instructions:
            role_errors.append(f"{path.name}: recursive-spawn guard missing")
        if "The parent workflow owns" not in instructions:
            role_errors.append(f"{path.name}: parent workflow ownership guard missing")
        if "If the brief supplies an output or report contract" not in instructions:
            role_errors.append(f"{path.name}: parent report-contract guard missing")
        if sandbox == "read-only":
            if "Do not edit files" not in instructions:
                role_errors.append(f"{path.name}: read-only edit guard missing")
            lowered = instructions.lower()
            if (
                "return the full structured report in your final response" not in lowered
                or "do not write a report file" not in lowered
            ):
                role_errors.append(
                    f"{path.name}: read-only report contract must return the full "
                    "structured report in the final response without writing a report file"
                )

        errors.extend(role_errors)
        warnings.extend(role_warnings)
        row["valid"] = not role_errors
        roles.append(row)

    config: dict[str, object] = {}
    if config_path.is_file():
        try:
            config = load_toml(config_path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"Invalid config.toml: {exc}")
    else:
        warnings.append(f"No config.toml at {config_path}; Codex defaults apply")

    skill_enabled_in_config, skill_config_matches, skill_config_errors, skill_config_warnings = (
        configured_skill_state(config, config_path, skill_path)
    )
    errors.extend(skill_config_errors)
    warnings.extend(skill_config_warnings)

    raw_features = config.get("features", {}) if isinstance(config, dict) else {}
    raw_agents = config.get("agents", {}) if isinstance(config, dict) else {}
    if raw_features is not None and not isinstance(raw_features, dict):
        errors.append("[features] must be a TOML table")
        features: dict[str, object] = {}
    else:
        features = raw_features if isinstance(raw_features, dict) else {}
    if raw_agents is not None and not isinstance(raw_agents, dict):
        errors.append("[agents] must be a TOML table")
        agents: dict[str, object] = {}
    else:
        agents = raw_agents if isinstance(raw_agents, dict) else {}

    multi_agent = features.get("multi_agent", True)
    agents_enabled = agents.get("enabled", True)
    max_threads = agents.get("max_concurrent_threads_per_session")
    if max_threads is None:
        max_threads = agents.get("max_threads")

    if not isinstance(multi_agent, bool):
        errors.append("features.multi_agent must be boolean")
    elif multi_agent is False:
        errors.append("[features].multi_agent is false")
    if not isinstance(agents_enabled, bool):
        errors.append("agents.enabled must be boolean")
    elif agents_enabled is False:
        errors.append("[agents].enabled is false")
    if max_threads is not None and (
        isinstance(max_threads, bool)
        or not isinstance(max_threads, int)
        or max_threads < 1
    ):
        errors.append(
            "agents.max_concurrent_threads_per_session must be a positive integer"
        )

    configured_approval_policy = config.get("approval_policy") if isinstance(config, dict) else None
    configured_sandbox_mode = config.get("sandbox_mode") if isinstance(config, dict) else None

    parallel_companion = discover_parallel_companion(project, home_input)
    discovered_skill_names = discover_skill_inventory(
        project,
        home_input,
        skill_path,
        include_default_globals=True,
    )
    if parallel_companion["found"] and PARALLEL_COMPANION not in discovered_skill_names:
        discovered_skill_names.append(PARALLEL_COMPANION)
        discovered_skill_names.sort()
    skill_inventory = {
        "names": discovered_skill_names,
        "incompatible": (
            [PARALLEL_COMPANION]
            if parallel_companion["found"] and not parallel_companion["compatible"]
            else []
        ),
    }
    if parallel_companion["found"] and not parallel_companion["compatible"]:
        warnings.append(
            f"Parallel companion is incompatible: {parallel_companion['reason']}"
        )

    codex_executable: str | None = None
    codex_version: str | None = None
    if args.codex_executable is not None:
        candidate = args.codex_executable.expanduser()
        if not candidate.is_absolute():
            errors.append("--codex-executable must be an absolute path")
        else:
            try:
                resolved_candidate = candidate.resolve(strict=True)
            except OSError as exc:
                errors.append(f"Codex executable cannot be resolved: {candidate}: {exc}")
            else:
                if not resolved_candidate.is_file():
                    errors.append(f"Codex executable is not a file: {resolved_candidate}")
                else:
                    codex_executable = str(resolved_candidate)
    if codex_executable is not None:
        try:
            result = subprocess.run(
                [codex_executable, "--version"],
                text=True,
                capture_output=True,
                check=False,
                timeout=args.codex_version_timeout,
            )
        except subprocess.TimeoutExpired:
            errors.append(
                "codex --version timed out after "
                f"{args.codex_version_timeout:g} seconds"
            )
        else:
            if result.returncode == 0:
                codex_version = (result.stdout or result.stderr).strip()
            else:
                errors.append(f"codex --version failed with exit {result.returncode}")
    else:
        warnings.append(
            "Codex executable was not probed; pass --codex-executable with a trusted "
            "absolute path to verify its version. Runtime checks remain unverified."
        )

    payload = {
        "ok": not errors,
        "package_version": package_version,
        "install_mode": install_mode,
        "codex_home": str(home),
        "skill": str(skill_path),
        "agents_dir": str(agents_dir),
        "config": str(config_path),
        "codex_executable": codex_executable,
        "codex_version": codex_version,
        "codex_version_timeout_seconds": args.codex_version_timeout,
        "skill_enabled_in_config": skill_enabled_in_config,
        "skill_config_matches": skill_config_matches,
        "multi_agent": multi_agent,
        "agents_enabled": agents_enabled,
        "max_threads": max_threads,
        "configured_approval_policy": configured_approval_policy,
        "configured_sandbox_mode": configured_sandbox_mode,
        "parallel_companion": parallel_companion,
        "skill_inventory": skill_inventory,
        "roles": roles,
        "errors": errors,
        "warnings": warnings,
        "runtime_model_availability": RUNTIME_MODEL_STATUS,
        "runtime_spawn_schema": RUNTIME_SPAWN_SCHEMA,
        "runtime_agent_allowlist": RUNTIME_AGENT_ALLOWLIST,
        "runtime_permission_mode": RUNTIME_PERMISSION_MODE,
        "runtime_skill_discovery": RUNTIME_SKILLS,
        "runtime_free_thread_slots": RUNTIME_THREAD_SLOTS,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Codex home: {home}")
        print(f"Package version: {package_version or 'INVALID'}")
        print(f"Install mode: {install_mode or 'INVALID'}")
        print(f"Skill: {'OK' if skill_path.is_file() else 'MISSING'} {skill_path}")
        skill_state = (
            "enabled"
            if skill_enabled_in_config is True
            else "disabled"
            if skill_enabled_in_config is False
            else "default (no explicit override)"
        )
        print(f"Skill config: {skill_state}")
        print(
            "Multi-agent config: "
            f"features.multi_agent={multi_agent}, agents.enabled={agents_enabled}, "
            f"max_threads={max_threads if max_threads is not None else 'default'}"
        )
        print(
            "Configured permissions: "
            f"approval_policy={configured_approval_policy or 'default'}, "
            f"sandbox_mode={configured_sandbox_mode or 'default'}"
        )
        companion_state = (
            "compatible"
            if parallel_companion["compatible"]
            else "incompatible"
            if parallel_companion["found"]
            else "absent"
        )
        print(
            f"Parallel companion: {companion_state} "
            f"({parallel_companion['path'] or parallel_companion['reason']})"
        )
        print("Custom agents:")
        for role in roles:
            status = "OK" if role["valid"] else "FAIL"
            file_note = Path(str(role["file"])).name
            print(
                f"  {status:4} {role['name']} [{file_note}]: "
                f"{role['model']} / {role['effort']} / {role['sandbox']}"
            )
        if codex_version:
            print(f"Codex: {codex_version}")
        elif codex_executable:
            print(f"Codex: {codex_executable} (version unavailable)")
        else:
            print("Codex: not found")
        for warning in warnings:
            print(f"WARN: {warning}")
        for error in errors:
            print(f"FAIL: {error}")
        print(f"Runtime models: {RUNTIME_MODEL_STATUS}")
        print(f"Runtime spawn schema: {RUNTIME_SPAWN_SCHEMA}")
        print(f"Runtime agent allowlist: {RUNTIME_AGENT_ALLOWLIST}")
        print(f"Runtime permission mode: {RUNTIME_PERMISSION_MODE}")
        print(f"Runtime skills: {RUNTIME_SKILLS}")
        print(f"Runtime thread slots: {RUNTIME_THREAD_SLOTS}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
