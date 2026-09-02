#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from bootstrap_project_companion import build_inventory, generated_file_fingerprints
from project_companion_common import (
    GENERATED_BY,
    SCHEMA_VERSION,
    get_git_info,
    inventory_sha256,
    sha256_file,
)

REQUIRED_HEADINGS = [
    "## Role in the pair",
    "## Project identity",
    "## Freshness contract",
    "## Required startup",
    "## Reference files",
    "## Durable update rules",
]
FORBIDDEN_MARKERS = ["TODO", "TBD", "{{", "}}", "$project_name", "$skill_name"]
FACT_FIELDS = ("Fact", "Evidence", "Confidence", "Last verified")
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
        r"\s*[:=]\s*[^\s`]{8,}",
        re.IGNORECASE,
    ),
]
ABSOLUTE_USER_PATH_PATTERNS = [
    re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s]+\\"),
    re.compile(r"/(?:Users|home)/[^/\s]+/"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a generated project companion skill.")
    parser.add_argument("companion_dir", help="Path to <project-slug>-project-context")
    parser.add_argument("--project-root", help="Override project root resolution")
    parser.add_argument("--json", action="store_true", help="Print machine-readable report")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"\'')
    return result


def resolve_within(base: Path, relative: str, label: str, errors: list[str]) -> Path | None:
    relative_path = Path(relative)
    if relative_path.is_absolute():
        errors.append(f"{label} must be relative: {relative}")
        return None
    candidate = (base / relative_path).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        target = "project root" if label in {"Fingerprint path", "Evidence path"} else "companion directory"
        errors.append(f"{label} escapes {target}: {relative}")
        return None
    return candidate


def text_without_fenced_blocks(text: str) -> list[str]:
    result: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append(line)
    return result


def parse_fact_records(companion_dir: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    references = companion_dir / "references"
    if not references.is_dir():
        return records
    for path in sorted(references.glob("*.md")):
        try:
            lines = text_without_fenced_blocks(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        current: dict[str, str] | None = None
        for line in lines:
            match = re.match(r"^(Fact|Evidence|Confidence|Last verified):\s*(.+?)\s*$", line)
            if not match:
                continue
            field, value = match.groups()
            if field == "Fact":
                if current:
                    records.append(current)
                current = {"source": path.relative_to(companion_dir).as_posix(), field: value}
            elif current is not None:
                current[field] = value
        if current:
            records.append(current)
    return records


def _looks_like_evidence_path(token: str, project_root: Path) -> bool:
    if "/" in token or "\\" in token:
        return True
    if Path(token).suffix:
        return True
    return (project_root / token).exists()


def validate_durable_facts(
    companion_dir: Path,
    project_root: Path,
    recorded_evidence: list[dict[str, Any]] | None = None,
) -> tuple[
    list[str],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, Any]],
]:
    errors: list[str] = []
    stale: list[dict[str, str]] = []
    records = parse_fact_records(companion_dir)
    evidence_fingerprints: list[dict[str, Any]] = []
    if not records:
        errors.append("Hydrated companion requires at least one evidence-backed durable fact")
        return errors, stale, records, evidence_fingerprints

    for index, record in enumerate(records, start=1):
        source = record.get("source", "unknown")
        for field in FACT_FIELDS:
            if not record.get(field):
                errors.append(f"Durable fact {index} in {source} is missing {field}")
        if record.get("Confidence", "").strip().lower() != "confirmed":
            errors.append(f"Durable fact {index} in {source} must use Confidence: confirmed")

        verified = record.get("Last verified", "").strip()
        valid_verified = False
        if re.fullmatch(r"[0-9a-fA-F]{7,40}", verified):
            valid_verified = True
        elif verified.lower().startswith("commit ") and re.fullmatch(r"[0-9a-fA-F]{7,40}", verified[7:].strip()):
            valid_verified = True
        else:
            try:
                date.fromisoformat(verified)
                valid_verified = True
            except ValueError:
                pass
        if verified and not valid_verified:
            errors.append(f"Durable fact {index} in {source} has invalid Last verified value")

        evidence = record.get("Evidence", "")
        tokens = re.findall(r"`([^`]+)`", evidence)
        path_tokens = [token for token in tokens if _looks_like_evidence_path(token, project_root)]
        if not path_tokens:
            errors.append(f"Durable fact {index} in {source} requires a repository-relative evidence path")
            continue
        existing_evidence = False
        for token in path_tokens:
            normalized = token.split("#", 1)[0]
            if re.search(r":\d+(?::\d+)?$", normalized):
                normalized = re.sub(r":\d+(?::\d+)?$", "", normalized)
            path_errors: list[str] = []
            candidate = resolve_within(project_root, normalized, "Evidence path", path_errors)
            errors.extend(path_errors)
            if candidate is None:
                continue
            if candidate.exists():
                existing_evidence = True
                try:
                    stat = candidate.stat()
                    digest = sha256_file(candidate)
                except OSError as exc:
                    stale.append(
                        {
                            "path": normalized,
                            "reason": (
                                f"unreadable evidence for durable fact {index}: "
                                f"{exc.strerror or str(exc) or type(exc).__name__}"
                            ),
                        }
                    )
                    continue
                evidence_fingerprints.append(
                    {
                        "fact_index": index,
                        "source": source,
                        "path": normalized,
                        "sha256": digest,
                        "size": stat.st_size,
                    }
                )
            else:
                stale.append({"path": normalized, "reason": f"missing evidence for durable fact {index}"})
        if not existing_evidence and not stale:
            errors.append(f"Durable fact {index} in {source} has no existing evidence path")

    text_paths = [companion_dir / "SKILL.md", *sorted((companion_dir / "references").glob("*.md"))]
    for path in text_paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        relative = path.relative_to(companion_dir).as_posix()
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"Secret-like content detected in {relative}")
                break
        for pattern in ABSOLUTE_USER_PATH_PATTERNS:
            if pattern.search(text):
                errors.append(f"Absolute user path detected in {relative}")
                break

    if recorded_evidence is not None:
        recorded_map: dict[tuple[int, str, str], str] = {}
        for entry in recorded_evidence:
            if not isinstance(entry, dict):
                errors.append("Durable evidence fingerprint entry must be an object")
                continue
            fact_index = entry.get("fact_index")
            source = entry.get("source")
            path = entry.get("path")
            digest = entry.get("sha256")
            if (
                not isinstance(fact_index, int)
                or not isinstance(source, str)
                or not isinstance(path, str)
                or not isinstance(digest, str)
            ):
                errors.append(
                    "Durable evidence fingerprint requires fact_index, source, path, and sha256"
                )
                continue
            recorded_map[(fact_index, source, path)] = digest

        current_map = {
            (entry["fact_index"], entry["source"], entry["path"]): entry["sha256"]
            for entry in evidence_fingerprints
        }
        existing_stale = {(item["path"], item["reason"]) for item in stale}
        for key in sorted(set(recorded_map) | set(current_map)):
            fact_index, _source, path = key
            if key not in recorded_map:
                item = {
                    "path": path,
                    "reason": f"unrecorded evidence for durable fact {fact_index}",
                }
            elif key not in current_map:
                item = {
                    "path": path,
                    "reason": f"missing evidence for durable fact {fact_index}",
                }
            elif recorded_map[key] != current_map[key]:
                item = {
                    "path": path,
                    "reason": f"content changed for durable fact {fact_index}",
                }
            else:
                continue
            if (item["path"], item["reason"]) not in existing_stale:
                stale.append(item)
                existing_stale.add((item["path"], item["reason"]))
    return errors, stale, records, evidence_fingerprints


