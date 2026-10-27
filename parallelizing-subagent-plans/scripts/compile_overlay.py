#!/usr/bin/env python3
"""Compile a plan or explicit plan bundle into one validated execution overlay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from normalize_plan_bundle import SUBPLANS_HEADING, bundle_source_paths
from plan_model import PlanFormatError, parse_plan, semantic_text


SCRIPT_DIR = Path(__file__).resolve().parent


class CompileError(ValueError):
    pass


def _run(command: list[str], stage: str, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode not in allowed:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise CompileError(f"{stage} failed: {detail}")
    return result


def _json(result: subprocess.CompletedProcess[str], stage: str) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CompileError(f"{stage} did not return JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CompileError(f"{stage} JSON must be an object")
    return value


def _is_bundle_master(path: Path) -> bool:
    return any(
        line.strip().casefold() == SUBPLANS_HEADING
        for line in semantic_text(path.read_bytes()).splitlines()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_plan", type=Path)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--normalized-output", type=Path)
    parser.add_argument("--inventory-output", type=Path)
    parser.add_argument("--constraint-map", type=Path)
    parser.add_argument("--constraint-skeleton", type=Path)
    parser.add_argument("--completed-tasks", type=Path)
    parser.add_argument("--isolation", choices=("worktree", "unavailable", "unknown"), default="unknown")
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--skill-root", action="append", type=Path)
    parser.add_argument("--git-executable", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    source = args.source_plan.expanduser().resolve()
    project = args.project.expanduser().resolve()
    output = args.output.expanduser().resolve()
    normalized = (
        args.normalized_output.expanduser().resolve()
        if args.normalized_output
        else source.with_name(f"{source.stem}.normalized.md")
    )
    try:
        bundle_master = _is_bundle_master(source)
        input_paths = {source}
        if bundle_master:
            input_paths.update(bundle_source_paths(source, project))
        input_paths.update(
            path.expanduser().resolve()
            for path in (args.constraint_map, args.completed_tasks)
            if path is not None
        )
        output_paths = {"overlay": output}
        if bundle_master:
            output_paths["normalized plan"] = normalized
        if args.inventory_output:
            output_paths["inventory"] = args.inventory_output.expanduser().resolve()
        if args.constraint_skeleton:
            output_paths["constraint skeleton"] = args.constraint_skeleton.expanduser().resolve()
        for label, path in output_paths.items():
            if path in input_paths:
                raise CompileError(f"output path conflict: {label} aliases an input file")
        by_path: dict[Path, list[str]] = {}
        for label, path in output_paths.items():
            by_path.setdefault(path, []).append(label)
        collisions = [labels for labels in by_path.values() if len(labels) > 1]
        if collisions:
            raise CompileError(
                "output path conflict: " + ", ".join("/".join(labels) for labels in collisions)
            )

        preflight_command = [
            sys.executable,
            "-B",
            str(SCRIPT_DIR / "preflight_dependencies.py"),
            "--project",
            str(project),
            "--format",
            "json",
        ]
        for root in args.skill_root or []:
            preflight_command.extend(["--skill-root", str(root.expanduser().resolve())])
        if args.git_executable:
            preflight_command.extend(["--git-executable", str(args.git_executable.expanduser().resolve())])
        preflight = _json(_run(preflight_command, "preflight", (0, 1)), "preflight")
        if preflight.get("ready") is not True:
            raise CompileError(
                "preflight is not ready: "
                + ", ".join(preflight.get("missing", []) + preflight.get("incompatible", []))
            )

        compiled_source = source
        if bundle_master:
            normalize_command = [
                sys.executable,
                "-B",
                str(SCRIPT_DIR / "normalize_plan_bundle.py"),
                str(source),
                "--project",
                str(project),
                "--output",
                str(normalized),
                "--format",
                "json",
            ]
            if args.force:
                normalize_command.append("--force")
            _run(normalize_command, "bundle normalization")
            compiled_source = normalized

        inventory_command = [
            sys.executable,
            "-B",
            str(SCRIPT_DIR / "plan_inventory.py"),
            str(compiled_source),
            "--format",
            "json",
        ]
        if args.inventory_output:
            inventory_command.extend(["--output", str(args.inventory_output.expanduser().resolve())])
            if args.force:
                inventory_command.append("--force")
        inventory_result = _run(inventory_command, "inventory")
        inventory = (
            json.loads(args.inventory_output.expanduser().resolve().read_text(encoding="utf-8"))
            if args.inventory_output
            else json.loads(inventory_result.stdout)
        )
        plan = parse_plan(compiled_source)
        if plan.global_constraints and args.constraint_map is None:
            skeleton = (
                args.constraint_skeleton.expanduser().resolve()
                if args.constraint_skeleton
                else compiled_source.with_suffix(".constraints.json")
            )
            reserved_outputs = {output}
            if bundle_master:
                reserved_outputs.add(normalized)
            if args.inventory_output:
                reserved_outputs.add(args.inventory_output.expanduser().resolve())
            if skeleton in input_paths or skeleton in reserved_outputs:
                raise CompileError("output path conflict: constraint skeleton aliases another artifact")
            skeleton_command = [
                sys.executable,
                "-B",
                str(SCRIPT_DIR / "generate_constraint_map.py"),
                str(compiled_source),
                "--output",
                str(skeleton),
            ]
            for check in args.check:
                skeleton_command.extend(["--check", check])
            if args.force:
                skeleton_command.append("--force")
            _run(skeleton_command, "constraint skeleton")
            report = {
                "schema_version": 1,
                "valid": False,
                "status": "constraint-map-required",
                "source_plan": str(compiled_source),
                "constraint_skeleton": str(skeleton),
                "task_count": len(inventory.get("tasks", [])),
            }
            if args.format == "json":
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f"Fill constraint map {skeleton}, then rerun with --constraint-map")
            return 3

        initialize_command = [
            sys.executable,
            "-B",
            str(SCRIPT_DIR / "init_overlay.py"),
            str(compiled_source),
            "--output",
            str(output),
            "--isolation",
            args.isolation,
            "--format",
            "json",
        ]
        for check in args.check:
            initialize_command.extend(["--check", check])
        if args.constraint_map:
            initialize_command.extend(["--constraint-map", str(args.constraint_map.expanduser().resolve())])
        if args.completed_tasks:
            initialize_command.extend(["--completed-tasks", str(args.completed_tasks.expanduser().resolve())])
        if args.git_executable:
            initialize_command.extend(["--git-executable", str(args.git_executable.expanduser().resolve())])
        if args.force:
            initialize_command.append("--force")
        initialized = _json(_run(initialize_command, "scheduler"), "scheduler")

        validation_command = [
            sys.executable,
            "-B",
            str(SCRIPT_DIR / "validate_parallel_plan.py"),
            str(compiled_source),
            str(output),
            "--format",
            "json",
        ]
        if args.git_executable:
            validation_command.extend(["--git-executable", str(args.git_executable.expanduser().resolve())])
        validation = _json(_run(validation_command, "overlay validation"), "overlay validation")
        report = {
            "schema_version": 1,
            "valid": validation.get("valid") is True,
            "verdict": initialized.get("verdict"),
            "source_plan": str(compiled_source),
            "output": str(output),
            "task_count": len(inventory.get("tasks", [])),
            "lane_count": initialized.get("lane_count", 0),
        }
    except (OSError, UnicodeError, json.JSONDecodeError, PlanFormatError, CompileError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote validated {str(report['verdict']).upper()} overlay to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
