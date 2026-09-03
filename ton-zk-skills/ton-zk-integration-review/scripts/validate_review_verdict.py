#!/usr/bin/env python3
"""Validate a TON ZK review verdict and derive its two release conclusions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PHASE_NAMES = (
    "circuitAudit",
    "proofSystemAudit",
    "proverConverterAudit",
    "setupSrsReview",
    "tonIntegrationAudit",
    "deploymentEvidence",
)
PHASE_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_IN_SCOPE", "NOT_ASSESSED"}
REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DuplicateKeyError(ValueError):
    """Raised when an input object repeats a JSON member name."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except (json.JSONDecodeError, DuplicateKeyError) as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _expected_ton_verdict(phases: dict[str, Any]) -> str:
    statuses = [
        phases.get(name, {}).get("status")
        for name in ("tonIntegrationAudit", "deploymentEvidence")
        if isinstance(phases.get(name), dict)
    ]
    if "FAIL" in statuses:
        return "TON_INTEGRATION_NOT_READY"
    if statuses == ["PASS", "PASS"]:
        return "TON_INTEGRATION_READY"
    return "TON_INTEGRATION_PARTIALLY_READY"


def _expected_full_verdict(phases: dict[str, Any]) -> str:
    if all(isinstance(phases.get(name), dict) and phases[name].get("status") == "PASS" for name in PHASE_NAMES):
        return "FULL_ZK_RELEASE_READY"
    return "FULL_ZK_RELEASE_NOT_READY"


def validate_verdict(data: Any) -> list[str]:
    """Return fail-closed shape and cross-field errors for a parsed verdict."""

    if not isinstance(data, dict):
        return ["verdict root must be an object"]
    errors: list[str] = []
    allowed = {
        "schemaVersion",
        "reviewTarget",
        "tonIntegrationVerdict",
        "fullZkReleaseVerdict",
        "phases",
        "ownerAcceptedRisks",
    }
    for key in sorted(allowed - set(data)):
        errors.append(f"missing required top-level field: {key}")
    for key in sorted(set(data) - allowed):
        errors.append(f"unexpected top-level field: {key}")
    if data.get("schemaVersion") != 2:
        errors.append("schemaVersion must be integer 2")

    target = data.get("reviewTarget")
    if not isinstance(target, dict):
        errors.append("reviewTarget must be an object")
    else:
        target_fields = {"repository", "revision", "artifactSet", "artifactSetSha256"}
        for key in sorted(target_fields - set(target)):
            errors.append(f"reviewTarget.{key} is required")
        for key in sorted(set(target) - target_fields):
            errors.append(f"reviewTarget.{key} is unexpected")
        if not _nonempty_string(target.get("repository")):
            errors.append("reviewTarget.repository must be a non-empty immutable repository identifier")
        revision = target.get("revision")
        if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
            errors.append("reviewTarget.revision must be a 40- or 64-character lowercase hexadecimal revision")
        if not _nonempty_string(target.get("artifactSet")):
            errors.append("reviewTarget.artifactSet must name the reviewed release manifest")
        digest = target.get("artifactSetSha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            errors.append("reviewTarget.artifactSetSha256 must be a lowercase SHA-256 digest")

    phases = data.get("phases")
    if not isinstance(phases, dict):
        errors.append("phases must be an object")
        phases = {}
    else:
        for name in sorted(set(PHASE_NAMES) - set(phases)):
            errors.append(f"phases.{name} is required")
        for name in sorted(set(phases) - set(PHASE_NAMES)):
            errors.append(f"phases.{name} is unexpected")

    for name in PHASE_NAMES:
        phase = phases.get(name)
        if not isinstance(phase, dict):
            if name in phases:
                errors.append(f"phases.{name} must be an object")
            continue
        for key in sorted(set(phase) - {"status", "evidence", "blocker"}):
            errors.append(f"phases.{name}.{key} is unexpected")
        status = phase.get("status")
        if status not in PHASE_STATUSES:
            errors.append(f"phases.{name}.status is invalid")
        evidence = phase.get("evidence")
        if not isinstance(evidence, list) or not all(_nonempty_string(item) for item in evidence):
            errors.append(f"phases.{name}.evidence must be a string array")
        elif status == "PASS" and not evidence:
            errors.append(f"phases.{name}.evidence must contain at least one item for PASS")
        blocker = phase.get("blocker")
        if status == "PASS" and blocker is not None:
            errors.append(f"phases.{name}.blocker must be absent for PASS")
        elif status in PHASE_STATUSES - {"PASS"} and not _nonempty_string(blocker):
            errors.append(f"phases.{name}.blocker is required for non-PASS status")

    expected_ton = _expected_ton_verdict(phases)
    if data.get("tonIntegrationVerdict") != expected_ton:
        errors.append(f"tonIntegrationVerdict must be {expected_ton} for the recorded phase statuses")
    expected_full = _expected_full_verdict(phases)
    if data.get("fullZkReleaseVerdict") != expected_full:
        errors.append(f"fullZkReleaseVerdict must be {expected_full} for the recorded phase statuses")

    risks = data.get("ownerAcceptedRisks")
    if not isinstance(risks, list) or not all(_nonempty_string(item) for item in risks):
        errors.append("ownerAcceptedRisks must be a string array")
    elif len(set(risks)) != len(risks):
        errors.append("ownerAcceptedRisks must not contain duplicates")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verdict", type=Path, help="review-verdict JSON document")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        verdict = _load_json(args.verdict)
    except ValueError as exc:
        parser.error(str(exc))
    errors = validate_verdict(verdict)
    if args.format == "json":
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    elif errors:
        print(f"Review verdict validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print("TON ZK review verdict is internally consistent and fail-closed.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
