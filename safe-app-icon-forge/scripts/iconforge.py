#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.iconforge_lib.build import (
    _renderer_identity,
    _review_input_for,
    build_project,
    initialize_project,
    plan_project,
    preview_project,
    validate_project_inputs,
)
from scripts.iconforge_lib.config import SKILL_VERSION
from scripts.iconforge_lib.errors import IconforgeError, PathSafetyError
from scripts.iconforge_lib.paths import confined_path, relative_posix
from scripts.iconforge_lib.renderer import create_updated_lock, load_locked_renderer, renderer_info
from scripts.iconforge_lib.svg_safe import sanitize_svg
from scripts.iconforge_lib.verify import verify_output

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LOCK_ID = "inkscape-default"


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit one canonical JSON object")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iconforge",
        description="Design-support, safe build, verification, and deterministic packaging for dual-tier app icons.",
    )
    parser.add_argument("--version", action="version", version=f"safe-app-icon-forge {SKILL_VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="create a new project from the bundled pending-review template")
    init_parser.add_argument("project", help="new project directory relative to the invocation directory")
    _json_flag(init_parser)

    inspect_parser = commands.add_parser("inspect-svg", help="sanitize one untrusted SVG without rendering")
    inspect_parser.add_argument("svg", help="SVG path relative to the invocation directory")
    _json_flag(inspect_parser)

    validate_parser = commands.add_parser("validate-project", help="validate project data, SVGs, review, and renderer lock")
    validate_parser.add_argument("project", help="project directory relative to the invocation directory")
    _json_flag(validate_parser)

    plan_parser = commands.add_parser("plan", help="perform a true dry-run without renderer or output writes")
    plan_parser.add_argument("project", help="project directory relative to the invocation directory")
    _json_flag(plan_parser)

    preview_parser = commands.add_parser("preview", help="render review assets before final visual approval")
    preview_parser.add_argument("project", help="project directory relative to the invocation directory")
    preview_parser.add_argument("--output", required=True, help="new preview directory relative to the invocation directory")
    _json_flag(preview_parser)

    build_parser = commands.add_parser("build", help="build, verify, and atomically publish an icon package")
    build_parser.add_argument("project", help="project directory relative to the invocation directory")
    build_parser.add_argument("--output", required=True, help="new output directory relative to the invocation directory")
    build_parser.add_argument("--replace", action="store_true", help="replace a verified output using backup and rollback")
    _json_flag(build_parser)

    verify_parser = commands.add_parser("verify", help="independently verify an output directory or project package ZIP")
    verify_parser.add_argument("target", help="directory or ZIP path relative to the invocation directory")
    _json_flag(verify_parser)

    compare_parser = commands.add_parser("compare", help="require two verified builds to have byte-identical project ZIPs")
    compare_parser.add_argument("first", help="first output directory or project ZIP")
    compare_parser.add_argument("second", help="second output directory or project ZIP")
    _json_flag(compare_parser)

    info_parser = commands.add_parser("renderer-info", help="show the locked local Inkscape identity")
    info_parser.add_argument("--lock-id", default=_DEFAULT_LOCK_ID)
    _json_flag(info_parser)

    update_parser = commands.add_parser("update-renderer-lock", help="write a separate reviewed lock candidate for a trusted local executable")
    update_parser.add_argument("--trusted-executable", required=True, help="absolute path to a trusted inkscape executable")
    update_parser.add_argument("--output", required=True, help="new lock file path relative to the invocation directory")
    update_parser.add_argument("--lock-id", default=_DEFAULT_LOCK_ID)
    _json_flag(update_parser)
    return parser


def _canonical_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _invocation_root(value: Path | None) -> Path:
    root = Path.cwd() if value is None else Path(value)
    try:
        mode = root.lstat().st_mode
    except OSError as exc:
        raise PathSafetyError(f"invocation root is unavailable: {root}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise PathSafetyError("invocation root must be a non-symlink directory")
    return root.resolve(strict=True)


def _redact(message: str, root: Path | None) -> str:
    if root is None:
        return message
    return message.replace(str(root), ".")


def _human(report: dict[str, Any]) -> str:
    if report.get("ok") is False:
        error = report["error"]
        return f"ERROR [{error['code']}]: {error['message']}\n"
    lines = ["OK"]
    for key, value in report.items():
        if key == "ok":
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _emit(stream: TextIO, report: dict[str, Any], *, json_mode: bool) -> None:
    stream.write(_canonical_line(report) if json_mode else _human(report))
    stream.flush()


def main(
    argv: list[str] | None = None,
    *,
    invocation_root: Path | None = None,
    renderer: Any | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    root: Path | None = None
    json_mode = "--json" in (sys.argv[1:] if argv is None else argv)
    try:
        args = _parser().parse_args(argv)
        json_mode = bool(getattr(args, "json", False))
        root = _invocation_root(invocation_root)

        if args.command == "init":
            project_dir = confined_path(root, args.project, must_exist=False)
            initialized = initialize_project(project_dir)
            report = {
                "ok": True,
                "project": relative_posix(initialized.project_path, root),
                "project_id": initialized.project_id,
                "project_version": initialized.project_version,
                "review_status": initialized.review_status,
                "release_ready": False,
            }
        elif args.command == "inspect-svg":
            source = confined_path(root, args.svg, must_exist=True, require_file=True)
            sanitized = sanitize_svg(source)
            report = {
                "ok": True,
                "svg": relative_posix(source, root),
                "sha256": sanitized.sha256,
                "geometry_sha256": sanitized.geometry_sha256,
                "sanitized_bytes": len(sanitized.data),
                "view_box": list(sanitized.viewbox),
                "element_count": sanitized.element_count,
                "attribute_count": sanitized.attribute_count,
            }
        elif args.command == "validate-project":
            project_dir = confined_path(root, args.project, must_exist=True)
            validated = validate_project_inputs(project_dir, require_final_review=False)
            if renderer is None:
                with tempfile.TemporaryDirectory(prefix="iconforge-validate-", dir=root) as temporary:
                    checked = load_locked_renderer(
                        _REPOSITORY_ROOT,
                        Path(temporary),
                        expected_lock_id=validated.config.renderer_lock_id,
                        project_root=validated.config.project_dir,
                    )
                    identity = checked.identity
            else:
                identity = _renderer_identity(
                    renderer, expected_lock_id=validated.config.renderer_lock_id
                )
            review_input = _review_input_for(validated, identity)
            review_source_matches = validated.visual_review.matches_source(
                review_input.review_source_sha256
            )
            review_input_matches = validated.visual_review.matches_input(
                review_input.review_input_sha256
            )
            report = {
                "ok": True,
                "project": relative_posix(project_dir, root),
                "id": validated.config.project.id,
                "version": validated.config.project.version,
                "bundle_name": validated.config.bundle_name,
                "large_svg_sha256": validated.large.sha256,
                "small_svg_sha256": validated.small.sha256,
                "large_geometry_sha256": validated.large.geometry_sha256,
                "small_geometry_sha256": validated.small.geometry_sha256,
                "style_lock_sha256": None if validated.style_lock is None else validated.style_lock.sha256,
                "provenance_entries": validated.provenance.entry_count,
                "visual_review_total": validated.visual_review.final_total,
                "visual_review_status": validated.visual_review.status,
                "visual_review_draft": validated.visual_review.draft,
                "review_source_sha256": review_input.review_source_sha256,
                "review_input_sha256": review_input.review_input_sha256,
                "review_source_matches": review_source_matches,
                "review_input_matches": review_input_matches,
                "review_output_recorded": validated.visual_review.review_output_sha256 is not None,
                "review_state_ready": (
                    validated.visual_review.status == "pass"
                    and review_source_matches
                    and review_input_matches
                    and validated.visual_review.review_output_sha256 is not None
                ),
                "rendered_output_binding_checked": False,
                "release_ready": False,
                "renderer": identity if isinstance(identity, dict) else {
                    "name": identity.name,
                    "version": identity.version,
                    "lock_id": identity.lock_id,
                    "executable_sha256": identity.executable_sha256,
                },
            }
        elif args.command == "plan":
            project_dir = confined_path(root, args.project, must_exist=True)
            report = plan_project(project_dir)
            report["project_path"] = relative_posix(project_dir, root)
        elif args.command == "preview":
            project_dir = confined_path(root, args.project, must_exist=True)
            output = confined_path(root, args.output, must_exist=False)
            result = preview_project(project_dir, output, renderer=renderer)
            report = {
                "ok": True,
                "output": relative_posix(result.output_path, root),
                "review_svg": relative_posix(result.review_svg_path, root),
                "review_png": relative_posix(result.review_png_path, root),
                "review_evidence": relative_posix(result.review_evidence_path, root),
                "png_count": result.png_count,
                "ico_frame_count": result.ico_frame_count,
                "review_status": result.review_status,
                "review_source_sha256": result.review_source_sha256,
                "review_input_sha256": result.review_input_sha256,
                "review_output_sha256": result.review_output_sha256,
                "review_required": not result.review_matches_current_assets,
                "review_matches_current_assets": result.review_matches_current_assets,
                "release_ready": False,
            }
        elif args.command == "build":
            project_dir = confined_path(root, args.project, must_exist=True)
            output = confined_path(root, args.output, must_exist=False)
            result = build_project(project_dir, output, renderer=renderer, replace=args.replace)
            report = {
                "ok": True,
                "output": relative_posix(result.output_path, root),
                "backup": relative_posix(result.backup_path, root) if result.backup_path is not None else None,
                "project_id": result.verification.project_id,
                "project_version": result.verification.project_version,
                "file_count": result.verification.file_count,
                "archive_sha256": result.verification.archive_sha256,
            }
        elif args.command == "verify":
            target = confined_path(root, args.target, must_exist=True)
            verified = verify_output(target)
            report = {
                "ok": True,
                "target": relative_posix(target, root),
                "project_id": verified.project_id,
                "project_version": verified.project_version,
                "file_count": verified.file_count,
                "archive_sha256": verified.archive_sha256,
                "package_only": verified.package_only,
            }
        elif args.command == "compare":
            first = confined_path(root, args.first, must_exist=True)
            second = confined_path(root, args.second, must_exist=True)
            first_report = verify_output(first)
            second_report = verify_output(second)
            if (first_report.project_id, first_report.project_version) != (
                second_report.project_id,
                second_report.project_version,
            ):
                raise IconforgeError("verified rebuilds identify different projects or versions")
            if first_report.archive_sha256 != second_report.archive_sha256:
                raise IconforgeError("verified rebuild project ZIPs are not byte-identical")
            report = {
                "ok": True,
                "first": relative_posix(first, root),
                "second": relative_posix(second, root),
                "project_id": first_report.project_id,
                "project_version": first_report.project_version,
                "archive_sha256": first_report.archive_sha256,
                "byte_identical": True,
            }
        elif args.command == "renderer-info":
            with tempfile.TemporaryDirectory(prefix="iconforge-renderer-info-", dir=root) as temporary:
                identity = renderer_info(_REPOSITORY_ROOT, Path(temporary), expected_lock_id=args.lock_id)
            report = {
                "ok": True,
                "renderer": {
                    "name": identity.name,
                    "version": identity.version,
                    "lock_id": identity.lock_id,
                    "executable_sha256": identity.executable_sha256,
                    "executable": identity.executable,
                },
            }
        elif args.command == "update-renderer-lock":
            output = confined_path(root, args.output, must_exist=False)
            value = create_updated_lock(Path(args.trusted_executable), output, lock_id=args.lock_id)
            report = {
                "ok": True,
                "output": relative_posix(output, root),
                "lock": value,
                "review_required": True,
            }
        else:  # pragma: no cover
            raise IconforgeError("unsupported command")

        _emit(stdout, report, json_mode=json_mode)
        return 0
    except KeyboardInterrupt:
        report = {
            "ok": False,
            "error": {"code": "interrupted", "type": "KeyboardInterrupt", "message": "operation interrupted"},
        }
        _emit(stderr, report, json_mode=json_mode)
        return 130
    except (IconforgeError, OSError) as exc:
        message = _redact(str(exc), root)
        code = getattr(exc, "code", "os_error")
        context = getattr(exc, "context", {})
        report = {
            "ok": False,
            "error": {"code": code, "type": type(exc).__name__, "message": message, "context": context},
        }
        _emit(stderr, report, json_mode=json_mode)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
