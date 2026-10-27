from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ProjectConfig, SKILL_VERSION, load_project
from .errors import BuildError, IconforgeError, PngError, VerificationError
from .ico import build_ico
from .json_safe import canonical_json_bytes
from .package import create_deterministic_zip
from .png import PngInfo, normalize_png_with_info
from .preview import build_review_svg
from .provenance import Provenance, load_provenance
from .renderer import RendererIdentity, load_locked_renderer
from .review_binding import (
    ReviewEvidence,
    ReviewInput,
    make_review_evidence,
    make_review_input,
    make_review_source,
)
from .style_lock import (
    StyleLock,
    effective_quality_policy,
    load_style_lock,
    scaled_canvas_pixels,
    validate_rendered_metrics,
    validate_svg_pair_against_style_lock,
)
from .svg_safe import SanitizedSvg, sanitize_svg
from .visual_review import VisualReview, load_visual_review

_MAX_RAW_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ValidatedProject:
    config: ProjectConfig
    large: SanitizedSvg
    small: SanitizedSvg
    style_lock: StyleLock | None
    provenance: Provenance
    visual_review: VisualReview


@dataclass(frozen=True, slots=True)
class BuildResult:
    output_path: Path
    backup_path: Path | None
    verification: Any


@dataclass(frozen=True, slots=True)
class PreviewResult:
    output_path: Path
    review_svg_path: Path
    review_png_path: Path
    review_evidence_path: Path
    png_count: int
    ico_frame_count: int
    review_status: str
    review_source_sha256: str
    review_input_sha256: str
    review_output_sha256: str
    review_matches_current_assets: bool


@dataclass(frozen=True, slots=True)
class InitializedProject:
    project_path: Path
    project_id: str
    project_version: str
    review_status: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_record(data: bytes, role: str, media_type: str, **metadata: Any) -> dict[str, Any]:
    return {"bytes": len(data), "media_type": media_type, "role": role, "sha256": _sha256(data), **metadata}


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise BuildError(f"unsafe output parent: {path.parent}")
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            path.chmod(0o644)
        except OSError:
            pass
    except FileExistsError as exc:
        raise BuildError(f"refusing to overwrite staged file: {path}") from exc


