#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bootstrap_project_companion import generated_file_fingerprints, write_json_atomic
from project_companion_common import utc_now
from validate_project_companion import load_json, validate_companion, validate_durable_facts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark a project companion hydrated after semantic fact validation."
    )
    parser.add_argument("companion_dir", help="Path to <project-slug>-project-context")
    parser.add_argument("--project-root", help="Override project root resolution")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output")
    return parser.parse_args()


def output_report(report: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False))
        return
    print(f"Status: {report.get('status', 'invalid')}")
    for error in report.get("errors", []):
        print(f"ERROR: {error}")


def main() -> int:
    args = parse_args()
    companion_dir = Path(args.companion_dir).expanduser().resolve()
    manifest_path = companion_dir / "manifest.json"
    manifest = load_json(manifest_path)
    project_root = Path(args.project_root).expanduser().resolve() if args.project_root else None
    if project_root is None and manifest:
        relative_root = manifest.get("root_relative_to_companion")
        if isinstance(relative_root, str) and relative_root:
            project_root = (companion_dir / relative_root).resolve()

    base_report, _base_code = validate_companion(companion_dir, project_root)
    base_errors = list(base_report["errors"])
    if base_report["inventory_status"] != "current":
        base_errors.append("Inventory must be current before hydration")
    if project_root is None or not project_root.is_dir():
        base_errors.append("Project root must exist before hydration")
        fact_changes: list[dict[str, str]] = []
        records: list[dict[str, str]] = []
        evidence_fingerprints: list[dict[str, object]] = []
    else:
        fact_errors, fact_changes, records, evidence_fingerprints = validate_durable_facts(
            companion_dir,
            project_root,
        )
        base_errors.extend(fact_errors)
    if fact_changes:
        base_errors.extend(
            f"Evidence is stale: {item['path']} ({item['reason']})" for item in fact_changes
        )

    changed_generated = base_report.get("changed_generated_files", [])
    changed_generated_paths = {
        item.get("path")
        for item in changed_generated
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    fact_sources = {
        record.get("source")
        for record in records
        if isinstance(record.get("source"), str)
    }
    generated_inventory_is_current = (
        manifest.get("generated_content_inventory_sha256")
        == base_report.get("current_inventory_sha256")
    )
    only_fact_files_changed = bool(changed_generated_paths) and changed_generated_paths.issubset(
        fact_sources
    )
    if base_report["generated_content_status"] != "current" and not (
        generated_inventory_is_current and only_fact_files_changed
    ):
        base_errors.append(
            "Generated companion content must be reconciled before hydration; only validated durable-fact files may differ"
        )

    if base_errors:
        report = {
            **base_report,
            "status": "invalid",
            "context_state": manifest.get("context_state") if manifest else None,
            "errors": list(dict.fromkeys(base_errors)),
        }
        output_report(report, args.json)
        return 2

    original_manifest = dict(manifest)
    manifest["context_state"] = "hydrated"
    manifest["last_verified_at"] = utc_now()
    manifest["generated_content_inventory_sha256"] = manifest.get("inventory_sha256")
    manifest["accepted_generated_file_fingerprints"] = generated_file_fingerprints(companion_dir)
    manifest["durable_fact_evidence_fingerprints"] = evidence_fingerprints
    try:
        write_json_atomic(manifest_path, manifest)
        report, exit_code = validate_companion(companion_dir, project_root)
        if exit_code != 0:
            write_json_atomic(manifest_path, original_manifest)
            report["errors"] = [
                *report["errors"],
                "Hydration transition was rolled back because post-write validation failed",
            ]
            output_report(report, args.json)
            return 2
    except BaseException:
        write_json_atomic(manifest_path, original_manifest)
        raise

    output_report(report, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
