from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from github_ready_lib.gate import (
    GATE_VERSION,
    enhance_pre_push_audit,
    gate_exit_code,
    redact_pre_push_result,
    verdict_for,
)
from github_ready_lib.git_repo import GitBudgetExceeded, GitCommandError, GitRepository
from github_ready_lib.model import coverage_gap
from github_ready_lib.scanner import scan_repository


class ArgumentParseError(ValueError):
    pass


class SanitizingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ArgumentParseError(message)


def _parser() -> argparse.ArgumentParser:
    parser = SanitizingArgumentParser(
        description="Audit a Git repository for GitHub publication readiness."
    )
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-blob-bytes", type=int, default=8_388_608)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--max-work-units", type=int, default=1_000_000)
    parser.add_argument(
        "--reviewed-findings-sha256",
        help="With --gate, approve only the independently reviewed exact staged policy SHA256.",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help=(
            "Enable the strict pre-push gate: scan the Git index, staged .gitignore "
            "rules, Git metadata, AI/local artifacts, path portability, and workflows."
        ),
    )
    parser.add_argument(
        "--fail-on",
        choices=("blocker", "warning", "none"),
        default="blocker",
        help="With --gate, return 1 at this finding threshold (default: blocker).",
    )
    return parser


def _json_document(result: dict[str, object]) -> str:
    return json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _text_document(result: dict[str, object]) -> str:
    coverage = result["coverage"]
    candidates = result["candidates"]
    assert isinstance(coverage, dict)
    assert isinstance(candidates, list)
    inventory = result["inventory"]
    assert isinstance(inventory, dict)
    lines = [
        f"verdict: {result.get('verdict', verdict_for(result))}",
        f"candidates: {len(candidates)}",
        f"coverage: {'complete' if coverage['complete'] else 'incomplete'}",
        f"coverage-gaps: {len(coverage['gaps'])}",
        "inventory: "
        + ", ".join(
            f"{state}={len(paths)}" for state, paths in sorted(inventory.items())
        ),
    ]
    if "gate_version" in result:
        lines.append(f"gate-version: {result['gate_version']}")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        fields = [
            f"kind={candidate.get('kind', 'unknown')}",
            f"severity={candidate.get('severity', 'unknown')}",
            f"action={candidate.get('action', 'unknown')}",
        ]
        for name in (
            "path",
            "line",
            "detector",
            "fingerprint",
            "source",
            "commit",
            "ref",
            "object_id",
            "reviewed_false_positive",
            "reviewed_policy_sha256",
        ):
            if name in candidate:
                fields.append(f"{name}={candidate[name]}")
        if "paths" in candidate:
            fields.append(f"paths={candidate['paths']}")
        lines.append("candidate: " + " ".join(fields))
    return "\n".join(lines) + "\n"


def _error_document() -> dict[str, object]:
    return {
        "error": {
            "code": "scan-failed",
            "message": "Repository scan could not be completed.",
        }
    }


def _write_or_print(document: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(document)
        return
    output.write_text(document, encoding="utf-8")


def _emit_error(output: Path | None) -> None:
    document = _json_document(_error_document())
    try:
        _write_or_print(document, output)
    except OSError:
        sys.stdout.write(document)


def _validate_gate_output_path(
    root: Path,
    output: Path | None,
    *,
    timeout_seconds: int,
    deadline: float | None = None,
) -> None:
    if output is None:
        return
    repository_root = GitRepository(
        root,
        timeout_seconds=timeout_seconds,
        deadline=deadline,
        max_git_commands=4,
        max_total_bytes=1_048_576,
        max_work_units=10_000,
        max_locations=1_000,
    ).root
    resolved_output = output.resolve(strict=False)
    try:
        resolved_output.relative_to(repository_root)
    except ValueError:
        return
    raise ValueError("strict gate output must be outside the audited repository")


def _mark_gate_budget_incomplete(
    result: dict[str, object], evidence: str = "strict pre-push gate budget exhausted"
) -> dict[str, object]:
    coverage = result.setdefault("coverage", {})
    if not isinstance(coverage, dict):
        raise ValueError("coverage must be an object")
    gaps = coverage.setdefault("gaps", [])
    if not isinstance(gaps, list):
        raise ValueError("coverage.gaps must be an array")
    gap = coverage_gap(path=None, object_id=None, evidence=evidence)
    if gap not in gaps:
        gaps.append(gap)
    coverage["complete"] = False
    result["gate_version"] = GATE_VERSION
    result["verdict"] = "INCOMPLETE"
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
    except ArgumentParseError:
        _emit_error(None)
        return 3
    if arguments.reviewed_findings_sha256 is not None and not arguments.gate:
        _emit_error(None)
        return 3
    deadline = time.monotonic() + max(0, arguments.timeout_seconds)
    if arguments.gate:
        try:
            _validate_gate_output_path(
                arguments.root,
                arguments.output,
                timeout_seconds=arguments.timeout_seconds,
                deadline=deadline,
            )
        except (GitCommandError, OSError, ValueError):
            _emit_error(None)
            return 3
    try:
        result = scan_repository(
            arguments.root,
            max_blob_bytes=arguments.max_blob_bytes,
            timeout_seconds=arguments.timeout_seconds,
            deadline=deadline,
            max_work_units=arguments.max_work_units,
        )
        if arguments.gate:
            try:
                result = enhance_pre_push_audit(
                    arguments.root,
                    result,
                    max_blob_bytes=arguments.max_blob_bytes,
                    timeout_seconds=arguments.timeout_seconds,
                    deadline=deadline,
                    max_work_units=arguments.max_work_units,
                    reviewed_findings_sha256=arguments.reviewed_findings_sha256,
                )
            except GitBudgetExceeded:
                result = redact_pre_push_result(
                    _mark_gate_budget_incomplete(
                        result,
                        "strict pre-push gate budget exhausted",
                    )
                )
            except GitCommandError:
                result = redact_pre_push_result(
                    _mark_gate_budget_incomplete(
                        result,
                        "strict pre-push gate could not complete its Git inspection",
                    )
                )
        document = (
            _json_document(result)
            if arguments.format == "json"
            else _text_document(result)
        )
        _write_or_print(document, arguments.output)
    except (GitCommandError, subprocess.TimeoutExpired, OSError, ValueError):
        _emit_error(arguments.output)
        return 3
    coverage = result["coverage"]
    assert isinstance(coverage, dict)
    if coverage["complete"] is not True:
        return 2
    if arguments.gate:
        return gate_exit_code(result, fail_on=arguments.fail_on)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
