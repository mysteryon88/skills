#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bootstrap_project_companion import generated_file_fingerprints, write_json_atomic
from project_companion_common import utc_now
from validate_project_companion import load_json, validate_companion, validate_durable_facts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate reviewed project-companion content and explicitly reconcile it with "
            "the current project inventory."
        )
    )
    parser.add_argument("companion_dir", help="Path to <project-slug>-project-context")
    parser.add_argument("--project-root", help="Override project root resolution")
    parser.add_argument(
        "--accept-current-generated",
        action="store_true",
        help=(
            "Accept the currently reviewed generated files as the reconciled content baseline; "
            "without this flag the command is read-only"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output")
    return parser.parse_args()


def output_report(report: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False))
        return
    print(f"Status: {report.get('status', 'invalid')}")
    for error in report.get("errors", []):
        print(f"ERROR: {error}")
    for item in report.get("changed_generated_files", []):
        print(f"CHANGED GENERATED: {item['path']} ({item['reason']})")
    operator_action = report.get("operator_action")
    if operator_action:
        print(f"OPERATOR ACTION: {operator_action}")


def resolve_project_root(
    companion_dir: Path,
    manifest: dict[str, object],
    override: str | None,
) -> Path | None:
    if override:
        return Path(override).expanduser().resolve()
    relative_root = manifest.get("root_relative_to_companion")
    if isinstance(relative_root, str) and relative_root:
        return (companion_dir / relative_root).resolve()
    return None


def main() -> int:
    args = parse_args()
    companion_dir = Path(args.companion_dir).expanduser().resolve()
    manifest_path = companion_dir / "manifest.json"
    manifest = load_json(manifest_path)
    project_root = resolve_project_root(companion_dir, manifest, args.project_root)
    report, exit_code = validate_companion(companion_dir, project_root)

    if report["structure_status"] != "valid" or exit_code == 2:
        output_report(report, args.json)
        return 2
    if report["inventory_status"] != "current":
        report["operator_action"] = (
            "Run the owning bootstrap tool with --refresh-metadata after resolving unreadable inputs, "
            "then review the generated references again."
        )
        output_report(report, args.json)
        return 3
    if project_root is None or not project_root.is_dir():
        report["errors"] = [*report["errors"], "Project root must exist for reconciliation"]
        report["status"] = "invalid"
        output_report(report, args.json)
        return 2

    evidence_fingerprints: list[dict[str, object]] = []
    if manifest.get("context_state") == "hydrated":
        recorded_evidence_changes = report.get("changed_evidence", [])
        legacy_evidence_only = bool(recorded_evidence_changes) and all(
            isinstance(item, dict)
            and isinstance(item.get("reason"), str)
            and item["reason"].startswith("unrecorded evidence")
            for item in recorded_evidence_changes
        )
        if report["durable_facts_status"] == "stale" and (
            not legacy_evidence_only or report["generated_content_status"] == "current"
        ):
            report["operator_action"] = (
                "Review the changed evidence, update the durable fact and Last verified value, "
                "then run hydrate_project_companion.py before reconciling generated content."
            )
            output_report(report, args.json)
            return 3
        fact_errors, fact_changes, _records, evidence_fingerprints = validate_durable_facts(
            companion_dir,
            project_root,
        )
        if fact_errors or fact_changes:
            report["errors"] = [
                *report["errors"],
                *fact_errors,
                *(f"Evidence is stale: {item['path']} ({item['reason']})" for item in fact_changes),
            ]
            report["status"] = "invalid"
            output_report(report, args.json)
            return 2

    if report["generated_content_status"] == "current":
        output_report(report, args.json)
        return 0
    if not args.accept_current_generated:
        report["operator_action"] = (
            "Inspect every changed generated file, reconcile it with the current inventory while "
            "preserving durable facts, then rerun with --accept-current-generated."
        )
        output_report(report, args.json)
        return 3

    fingerprint_errors: list[str] = []
    accepted_fingerprints = generated_file_fingerprints(
        companion_dir,
        errors=fingerprint_errors,
    )
    if fingerprint_errors:
        report["errors"] = [
            *report["errors"],
            *(f"Cannot reconcile generated file: {item}" for item in fingerprint_errors),
        ]
        report["status"] = "invalid"
        output_report(report, args.json)
        return 2

    original_manifest = dict(manifest)
    manifest["accepted_generated_file_fingerprints"] = accepted_fingerprints
    manifest["generated_content_inventory_sha256"] = report["current_inventory_sha256"]
    manifest["durable_fact_evidence_fingerprints"] = evidence_fingerprints
    manifest["last_verified_at"] = utc_now()
    try:
        write_json_atomic(manifest_path, manifest)
        final_report, final_code = validate_companion(companion_dir, project_root)
        if final_code != 0:
            write_json_atomic(manifest_path, original_manifest)
            final_report["errors"] = [
                *final_report["errors"],
                "Reconciliation was rolled back because post-write validation failed",
            ]
            output_report(final_report, args.json)
            return 2
    except BaseException:
        write_json_atomic(manifest_path, original_manifest)
        raise

    final_report["action"] = "reconciled"
    output_report(final_report, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
