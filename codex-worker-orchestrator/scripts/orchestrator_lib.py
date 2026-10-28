#!/usr/bin/env python3
"""Shared deterministic configuration, schema, path, and JSON helpers."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


@dataclass(frozen=True)
class RoleSpec:
    name: str
    filename: str
    description: str
    model: str
    model_reasoning_effort: str
    model_reasoning_summary: str
    model_verbosity: str
    sandbox_mode: str
    mutation_class: str
    intents: tuple[str, ...]
    cost_rank: int
    fallbacks: tuple[str, ...]


@dataclass(frozen=True)
class InstallProfile:
    name: str
    description: str
    roles: tuple[str, ...]
    default_max_threads: int


@dataclass(frozen=True)
class CapabilityPack:
    name: str
    description: str
    skill_alternatives: tuple[str, ...]


ROLE_FIELDS = {
    "name": str,
    "filename": str,
    "description": str,
    "model": str,
    "model_reasoning_effort": str,
    "model_reasoning_summary": str,
    "model_verbosity": str,
    "sandbox_mode": str,
    "mutation_class": str,
    "intents": list,
    "cost_rank": int,
    "fallbacks": list,
}

REPOSITORY_ONLY = {
    Path("AUDIT.md"),
    Path("VERIFICATION.md"),
    Path("assets/agent-configs/README.md"),
    Path("scripts/build_archive.py"),
    Path("scripts/prepare_publish.py"),
    Path("codex-global-subagents-install-en.md"),
    Path("codex-global-subagents-install-ru.md"),
    Path("codex-subagents-install-report-ru.md"),
}

RUNTIME_FILES = {
    Path("SKILL.md"),
    Path("VERSION"),
    Path("INSTALL.md"),
    Path("agents/openai.yaml"),
    Path("config/capability-packs.toml"),
    Path("config/install-profiles.toml"),
    Path("config/roles.toml"),
    Path("config/routing-policy.toml"),
    Path("references/dispatch-contract.md"),
    Path("references/routing-matrix.md"),
    Path("schemas/agent-report.schema.json"),
    Path("schemas/context-manifest.schema.json"),
    Path("schemas/route-request.schema.json"),
    Path("schemas/route.schema.json"),
    Path("schemas/run-state.schema.json"),
    Path("schemas/task-packet.schema.json"),
    Path("scripts/install.py"),
    Path("scripts/orchestrator_lib.py"),
    Path("scripts/preflight.py"),
    Path("scripts/resolve_roles.py"),
    Path("scripts/run_state.py"),
    Path("scripts/validate_skill.py"),
}

RUNTIME_EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".tox",
    ".nox",
    ".git",
    ".backups",
    "backups",
    "htmlcov",
    "tests",
    ".venv",
    "venv",
}
RUNTIME_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
RUNTIME_EXCLUDED_NAMES = {".DS_Store", ".coverage", "coverage.xml"}


def is_link_junction_or_reparse(path: Path) -> bool:
    """Return true for any filesystem entry that may redirect traversal."""

    try:
        info = path.lstat()
    except OSError:
        return False
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def package_tree_files(root: Path) -> list[Path]:
    """Walk regular package files without following links or reparse points."""

    root = Path(root)
    if is_link_junction_or_reparse(root):
        raise ValueError(f"package root is a link, junction, or reparse point: {root}")
    if not root.is_dir():
        raise ValueError(f"package root is not a directory: {root}")

    files: list[Path] = []

    def walk(directory: Path) -> None:
        try:
            with os.scandir(directory) as scanned:
                entries = sorted(scanned, key=lambda entry: entry.name)
        except OSError as exc:
            raise ValueError(f"cannot scan package directory {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ValueError(f"cannot inspect package entry {path}: {exc}") from exc
            if (
                entry.is_symlink()
                or getattr(path, "is_junction", lambda: False)()
                or bool(getattr(info, "st_file_attributes", 0) & 0x400)
            ):
                raise ValueError(
                    f"package contains a link, junction, or reparse point: {path.relative_to(root)}"
                )
            if stat.S_ISDIR(info.st_mode):
                walk(path)
            elif stat.S_ISREG(info.st_mode):
                files.append(path)
            else:
                raise ValueError(
                    f"package contains a non-regular filesystem entry: {path.relative_to(root)}"
                )

    walk(root)
    return files


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot load TOML {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"TOML root must be a table: {path}")
    return payload


def _expected_names(payload: Mapping[str, Any], path: Path) -> list[str]:
    registry = payload.get("registry")
    if not isinstance(registry, dict):
        raise ValueError(f"missing [registry] table in {path}")
    names = registry.get("expected_names")
    if not isinstance(names, list) or not names or not all(isinstance(item, str) and item for item in names):
        raise ValueError(f"registry.expected_names must be a non-empty string list in {path}")
    if len(names) != len(set(names)):
        raise ValueError(f"registry.expected_names contains duplicates in {path}")
    return names


def load_role_registry(package_root: Path) -> dict[str, RoleSpec]:
    path = Path(package_root) / "config" / "roles.toml"
    payload = _load_toml(path)
    expected = _expected_names(payload, path)
    rows = payload.get("roles")
    if not isinstance(rows, list):
        raise ValueError(f"roles must be an array of tables in {path}")

    result: dict[str, RoleSpec] = {}
    filenames: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"roles[{index}] must be a table")
        unknown = sorted(set(row) - set(ROLE_FIELDS))
        missing = sorted(set(ROLE_FIELDS) - set(row))
        if unknown or missing:
            raise ValueError(f"invalid roles[{index}] fields: missing={missing}, unknown={unknown}")
        for field, expected_type in ROLE_FIELDS.items():
            value = row[field]
            if expected_type is int:
                valid = isinstance(value, int) and not isinstance(value, bool)
            else:
                valid = isinstance(value, expected_type)
            if not valid:
                raise ValueError(f"roles[{index}].{field} has invalid type")
        if not all(isinstance(item, str) and item for item in row["intents"]):
            raise ValueError(f"roles[{index}].intents must contain non-empty strings")
        if not all(isinstance(item, str) and item for item in row["fallbacks"]):
            raise ValueError(f"roles[{index}].fallbacks must contain non-empty strings")
        name = row["name"]
        filename = row["filename"]
        if name in result:
            raise ValueError(f"duplicate role name: {name}")
        if filename in filenames:
            raise ValueError(f"duplicate role filename: {filename}")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"invalid role name: {name}")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*\.toml", filename):
            raise ValueError(f"invalid role filename: {filename}")
        result[name] = RoleSpec(
            name=name,
            filename=filename,
            description=row["description"],
            model=row["model"],
            model_reasoning_effort=row["model_reasoning_effort"],
            model_reasoning_summary=row["model_reasoning_summary"],
            model_verbosity=row["model_verbosity"],
            sandbox_mode=row["sandbox_mode"],
            mutation_class=row["mutation_class"],
            intents=tuple(row["intents"]),
            cost_rank=row["cost_rank"],
            fallbacks=tuple(row["fallbacks"]),
        )
        filenames.add(filename)

    if list(result) != expected:
        raise ValueError(f"role registry does not match registry.expected_names in {path}")
    unknown_fallbacks = sorted({item for spec in result.values() for item in spec.fallbacks} - set(result))
    if unknown_fallbacks:
        raise ValueError(f"unknown role fallbacks: {', '.join(unknown_fallbacks)}")
    return result


def runtime_manifest(root: Path) -> set[Path]:
    try:
        roles = load_role_registry(root)
    except ValueError as exc:
        raise SystemExit(f"FAIL: cannot build runtime manifest: {exc}") from exc
    return RUNTIME_FILES | {
        Path("assets") / "agent-configs" / spec.filename for spec in roles.values()
    }


def included_files(root: Path) -> list[Path]:
    try:
        tree_files = package_tree_files(root)
    except ValueError as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    manifest = runtime_manifest(root)
    files: list[Path] = []
    unexpected: list[Path] = []
    for path in tree_files:
        relative = path.relative_to(root)
        if relative in REPOSITORY_ONLY:
            continue
        if any(part in RUNTIME_EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in RUNTIME_EXCLUDED_SUFFIXES:
            continue
        if path.name in RUNTIME_EXCLUDED_NAMES or path.name.startswith(".coverage."):
            continue
        if relative in manifest:
            files.append(path)
        else:
            unexpected.append(relative)
    if unexpected:
        shown = ", ".join(path.as_posix() for path in unexpected[:8])
        suffix = "" if len(unexpected) <= 8 else f" (+{len(unexpected) - 8} more)"
        raise SystemExit(f"FAIL: unexpected package file(s): {shown}{suffix}")
    missing = sorted(manifest - {path.relative_to(root) for path in files}, key=lambda path: path.as_posix())
    if missing:
        raise SystemExit(
            "FAIL: runtime manifest file(s) missing: "
            + ", ".join(path.as_posix() for path in missing)
        )
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def load_install_profiles(
    package_root: Path,
    role_registry: Mapping[str, RoleSpec] | None = None,
) -> dict[str, InstallProfile]:
    path = Path(package_root) / "config" / "install-profiles.toml"
    payload = _load_toml(path)
    expected = _expected_names(payload, path)
    rows = payload.get("profiles")
    if not isinstance(rows, list):
        raise ValueError(f"profiles must be an array of tables in {path}")
    roles = dict(role_registry) if role_registry is not None else load_role_registry(package_root)
    result: dict[str, InstallProfile] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
            "name", "description", "roles", "default_max_threads"
        }:
            raise ValueError(
                f"profiles[{index}] must contain name, description, roles, and default_max_threads"
            )
        name = row["name"]
        description = row["description"]
        selected_roles = row["roles"]
        default_threads = row["default_max_threads"]
        if not isinstance(name, str) or not name or name in result:
            raise ValueError(f"invalid or duplicate install profile name at index {index}")
        if not isinstance(description, str) or not description:
            raise ValueError(f"profiles[{index}].description must be a non-empty string")
        if (
            not isinstance(selected_roles, list)
            or not selected_roles
            or not all(isinstance(item, str) and item for item in selected_roles)
            or len(selected_roles) != len(set(selected_roles))
        ):
            raise ValueError(f"profiles[{index}].roles must be a unique non-empty string list")
        unknown = sorted(set(selected_roles) - set(roles))
        if unknown:
            raise ValueError(
                f"profiles[{index}] references unknown role(s): {', '.join(unknown)}"
            )
        if (
            not isinstance(default_threads, int)
            or isinstance(default_threads, bool)
            or default_threads < 1
        ):
            raise ValueError(
                f"profiles[{index}].default_max_threads must be a positive integer"
            )
        result[name] = InstallProfile(
            name=name,
            description=description,
            roles=tuple(selected_roles),
            default_max_threads=default_threads,
        )
    if list(result) != expected:
        raise ValueError(f"install profiles do not match registry.expected_names in {path}")
    return result


def load_capability_packs(package_root: Path) -> dict[str, CapabilityPack]:
    path = Path(package_root) / "config" / "capability-packs.toml"
    payload = _load_toml(path)
    expected = _expected_names(payload, path)
    rows = payload.get("packs")
    if not isinstance(rows, list):
        raise ValueError(f"packs must be an array of tables in {path}")
    result: dict[str, CapabilityPack] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"name", "description", "skill_alternatives"}:
            raise ValueError(f"packs[{index}] must contain name, description, and skill_alternatives")
        name = row["name"]
        description = row["description"]
        alternatives = row["skill_alternatives"]
        if not isinstance(name, str) or not name or name in result:
            raise ValueError(f"invalid or duplicate capability pack name at index {index}")
        if not isinstance(description, str) or not description:
            raise ValueError(f"packs[{index}].description must be a non-empty string")
        if not isinstance(alternatives, list) or not alternatives or not all(
            isinstance(item, str) and item for item in alternatives
        ):
            raise ValueError(f"packs[{index}].skill_alternatives must be a non-empty string list")
        result[name] = CapabilityPack(name, description, tuple(alternatives))
    if list(result) != expected:
        raise ValueError(f"capability packs do not match registry.expected_names in {path}")
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def canonical_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty string")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ValueError(f"absolute path is not allowed: {value}")
    parts: list[str] = []
    for part in PurePosixPath(normalized).parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"path traversal is not allowed: {value}")
        parts.append(part)
    if not parts:
        raise ValueError("path must identify a non-root relative target")
    return "/".join(parts)


def artifact_path(root: Path, value: str) -> Path:
    path = canonical_relative_path(value)
    if ":" in path or "\x00" in path:
        raise ValueError("artifact path cannot contain a stream or null byte")
    artifact = root
    for part in path.split("/"):
        artifact = artifact / part
        if is_link_junction_or_reparse(artifact):
            raise ValueError("artifact path contains a link, junction, or reparse point")
    artifact = artifact.resolve(strict=True)
    artifact.relative_to(root)
    if not stat.S_ISREG(artifact.stat().st_mode):
        raise ValueError("artifact must be a regular file")
    return artifact


def artifact_identity(path: Path) -> str | None:
    identity = path.stat()
    return f"{identity.st_dev}:{identity.st_ino}" if identity.st_ino else None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: object) -> None:
    target = Path(path)
    rendered = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False,
    ) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool-as-number coercion."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_equal(item, other) for item, other in zip(left, right))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_json_equal(left[key], right[key]) for key in left)
        )
    return left == right


_ALLOWED_SCHEMA_KEYWORDS = frozenset({
    "$schema", "$id", "$defs", "$ref", "type", "required", "properties",
    "additionalProperties", "enum", "const", "items", "minItems", "maxItems",
    "minLength", "maxLength", "pattern", "minimum", "maximum", "allOf", "anyOf",
    "oneOf", "not",
})


def _audit_schema(
    rule: Mapping[str, Any],
    *,
    path: str,
    root: Mapping[str, Any],
    visited: set[int],
) -> None:
    """Reject unsupported schema keywords before validation can ignore them."""
    if id(rule) in visited:
        return
    visited.add(id(rule))
    unknown = sorted(set(rule) - _ALLOWED_SCHEMA_KEYWORDS)
    if unknown:
        raise ValueError(f"unsupported JSON Schema keyword(s) at {path}: {', '.join(unknown)}")
    if "$ref" in rule:
        reference = rule["$ref"]
        if not isinstance(reference, str):
            raise ValueError(f"invalid schema $ref at {path}")
        _resolve_local_ref(root, reference)
    properties = rule.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ValueError(f"invalid schema properties at {path}")
    for key, child in properties.items():
        if not isinstance(child, Mapping):
            raise ValueError(f"invalid schema property {key!r} at {path}")
        _audit_schema(child, path=f"{path}.properties.{key}", root=root, visited=visited)
    defs = rule.get("$defs", {})
    if not isinstance(defs, Mapping):
        raise ValueError(f"invalid schema $defs at {path}")
    for key, child in defs.items():
        if not isinstance(child, Mapping):
            raise ValueError(f"invalid schema definition {key!r} at {path}")
        _audit_schema(child, path=f"{path}.$defs.{key}", root=root, visited=visited)
    items = rule.get("items")
    if items is not None:
        if not isinstance(items, Mapping):
            raise ValueError(f"invalid schema items at {path}")
        _audit_schema(items, path=f"{path}.items", root=root, visited=visited)
    additional = rule.get("additionalProperties")
    if isinstance(additional, Mapping):
        _audit_schema(additional, path=f"{path}.additionalProperties", root=root, visited=visited)
    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = rule.get(keyword)
        if branches is not None:
            if not isinstance(branches, list) or not all(isinstance(item, Mapping) for item in branches):
                raise ValueError(f"invalid schema {keyword} at {path}")
            for index, branch in enumerate(branches):
                _audit_schema(branch, path=f"{path}.{keyword}[{index}]", root=root, visited=visited)
    forbidden = rule.get("not")
    if forbidden is not None:
        if not isinstance(forbidden, Mapping):
            raise ValueError(f"invalid schema not at {path}")
        _audit_schema(forbidden, path=f"{path}.not", root=root, visited=visited)


def _resolve_local_ref(root_schema: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"only local JSON Schema references are supported: {reference}")
    current: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"unresolvable local JSON Schema reference: {reference}")
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError(f"JSON Schema reference does not target an object: {reference}")
    return current


def validate_instance(
    instance: Any,
    schema: Mapping[str, Any],
    *,
    schema_name: str = "instance",
) -> list[str]:
    """Validate the deterministic JSON Schema subset used by this package."""
    errors: list[str] = []

    def visit(value: Any, rule: Mapping[str, Any], path: str, root: Mapping[str, Any]) -> None:
        _audit_schema(rule, path=path, root=root, visited=set())
        if "$ref" in rule:
            reference = rule["$ref"]
            if not isinstance(reference, str):
                errors.append(f"{path}: $ref must be a string")
                return
            visit(value, _resolve_local_ref(root, reference), path, root)
            return

        expected_type = rule.get("type")
        if expected_type is not None:
            types = [expected_type] if isinstance(expected_type, str) else expected_type
            if not isinstance(types, list) or not types or not all(isinstance(item, str) for item in types):
                raise ValueError(f"invalid schema type at {path}")
            if not any(_type_matches(value, item) for item in types):
                errors.append(f"{path}: expected {' or '.join(types)}")
                return

        if "const" in rule and not _json_equal(value, rule["const"]):
            errors.append(f"{path}: value must equal {rule['const']!r}")
        if "enum" in rule:
            choices = rule["enum"]
            if not isinstance(choices, list):
                raise ValueError(f"invalid schema enum at {path}")
            if not any(_json_equal(value, choice) for choice in choices):
                errors.append(f"{path}: value is not in the allowed enum")

        for keyword in ("allOf", "anyOf", "oneOf"):
            if keyword not in rule:
                continue
            branches = rule[keyword]
            if not isinstance(branches, list) or not all(isinstance(item, dict) for item in branches):
                raise ValueError(f"invalid schema {keyword} at {path}")
            branch_errors: list[list[str]] = []
            for branch in branches:
                before = len(errors)
                visit(value, branch, path, root)
                branch_errors.append(errors[before:])
                del errors[before:]
            matches = sum(not item for item in branch_errors)
            if keyword == "allOf":
                for item in branch_errors:
                    errors.extend(item)
            elif keyword == "anyOf" and matches == 0:
                errors.append(f"{path}: value does not match anyOf")
            elif keyword == "oneOf" and matches != 1:
                errors.append(f"{path}: value must match exactly one oneOf branch")
        if "not" in rule:
            branch = rule["not"]
            if not isinstance(branch, dict):
                raise ValueError(f"invalid schema not at {path}")
            before = len(errors)
            visit(value, branch, path, root)
            matched = len(errors) == before
            del errors[before:]
            if matched:
                errors.append(f"{path}: value matches forbidden schema")

        if isinstance(value, dict):
            required = rule.get("required", [])
            if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
                raise ValueError(f"invalid schema required at {path}")
            for key in required:
                if key not in value:
                    errors.append(f"{path}: missing required property {key!r}")
            properties = rule.get("properties", {})
            if not isinstance(properties, dict):
                raise ValueError(f"invalid schema properties at {path}")
            for key, child in properties.items():
                if not isinstance(child, dict):
                    raise ValueError(f"invalid schema property {key!r} at {path}")
                if key in value:
                    visit(value[key], child, f"{path}.{key}", root)
            if rule.get("additionalProperties") is False:
                for key in sorted(set(value) - set(properties)):
                    errors.append(f"{path}: unknown property {key!r}")
            elif isinstance(rule.get("additionalProperties"), dict):
                additional = rule["additionalProperties"]
                for key in sorted(set(value) - set(properties)):
                    visit(value[key], additional, f"{path}.{key}", root)

        if isinstance(value, list):
            if "minItems" in rule and len(value) < rule["minItems"]:
                errors.append(f"{path}: expected at least {rule['minItems']} items")
            if "maxItems" in rule and len(value) > rule["maxItems"]:
                errors.append(f"{path}: expected at most {rule['maxItems']} items")
            items = rule.get("items")
            if items is not None:
                if not isinstance(items, dict):
                    raise ValueError(f"invalid schema items at {path}")
                for index, item in enumerate(value):
                    visit(item, items, f"{path}[{index}]", root)

        if isinstance(value, str):
            if "minLength" in rule and len(value) < rule["minLength"]:
                errors.append(f"{path}: string is shorter than {rule['minLength']}")
            if "maxLength" in rule and len(value) > rule["maxLength"]:
                errors.append(f"{path}: string is longer than {rule['maxLength']}")
            if "pattern" in rule and re.search(rule["pattern"], value) is None:
                errors.append(f"{path}: string does not match required pattern")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                errors.append(f"{path}: value is below minimum {rule['minimum']}")
            if "maximum" in rule and value > rule["maximum"]:
                errors.append(f"{path}: value is above maximum {rule['maximum']}")

    if not isinstance(schema, Mapping):
        raise ValueError("schema must be an object")
    _audit_schema(schema, path=schema_name, root=schema, visited=set())
    visit(instance, schema, schema_name, schema)
    return errors