def validate_companion(
    companion_dir: Path,
    project_root_override: Path | None = None,
) -> tuple[dict[str, Any], int]:
    companion_dir = companion_dir.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    changed: list[dict[str, str]] = []
    generated_changes: list[dict[str, str]] = []
    durable_changes: list[dict[str, str]] = []

    if not companion_dir.is_dir():
        errors.append(f"Companion directory does not exist: {companion_dir}")

    skill_path = companion_dir / "SKILL.md"
    manifest_path = companion_dir / "manifest.json"
    skill_text = ""
    if not skill_path.is_file():
        errors.append("Missing SKILL.md")
    else:
        try:
            skill_text = skill_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"Cannot read SKILL.md: {exc}")

    frontmatter = parse_frontmatter(skill_text) if skill_text else {}
    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if not re.fullmatch(r"[a-z0-9-]+", name):
        errors.append("Frontmatter name must use lowercase letters, numbers, and hyphens")
    if name and name != companion_dir.name and not companion_dir.name.startswith(f".{name}.staging-"):
        errors.append(f"Frontmatter name {name!r} does not match directory {companion_dir.name!r}")
    if not description.startswith("Use when "):
        errors.append("Frontmatter description must start with 'Use when '")
    if len(description) > 500:
        errors.append("Frontmatter description exceeds 500 characters")
    for heading in REQUIRED_HEADINGS:
        if skill_text and heading not in skill_text:
            errors.append(f"Missing required heading: {heading}")
    for marker in FORBIDDEN_MARKERS:
        if marker in skill_text:
            errors.append(f"Unresolved marker in SKILL.md: {marker}")

    manifest = load_json(manifest_path)
    if not manifest:
        errors.append("Missing or invalid manifest.json")
    else:
        if manifest.get("schema_version") != SCHEMA_VERSION:
            errors.append(
                f"Unsupported schema_version: {manifest.get('schema_version')!r}; expected {SCHEMA_VERSION}. "
                "Run --refresh-metadata with the owning bootstrap tool to migrate."
            )
        if manifest.get("generated_by") != GENERATED_BY:
            errors.append("manifest.json generated_by is not recognized")
        if not isinstance(manifest.get("generator_version"), str) or not manifest.get("generator_version"):
            errors.append("manifest.json generator_version must be a non-empty string")
        if manifest.get("skill_name") != name:
            errors.append("manifest.json skill_name does not match SKILL.md")
        if manifest.get("context_state") not in {"bootstrap", "hydrated"}:
            errors.append("manifest.json context_state must be bootstrap or hydrated")

    project_root = project_root_override.expanduser().resolve() if project_root_override else None
    if project_root is None and manifest:
        relative_root = manifest.get("root_relative_to_companion")
        if isinstance(relative_root, str) and relative_root:
            project_root = (companion_dir / relative_root).resolve()
        else:
            errors.append("manifest.json is missing root_relative_to_companion")

    if project_root is not None and not project_root.is_dir():
        errors.append(f"Resolved project root does not exist: {project_root}")
    elif project_root is not None:
        try:
            companion_dir.relative_to(project_root)
        except ValueError:
            errors.append("Companion directory is not inside the resolved project root")

    if manifest:
        references = manifest.get("reference_files")
        if not isinstance(references, list) or not references:
            errors.append("manifest.json reference_files must be a non-empty list")
        else:
            for relative in references:
                if not isinstance(relative, str):
                    errors.append("manifest.json reference_files contains a non-string value")
                    continue
                path = resolve_within(companion_dir, relative, "Reference path", errors)
                if path is None:
                    continue
                if not path.is_file():
                    errors.append(f"Missing reference file: {relative}")
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError as exc:
                    errors.append(f"Cannot read reference file {relative}: {exc}")
                    continue
                for marker in FORBIDDEN_MARKERS:
                    if marker in text:
                        errors.append(f"Unresolved marker in {relative}: {marker}")

    inventory_status = "indeterminate"
    discovery_report: dict[str, Any] = {}
    recorded_inventory_sha256 = manifest.get("inventory_sha256") if manifest else None
    current_inventory_sha256: str | None = None
    if manifest and project_root is not None and project_root.is_dir():
        fingerprints = manifest.get("high_signal_fingerprints")
        recorded: dict[str, str] = {}
        if not isinstance(fingerprints, list):
            errors.append("manifest.json high_signal_fingerprints must be a list")
        else:
            for entry in fingerprints:
                if not isinstance(entry, dict):
                    errors.append("Fingerprint entry must be an object")
                    continue
                relative = entry.get("path")
                expected = entry.get("sha256")
                if not isinstance(relative, str) or not isinstance(expected, str):
                    errors.append("Fingerprint entry requires string path and sha256")
                    continue
                path = resolve_within(project_root, relative, "Fingerprint path", errors)
                if path is not None:
                    recorded[relative] = expected

        current_inventory = build_inventory(project_root)
        discovery_report = current_inventory["discovery"]
        current_entries = current_inventory["fingerprints"]
        current_inventory_sha256 = inventory_sha256(current_inventory)
        current = {entry["path"]: entry["sha256"] for entry in current_entries}
        for relative in sorted(set(recorded) | set(current)):
            if relative not in recorded:
                changed.append({"path": relative, "reason": "added"})
            elif relative not in current:
                changed.append({"path": relative, "reason": "missing"})
            elif current[relative] != recorded[relative]:
                changed.append({"path": relative, "reason": "content changed"})

        recorded_discovery = manifest.get("discovery")
        if isinstance(recorded_discovery, dict) and recorded_discovery.get("truncated"):
            warnings.append("Recorded discovery was truncated; inventory cannot be proven current")
        discovery_errors = discovery_report.get("errors", [])
        if discovery_errors:
            warnings.append("Current discovery was incomplete: " + "; ".join(discovery_errors))
        if not isinstance(recorded_inventory_sha256, str) or not recorded_inventory_sha256:
            errors.append("manifest.json inventory_sha256 must be a non-empty string")
        if discovery_errors or (isinstance(recorded_discovery, dict) and recorded_discovery.get("truncated")):
            inventory_status = "indeterminate"
        elif changed or recorded_inventory_sha256 != current_inventory_sha256:
            inventory_status = "stale"
        else:
            inventory_status = "current"

        recorded_git = manifest.get("git") if isinstance(manifest.get("git"), dict) else {}
        current_git = get_git_info(project_root)
        recorded_commit = recorded_git.get("commit") if isinstance(recorded_git, dict) else None
        if (
            isinstance(recorded_commit, str)
            and recorded_commit not in {"", "not available"}
            and current_git.commit not in {"", "not available"}
            and recorded_commit != current_git.commit
        ):
            warnings.append(
                "Git HEAD differs from the last verified commit; inventory comparison determines structural staleness"
            )

    generated_from = manifest.get("generated_content_inventory_sha256") if manifest else None
    generated_content_status = "stale"
    if manifest:
        generator_baseline = manifest.get("generated_file_fingerprints")
        if not isinstance(generator_baseline, list) or not generator_baseline:
            errors.append("manifest.json generated_file_fingerprints must be a non-empty list")

        accepted = manifest.get("accepted_generated_file_fingerprints")
        accepted_map: dict[str, str] = {}
        if not isinstance(accepted, list) or not accepted:
            errors.append(
                "manifest.json accepted_generated_file_fingerprints must be a non-empty list"
            )
        else:
            for entry in accepted:
                if not isinstance(entry, dict):
                    errors.append("Accepted generated fingerprint entry must be an object")
                    continue
                relative = entry.get("path")
                digest = entry.get("sha256")
                if not isinstance(relative, str) or not isinstance(digest, str):
                    errors.append(
                        "Accepted generated fingerprint entry requires string path and sha256"
                    )
                    continue
                if resolve_within(
                    companion_dir,
                    relative,
                    "Generated fingerprint path",
                    errors,
                ) is not None:
                    accepted_map[relative] = digest

        generated_read_errors: list[str] = []
        current_generated_entries = generated_file_fingerprints(
            companion_dir,
            errors=generated_read_errors,
        )
        current_generated = {
            entry["path"]: entry["sha256"] for entry in current_generated_entries
        }
        for relative in sorted(set(accepted_map) | set(current_generated)):
            if relative not in accepted_map:
                generated_changes.append({"path": relative, "reason": "unrecorded"})
            elif relative not in current_generated:
                generated_changes.append({"path": relative, "reason": "missing or unreadable"})
            elif accepted_map[relative] != current_generated[relative]:
                generated_changes.append({"path": relative, "reason": "content changed"})
        if generated_read_errors:
            warnings.append(
                "Generated companion inputs could not be read: " + "; ".join(generated_read_errors)
            )
        if (
            isinstance(generated_from, str)
            and generated_from
            and current_inventory_sha256 is not None
            and generated_from == current_inventory_sha256
            and not generated_changes
            and not generated_read_errors
        ):
            generated_content_status = "current"

    context_state = manifest.get("context_state") if manifest else None
    if context_state == "bootstrap":
        durable_facts_status = "bootstrap"
        warnings.append(
            "Companion is structurally valid but still in bootstrap state; hydrate durable architecture facts before relying on them"
        )
    elif context_state == "hydrated" and project_root is not None and project_root.is_dir():
        recorded_evidence = manifest.get("durable_fact_evidence_fingerprints")
        if not isinstance(recorded_evidence, list):
            errors.append("manifest.json durable_fact_evidence_fingerprints must be a list")
            recorded_evidence = []
        fact_errors, durable_changes, _records, _current_evidence = validate_durable_facts(
            companion_dir,
            project_root,
            recorded_evidence,
        )
        errors.extend(fact_errors)
        durable_facts_status = "invalid" if fact_errors else ("stale" if durable_changes else "current")
    else:
        durable_facts_status = "invalid"

    structure_status = "invalid" if errors else "valid"
    if errors:
        status = "invalid"
        exit_code = 2
    elif inventory_status != "current" or generated_content_status != "current" or durable_facts_status == "stale":
        status = "stale"
        exit_code = 3
    else:
        status = "valid"
        exit_code = 0

    report = {
        "status": status,
        "structure_status": structure_status,
        "inventory_status": inventory_status,
        "generated_content_status": generated_content_status,
        "durable_facts_status": durable_facts_status,
        "companion_dir": str(companion_dir),
        "project_root": str(project_root) if project_root is not None else None,
        "context_state": context_state,
        "errors": errors,
        "warnings": warnings,
        "changed_fingerprints": changed,
        "changed_generated_files": generated_changes,
        "changed_evidence": durable_changes,
        "discovery": discovery_report,
        "recorded_inventory_sha256": recorded_inventory_sha256,
        "current_inventory_sha256": current_inventory_sha256,
    }
    return report, exit_code


def main() -> int:
    args = parse_args()
    companion_dir = Path(args.companion_dir)
    project_root = Path(args.project_root) if args.project_root else None
    report, exit_code = validate_companion(companion_dir, project_root)

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"Status: {report['status']}")
        for error in report["errors"]:
            print(f"ERROR: {error}")
        for item in report["changed_fingerprints"]:
            print(f"STALE: {item['path']} ({item['reason']})")
        for item in report["changed_generated_files"]:
            print(f"STALE GENERATED: {item['path']} ({item['reason']})")
        for item in report["changed_evidence"]:
            print(f"STALE EVIDENCE: {item['path']} ({item['reason']})")
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