def _check_existing_ancestors(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    for component in [*reversed(absolute.parents), absolute]:
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise BuildError(f"cannot inspect output path component: {component}") from exc
        if stat.S_ISLNK(mode):
            raise BuildError(f"symlink output path component is forbidden: {component}")


def _prepare_output_path(output: Path) -> Path:
    output = Path(os.path.abspath(output))
    if not output.name or output.name in {".", ".."} or "\x00" in output.name:
        raise BuildError("output directory name is invalid")
    _check_existing_ancestors(output.parent)
    if not output.parent.exists() or not output.parent.is_dir() or output.parent.is_symlink():
        raise BuildError("output parent must be an existing non-symlink directory")
    if output.exists() or output.is_symlink():
        mode = output.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise BuildError("existing output must be a regular non-symlink directory")
    return output


def _read_raw_once(path: Path) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BuildError(f"cannot open renderer output safely: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_RAW_BYTES:
            raise BuildError("renderer output is not a bounded regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, _MAX_RAW_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_RAW_BYTES:
                raise BuildError("renderer output exceeds the raw-file size limit")
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev or before.st_ino != after.st_ino or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns or total != after.st_size
        ):
            raise BuildError("renderer output changed while it was being sealed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _render_png(
    renderer: Any,
    *,
    source: Path,
    raw_root: Path,
    token: str,
    width: int,
    height: int,
    require_transparency: bool,
    require_transparent_corners: bool,
    minimum_safe_margin: int,
    analyze_metrics: bool = True,
) -> tuple[bytes, PngInfo]:
    render_dir = raw_root / token
    render_dir.mkdir(parents=True, exist_ok=False)
    raw_path = render_dir / "raw.png"
    try:
        renderer.render(source, raw_path, width, height)
        return normalize_png_with_info(
            _read_raw_once(raw_path),
            expected_width=width,
            expected_height=height,
            require_transparency=require_transparency,
            require_transparent_corners=require_transparent_corners,
            minimum_safe_margin=minimum_safe_margin,
            analyze_metrics=analyze_metrics,
        )
    except PngError as exc:
        raise BuildError(f"renderer produced an invalid {width}x{height} PNG: {exc}") from exc
    except IconforgeError:
        raise
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        raise BuildError(f"renderer failed for {width}x{height}: {exc}") from exc
    finally:
        shutil.rmtree(render_dir, ignore_errors=True)


def validate_project_inputs(
    project_dir: Path,
    *,
    require_final_review: bool = True,
    require_design_ready: bool = False,
) -> ValidatedProject:
    try:
        config = load_project(Path(project_dir))
        large = sanitize_svg(config.large_svg)
        small = sanitize_svg(config.small_svg)
        if large.geometry_sha256 == small.geometry_sha256:
            raise BuildError("small SVG is geometrically identical to large SVG; a separate optical redraw is required")
        style_lock = (
            None
            if config.style_lock_path is None
            else load_style_lock(config.style_lock_path, expected_preset=config.preset)
        )
        if style_lock is not None:
            validate_svg_pair_against_style_lock(style_lock, large.data, small.data)
        provenance = load_provenance(config.provenance_path)
        visual_review = load_visual_review(config.visual_review_path, require_pass=require_final_review)
        if require_design_ready and visual_review.draft:
            raise BuildError(
                "visual review is still a draft; replace the starter brief, concepts, and SVGs, "
                "then set draft to false before preview"
            )
        return ValidatedProject(config, large, small, style_lock, provenance, visual_review)
    except BuildError:
        raise
    except IconforgeError as exc:
        raise BuildError(str(exc)) from exc


def _minimum_margin(style_lock: StyleLock | None, size: int) -> int:
    policy = effective_quality_policy(style_lock)
    return scaled_canvas_pixels(policy.safe_margin_px, size)


def _renderer_identity(renderer: Any, *, expected_lock_id: str) -> RendererIdentity:
    identity = getattr(renderer, "identity", None)
    if isinstance(identity, RendererIdentity):
        result = identity
    else:
        name = getattr(renderer, "name", None)
        version = getattr(renderer, "version", None)
        render = getattr(renderer, "render", None)
        lock_id = getattr(renderer, "lock_id", expected_lock_id)
        executable_hash = getattr(renderer, "executable_sha256", _sha256(f"{name}:{version}".encode("utf-8")))
        executable = getattr(renderer, "executable", "test-double")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version or not callable(render):
            raise BuildError("renderer object does not implement name, version, and render")
        result = RendererIdentity(name, version, lock_id, executable_hash, str(executable))
    if result.lock_id != expected_lock_id:
        raise BuildError(f"renderer lock id {result.lock_id!r} does not match project {expected_lock_id!r}")
    if len(result.executable_sha256) != 64:
        raise BuildError("renderer identity has an invalid executable SHA-256")
    return result


def _review_source_for(project: ValidatedProject):
    return make_review_source(
        iconforge_sha256=project.config.sha256,
        large_svg_sha256=project.large.sha256,
        small_svg_sha256=project.small.sha256,
        style_lock_sha256=None if project.style_lock is None else project.style_lock.sha256,
    )


def _review_input_for(project: ValidatedProject, identity: RendererIdentity) -> ReviewInput:
    return make_review_input(
        iconforge_sha256=project.config.sha256,
        large_svg_sha256=project.large.sha256,
        small_svg_sha256=project.small.sha256,
        style_lock_sha256=None if project.style_lock is None else project.style_lock.sha256,
        renderer=identity,
    )


def _require_current_review_input(project: ValidatedProject, review_input: ReviewInput) -> None:
    review = project.visual_review
    if not review.matches_source(review_input.review_source_sha256):
        raise BuildError(
            "final visual review is stale: source/config/style inputs no longer match the approved preview"
        )
    if not review.matches_input(review_input.review_input_sha256):
        raise BuildError(
            "final visual review is stale: renderer identity or environment no longer matches the approved preview"
        )


def _source_record(svg: SanitizedSvg, role: str) -> dict[str, Any]:
    return _file_record(
        svg.data,
        f"source-svg-{role}",
        "image/svg+xml",
        view_box=list(svg.viewbox),
        geometry_sha256=svg.geometry_sha256,
        element_count=svg.element_count,
        attribute_count=svg.attribute_count,
    )


def _next_backup_path(output: Path) -> Path:
    for index in range(1, 10_000):
        candidate = output.with_name(f"{output.name}.backup-{index:04d}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise BuildError("no free recoverable backup name is available")


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _build_in_staging(
    project: ValidatedProject,
    staging: Path,
    *,
    renderer: Any | None,
    release: bool = True,
) -> Any:
    from .verify import verify_output

    config = project.config
    raw_root = staging / ".raw"
    raw_root.mkdir(mode=0o700)
    runtime_root = staging / ".runtime"
    if renderer is None:
        repository_root = Path(__file__).resolve().parents[2]
        renderer = load_locked_renderer(
            repository_root,
            runtime_root,
            expected_lock_id=config.renderer_lock_id,
            project_root=config.project_dir,
        )
    identity = _renderer_identity(renderer, expected_lock_id=config.renderer_lock_id)
    review_input = _review_input_for(project, identity)
    if release:
        _require_current_review_input(project, review_input)

    config_member = "source/iconforge.json"
    _write_exclusive(staging / config_member, config.canonical)
    file_records: dict[str, dict[str, Any]] = {
        config_member: _file_record(
            config.canonical,
            "project-config",
            "application/json",
            schema_version=2,
        )
    }

    large_path = staging / "source" / "icon-large.svg"
    small_path = staging / "source" / "icon-small.svg"
    _write_exclusive(large_path, project.large.data)
    _write_exclusive(small_path, project.small.data)
    file_records.update({
        "source/icon-large.svg": _source_record(project.large, "large"),
        "source/icon-small.svg": _source_record(project.small, "small"),
    })
    if project.style_lock is not None:
        member = "source/style-lock.json"
        _write_exclusive(staging / member, project.style_lock.canonical)
        file_records[member] = _file_record(
            project.style_lock.canonical,
            "style-lock",
            "application/json",
            style_id=project.style_lock.style_id,
            style_version=project.style_lock.style_version,
            preset_id=project.style_lock.preset_id,
            preset_version=project.style_lock.preset_version,
        )

    provenance_member = "provenance.json"
    _write_exclusive(staging / provenance_member, project.provenance.canonical)
    file_records[provenance_member] = _file_record(
        project.provenance.canonical,
        "provenance",
        "application/json",
        entry_count=project.provenance.entry_count,
    )
    visual_member = "review/visual-review.json"
    _write_exclusive(staging / visual_member, project.visual_review.canonical)
    file_records[visual_member] = _file_record(
        project.visual_review.canonical,
        "visual-review",
        "application/json",
        status=project.visual_review.status,
        total=project.visual_review.final_total,
        selected_concept=project.visual_review.selected_concept,
    )

    pngs: dict[int, bytes] = {}
    png_infos: dict[int, PngInfo] = {}
    routing: dict[int, str] = {}
    margins: dict[int, int] = {}
    quality_policy = effective_quality_policy(project.style_lock)
    require_corners = quality_policy.transparent_corners
    full_bleed = quality_policy.full_bleed_allowed
    for size in config.png_sizes:
        tier = config.source_tier(size)
        source = small_path if tier == "small" else large_path
        margin = 0 if full_bleed else _minimum_margin(project.style_lock, size)
        normalized, info = _render_png(
            renderer,
            source=source,
            raw_root=raw_root,
            token=f"icon-{size}",
            width=size,
            height=size,
            require_transparency=not full_bleed,
            require_transparent_corners=require_corners,
            minimum_safe_margin=margin,
        )
        validate_rendered_metrics(project.style_lock, info, size)
        member = f"exports/png/{config.project.id}-{size}.png"
        _write_exclusive(staging / member, normalized)
        pngs[size] = normalized
        png_infos[size] = info
        routing[size] = tier
        margins[size] = margin
        source_hash = project.small.sha256 if tier == "small" else project.large.sha256
        file_records[member] = _file_record(
            normalized,
            "png-export",
            "image/png",
            width=size,
            height=size,
            source_tier=tier,
            source_svg_sha256=source_hash,
            alpha_bbox=list(info.alpha_bbox),
            safe_margin=list(info.safe_margin),
            visual_weight=round(info.visual_weight, 8),
            optical_center=[round(info.optical_center[0], 8), round(info.optical_center[1], 8)],
        )

    ico_bytes = build_ico({size: pngs[size] for size in config.ico_sizes})
    ico_member = f"exports/windows/{config.project.id}.ico"
    _write_exclusive(staging / ico_member, ico_bytes)
    ico_frames = [
        {"size": size, "sha256": _sha256(pngs[size]), "source_tier": routing[size]}
        for size in config.ico_sizes
    ]
    file_records[ico_member] = _file_record(
        ico_bytes, "windows-ico", "image/vnd.microsoft.icon", frames=ico_frames
    )

    sheet = build_review_svg(
        config.project.id, pngs, routing, safe_margin_by_size=margins, prevalidated_infos=png_infos
    )
    review_svg_member = f"review/{config.project.id}-review.svg"
    review_png_member = f"review/{config.project.id}-review.png"
    review_svg_path = staging / review_svg_member
    _write_exclusive(review_svg_path, sheet.data)
    review_png, _review_info = _render_png(
        renderer,
        source=review_svg_path,
        raw_root=raw_root,
        token="review-sheet",
        width=sheet.width,
        height=sheet.height,
        require_transparency=False,
        require_transparent_corners=False,
        minimum_safe_margin=0,
        analyze_metrics=False,
    )
    _write_exclusive(staging / review_png_member, review_png)
    file_records[review_svg_member] = _file_record(
        sheet.data,
        "review-svg",
        "image/svg+xml",
        width=sheet.width,
        height=sheet.height,
        embedded_sizes=list(sheet.embedded_sizes),
    )
    file_records[review_png_member] = _file_record(
        review_png, "review-png", "image/png", width=sheet.width, height=sheet.height
    )

    evidence: ReviewEvidence = make_review_evidence(
        review_input,
        {size: pngs[size] for size in config.png_sizes},
        review_svg=sheet.data,
        review_png=review_png,
    )
    evidence_member = "review/review-evidence.json"
    _write_exclusive(staging / evidence_member, evidence.canonical)
    file_records[evidence_member] = _file_record(
        evidence.canonical,
        "review-evidence",
        "application/json",
        review_source_sha256=evidence.review_source_sha256,
        review_input_sha256=evidence.review_input_sha256,
        review_output_sha256=evidence.review_output_sha256,
    )

    review_matches = (
        project.visual_review.matches_source(evidence.review_source_sha256)
        and project.visual_review.matches_input(evidence.review_input_sha256)
        and project.visual_review.matches_output(evidence.review_output_sha256)
    )
    if release and not project.visual_review.matches_output(evidence.review_output_sha256):
        raise BuildError(
            "final visual review is stale: rendered pixels or review sheet no longer match the approved preview"
        )

    shutil.rmtree(raw_root, ignore_errors=True)
    shutil.rmtree(runtime_root, ignore_errors=True)

    if not release:
        return {
            "review_svg": review_svg_member,
            "review_png": review_png_member,
            "review_evidence": evidence_member,
            "png_count": len(pngs),
            "ico_frame_count": len(config.ico_sizes),
            "review_source_sha256": evidence.review_source_sha256,
            "review_input_sha256": evidence.review_input_sha256,
            "review_output_sha256": evidence.review_output_sha256,
            "review_matches_current_assets": review_matches,
        }

    style_summary = None
    if project.style_lock is not None:
        style_summary = {
            "path": "source/style-lock.json",
            "style_id": project.style_lock.style_id,
            "style_version": project.style_lock.style_version,
            "sha256": project.style_lock.sha256,
        }
    preset_summary = None if config.preset is None else {"id": config.preset.id, "version": config.preset.version}
    package_members = tuple(sorted((*file_records.keys(), "manifest.json", "SHA256SUMS")))
    manifest = {
        "manifest_schema_version": 3,
        "tool": "safe-app-icon-forge",
        "skill_version": SKILL_VERSION,
        "project": {"id": config.project.id, "title": config.project.title, "version": config.project.version},
        "preset": preset_summary,
        "style_lock": style_summary,
        "quality_policy": {
            "id": quality_policy.policy_id,
            "safe_margin_px": quality_policy.safe_margin_px,
            "optical_center_tolerance_px": quality_policy.optical_center_tolerance_px,
            "visual_weight_minimum": quality_policy.visual_weight_minimum,
            "visual_weight_maximum": quality_policy.visual_weight_maximum,
            "transparent_corners": quality_policy.transparent_corners,
            "full_bleed_allowed": quality_policy.full_bleed_allowed,
        },
        "renderer": {
            "name": identity.name,
            "version_output": identity.version,
            "lock_id": identity.lock_id,
            "executable_sha256": identity.executable_sha256,
            "platform": platform.system().lower(),
            "machine": platform.machine().lower() or "unknown",
            "python_version": sys.version.split()[0],
        },
        "formats": {"png_sizes": list(config.png_sizes), "ico_sizes": list(config.ico_sizes)},
        "routing": {
            "png": {str(size): routing[size] for size in config.png_sizes},
            "ico": {str(size): routing[size] for size in config.ico_sizes},
        },
        "provenance": {
            "path": provenance_member,
            "entry_count": project.provenance.entry_count,
            "sha256": project.provenance.sha256,
        },
        "visual_review": {
            "path": visual_member,
            "status": project.visual_review.status,
            "total": project.visual_review.final_total,
            "selected_concept": project.visual_review.selected_concept,
            "sha256": project.visual_review.sha256,
            "review_source_sha256": evidence.review_source_sha256,
            "review_input_sha256": evidence.review_input_sha256,
            "review_output_sha256": evidence.review_output_sha256,
        },
        "review_evidence": {
            "path": evidence_member,
            "sha256": evidence.sha256,
            "review_source_sha256": evidence.review_source_sha256,
            "review_input_sha256": evidence.review_input_sha256,
            "review_output_sha256": evidence.review_output_sha256,
        },
        "deterministic_build_format_version": 2,
        "files": file_records,
        "package_members": list(package_members),
    }
    manifest_bytes = canonical_json_bytes(manifest)
    _write_exclusive(staging / "manifest.json", manifest_bytes)

    checksum_members = tuple(sorted((*file_records.keys(), "manifest.json")))
    checksum_data = b"".join(
        f"{_sha256((staging / member).read_bytes())}  {member}\n".encode("ascii")
        for member in checksum_members
    )
    _write_exclusive(staging / "SHA256SUMS", checksum_data)

    archive_name = f"{config.bundle_name}.zip"
    archive_bytes = create_deterministic_zip(staging, staging / archive_name, package_members)
    _write_exclusive(
        staging / f"{archive_name}.sha256",
        f"{_sha256(archive_bytes)}  {archive_name}\n".encode("ascii"),
    )
    return verify_output(staging)


def plan_project(project_dir: Path) -> dict[str, Any]:
    project = validate_project_inputs(project_dir, require_final_review=False)
    config = project.config
    review_source = _review_source_for(project)
    source_matches = project.visual_review.matches_source(review_source.review_source_sha256)
    return {
        "ok": True,
        "project": {"id": config.project.id, "title": config.project.title, "version": config.project.version},
        "bundle_name": config.bundle_name,
        "png_routing": {str(size): config.source_tier(size) for size in config.png_sizes},
        "ico_routing": {str(size): config.source_tier(size) for size in config.ico_sizes},
        "large_svg_sha256": project.large.sha256,
        "small_svg_sha256": project.small.sha256,
        "style_lock_sha256": None if project.style_lock is None else project.style_lock.sha256,
        "provenance_entries": project.provenance.entry_count,
        "visual_review": {
            "status": project.visual_review.status,
            "total": project.visual_review.final_total,
            "draft": project.visual_review.draft,
            "selected_concept_total": project.visual_review.selected_concept_total,
        },
        "review_source_sha256": review_source.review_source_sha256,
        "review_source_matches": source_matches,
        "renderer_binding_checked": False,
        "review_state_ready": project.visual_review.status == "pass" and source_matches,
        "release_ready": False,
        "writes_output": False,
        "runs_renderer": False,
    }


def initialize_project(output: Path) -> InitializedProject:
    output = _prepare_output_path(output)
    if output.exists():
        raise BuildError(f"refusing to overwrite existing project directory: {output}")
    template = Path(__file__).resolve().parents[2] / "assets" / "template-project"
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.init-", dir=output.parent))
    published = False
    try:
        shutil.copytree(template, staging, dirs_exist_ok=True)
        project = validate_project_inputs(staging, require_final_review=False)
        if output.exists() or output.is_symlink():
            raise BuildError("project path appeared during initialization; refusing to overwrite it")
        os.rename(staging, output)
        published = True
        _fsync_directory(output.parent)
        return InitializedProject(
            project_path=output,
            project_id=project.config.project.id,
            project_version=project.config.project.version,
            review_status=project.visual_review.status,
        )
    except BuildError:
        raise
    except IconforgeError as exc:
        raise BuildError(str(exc)) from exc
    except Exception as exc:
        raise BuildError(f"project initialization failed: {exc}") from exc
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def preview_project(project_dir: Path, output: Path, *, renderer: Any | None = None) -> PreviewResult:
    project = validate_project_inputs(
        Path(project_dir), require_final_review=False, require_design_ready=True
    )
    output = _prepare_output_path(output)
    try:
        output.relative_to(project.config.project_dir)
    except ValueError:
        pass
    else:
        raise BuildError("preview output directory must be outside the untrusted project root")
    if output.exists():
        raise BuildError(f"refusing to overwrite existing preview output directory: {output}")

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.preview-", dir=output.parent))
    published = False
    try:
        details = _build_in_staging(project, staging, renderer=renderer, release=False)
        if output.exists() or output.is_symlink():
            raise BuildError("preview output path appeared during build; refusing to overwrite it")
        os.rename(staging, output)
        published = True
        _fsync_directory(output.parent)
        return PreviewResult(
            output_path=output,
            review_svg_path=output / details["review_svg"],
            review_png_path=output / details["review_png"],
            review_evidence_path=output / details["review_evidence"],
            png_count=details["png_count"],
            ico_frame_count=details["ico_frame_count"],
            review_status=project.visual_review.status,
            review_source_sha256=details["review_source_sha256"],
            review_input_sha256=details["review_input_sha256"],
            review_output_sha256=details["review_output_sha256"],
            review_matches_current_assets=details["review_matches_current_assets"],
        )
    except BuildError:
        raise
    except IconforgeError as exc:
        raise BuildError(str(exc)) from exc
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        raise BuildError(f"preview build failed: {exc}") from exc
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def build_project(
    project_dir: Path,
    output: Path,
    *,
    renderer: Any | None = None,
    replace: bool = False,
) -> BuildResult:
    from .verify import verify_output

    project = validate_project_inputs(Path(project_dir))
    output = _prepare_output_path(output)
    try:
        output.relative_to(project.config.project_dir)
    except ValueError:
        pass
    else:
        raise BuildError("output directory must be outside the untrusted project root")
    existing = output.exists()
    if existing and not replace:
        raise BuildError(f"refusing to overwrite existing output directory: {output}")
    if existing:
        try:
            verify_output(output)
        except VerificationError as exc:
            raise BuildError(f"existing output is not a valid recoverable package: {exc}") from exc

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        staging.chmod(0o700)
    except OSError:
        pass
    backup: Path | None = None
    published = False
    try:
        _build_in_staging(project, staging, renderer=renderer)
        if existing:
            if not output.exists() or output.is_symlink():
                raise BuildError("existing output changed before recoverable replacement")
            backup = _next_backup_path(output)
            os.rename(output, backup)
            _fsync_directory(output.parent)
            try:
                if output.exists() or output.is_symlink():
                    raise BuildError("output path was recreated during replacement")
                os.rename(staging, output)
                published = True
                _fsync_directory(output.parent)
            except Exception:
                if not output.exists() and backup.exists():
                    os.rename(backup, output)
                    _fsync_directory(output.parent)
                raise
        else:
            if output.exists() or output.is_symlink():
                raise BuildError("output path appeared during build; refusing to overwrite it")
            os.rename(staging, output)
            published = True
            _fsync_directory(output.parent)

        try:
            final_verification = verify_output(output)
        except Exception as final_error:
            try:
                if output.exists() or output.is_symlink():
                    os.rename(output, staging)
                if backup is not None and backup.exists():
                    os.rename(backup, output)
                published = False
                _fsync_directory(output.parent)
            except Exception as rollback_error:
                raise BuildError(
                    f"final verification failed ({final_error}); rollback also failed: {rollback_error}"
                ) from rollback_error
            raise
        return BuildResult(output, backup, final_verification)
    except BuildError:
        raise
    except IconforgeError as exc:
        raise BuildError(str(exc)) from exc
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        raise BuildError(f"build failed: {exc}") from exc
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
