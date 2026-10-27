from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PresetRef, SKILL_VERSION, is_semver
from .errors import (
    IcoError, JsonSecurityError, PngError, StyleLockError, SvgSecurityError,
    VerificationError, VisualReviewError,
)
from .ico import inspect_ico
from .json_safe import canonical_json_bytes, loads_strict
from .package import open_safe_zip, read_zip_member, validate_archive_name
from .png import encode_rgba_png, inspect_png
from .preview import build_review_svg
from .provenance import load_provenance
from .review_binding import load_review_evidence_bytes
from .style_lock import (
    effective_quality_policy,
    load_style_lock,
    scaled_canvas_pixels,
    validate_rendered_metrics,
    validate_svg_pair_against_style_lock,
)
from .svg_safe import sanitize_svg_bytes
from .visual_review import load_visual_review

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_OUTPUT_FILE_BYTES = 64 * 1024 * 1024
_MAX_OUTPUT_TOTAL_BYTES = 128 * 1024 * 1024
_TOP_KEYS = {
    "manifest_schema_version", "tool", "skill_version", "project", "preset", "style_lock",
    "renderer", "quality_policy", "formats", "routing", "provenance", "visual_review",
    "review_evidence", "deterministic_build_format_version", "files", "package_members",
}
_COMMON_RECORD = {"bytes", "media_type", "role", "sha256"}
_FORBIDDEN_EXTENSIONS = {
    ".sh", ".bash", ".zsh", ".fish", ".bat", ".cmd", ".com", ".exe", ".dll", ".so", ".dylib",
    ".ps1", ".py", ".pyc", ".js", ".mjs", ".cjs", ".jar", ".msi", ".scr",
}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    output_path: Path
    project_id: str
    project_version: str
    file_count: int
    archive_sha256: str
    package_only: bool = False

    @property
    def name(self) -> str:
        return self.project_id


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerificationError(f"{label} must be an object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise VerificationError(f"{label} key mismatch; missing={missing}, unknown={unknown}")
    return value


def _int_list(value: Any, *, label: str, maximum: int) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise VerificationError(f"{label} must be a non-empty array")
    if any(isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= maximum for item in value):
        raise VerificationError(f"{label} has unsupported entries")
    if value != sorted(value) or len(value) != len(set(value)):
        raise VerificationError(f"{label} must be sorted and unique")
    return tuple(value)


def _read_regular(path: Path, *, maximum: int = _MAX_OUTPUT_FILE_BYTES) -> bytes:
    try:
        initial = path.lstat()
    except OSError as exc:
        raise VerificationError(f"required file is unavailable: {path}") from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise VerificationError(f"output member is not a regular non-symlink file: {path}")
    if initial.st_size > maximum:
        raise VerificationError(f"output member exceeds the size limit: {path}")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise VerificationError(f"output member exceeds the size limit: {path}")
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev or before.st_ino != after.st_ino or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns or total != after.st_size
        ):
            raise VerificationError(f"output member changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _collect_tree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    folded: dict[str, str] = {}
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for dirname in list(dirnames):
            child = current_path / dirname
            mode = child.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise VerificationError(f"output contains an unsafe directory entry: {child}")
            relative = child.relative_to(root).as_posix()
            validate_archive_name(relative)
            fold = relative.casefold()
            if fold in folded and folded[fold] != relative:
                raise VerificationError("output contains a case-insensitive path collision")
            folded[fold] = relative
            directories.add(relative)
        for filename in filenames:
            child = current_path / filename
            mode = child.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise VerificationError(f"output contains an unsafe file entry: {child}")
            relative = child.relative_to(root).as_posix()
            validate_archive_name(relative)
            fold = relative.casefold()
            if fold in folded and folded[fold] != relative:
                raise VerificationError("output contains a case-insensitive path collision")
            folded[fold] = relative
            files.add(relative)
    return files, directories


def _preflight_directory_members(
    root: Path,
    contract: dict[str, Any],
    *,
    manifest_size: int,
    maximum_total: int = _MAX_OUTPUT_TOTAL_BYTES,
) -> int:
    """Reject oversized directory packages using metadata before any payload read."""

    total = 0
    files = contract["files"]
    for member in contract["package_members"]:
        path = root / member
        try:
            info = path.lstat()
        except OSError as exc:
            raise VerificationError(f"required output member is unavailable: {member}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise VerificationError(f"output member is not a regular non-symlink file: {member}")
        if info.st_size > _MAX_OUTPUT_FILE_BYTES:
            raise VerificationError(f"output member exceeds the size limit before read: {member}")
        if member == "manifest.json":
            declared = manifest_size
        elif member == "SHA256SUMS":
            declared = info.st_size
        else:
            record = files.get(member)
            if not isinstance(record, dict):
                raise VerificationError(f"manifest file record is unavailable before read: {member}")
            declared = record.get("bytes")
            if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
                raise VerificationError(f"manifest byte count is invalid before read: {member}")
        if info.st_size != declared:
            raise VerificationError(f"output member size differs from manifest before read: {member}")
        total += info.st_size
        if total > maximum_total:
            raise VerificationError("output cumulative package size exceeds the limit before read")
    return total


def _parse_manifest(data: bytes) -> dict[str, Any]:
    try:
        value = loads_strict(data, label="manifest.json")
    except JsonSecurityError as exc:
        raise VerificationError(str(exc)) from exc
    root = _exact(value, _TOP_KEYS, "manifest")
    if data != canonical_json_bytes(root):
        raise VerificationError("manifest.json is not canonical JSON")
    if root["manifest_schema_version"] != 3 or root["tool"] != "safe-app-icon-forge":
        raise VerificationError("manifest schema or tool identifier is unsupported")
    if root["skill_version"] != SKILL_VERSION:
        raise VerificationError(f"manifest skill_version must be {SKILL_VERSION}")
    if root["deterministic_build_format_version"] != 2:
        raise VerificationError("deterministic build format is unsupported")
    return root


def _manifest_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    project = _exact(manifest["project"], {"id", "title", "version"}, "manifest.project")
    project_id = project["id"]
    if not isinstance(project_id, str) or not _ID_RE.fullmatch(project_id) or "--" in project_id:
        raise VerificationError("manifest project id is invalid")
    if not isinstance(project["title"], str) or not project["title"].strip() or len(project["title"]) > 160:
        raise VerificationError("manifest project title is invalid")
    if not isinstance(project["version"], str) or not is_semver(project["version"]):
        raise VerificationError("manifest project version is not SemVer")

    preset_value = manifest["preset"]
    preset: PresetRef | None
    if preset_value is None:
        preset = None
    else:
        preset_obj = _exact(preset_value, {"id", "version"}, "manifest.preset")
        if not isinstance(preset_obj["id"], str) or not _ID_RE.fullmatch(preset_obj["id"]):
            raise VerificationError("manifest preset id is invalid")
        if not isinstance(preset_obj["version"], str) or not is_semver(preset_obj["version"]):
            raise VerificationError("manifest preset version is invalid")
        preset = PresetRef(preset_obj["id"], preset_obj["version"])

    style_value = manifest["style_lock"]
    if style_value is not None:
        style_obj = _exact(style_value, {"path", "style_id", "style_version", "sha256"}, "manifest.style_lock")
        if style_obj["path"] != "source/style-lock.json":
            raise VerificationError("manifest style lock path is invalid")
        if not isinstance(style_obj["style_id"], str) or not _ID_RE.fullmatch(style_obj["style_id"]):
            raise VerificationError("manifest style id is invalid")
        if not isinstance(style_obj["style_version"], str) or not is_semver(style_obj["style_version"]):
            raise VerificationError("manifest style version is invalid")
        if not isinstance(style_obj["sha256"], str) or not _SHA_RE.fullmatch(style_obj["sha256"]):
            raise VerificationError("manifest style SHA-256 is invalid")
    elif preset is not None:
        raise VerificationError("manifest preset requires a style lock")

    quality = _exact(
        manifest["quality_policy"],
        {
            "id", "safe_margin_px", "optical_center_tolerance_px",
            "visual_weight_minimum", "visual_weight_maximum",
            "transparent_corners", "full_bleed_allowed",
        },
        "manifest.quality_policy",
    )
    if not isinstance(quality["id"], str) or not quality["id"] or len(quality["id"]) > 256:
        raise VerificationError("manifest quality policy id is invalid")
    for key in ("safe_margin_px", "optical_center_tolerance_px"):
        if isinstance(quality[key], bool) or not isinstance(quality[key], int) or not 0 <= quality[key] <= 256:
            raise VerificationError(f"manifest quality policy {key} is invalid")
    for key in ("visual_weight_minimum", "visual_weight_maximum"):
        if isinstance(quality[key], bool) or not isinstance(quality[key], (int, float)) or not 0 <= quality[key] <= 1:
            raise VerificationError(f"manifest quality policy {key} is invalid")
    if quality["visual_weight_minimum"] > quality["visual_weight_maximum"]:
        raise VerificationError("manifest quality policy visual-weight range is invalid")
    if not isinstance(quality["transparent_corners"], bool) or not isinstance(quality["full_bleed_allowed"], bool):
        raise VerificationError("manifest quality policy transparency flags are invalid")
    if quality["transparent_corners"] and quality["full_bleed_allowed"]:
        raise VerificationError("manifest quality policy transparency flags conflict")

    renderer = _exact(
        manifest["renderer"],
        {"name", "version_output", "lock_id", "executable_sha256", "platform", "machine", "python_version"},
        "manifest.renderer",
    )
    if renderer["name"] != "inkscape":
        raise VerificationError("manifest renderer name must be 'inkscape'")
    for key in ("version_output", "lock_id", "platform", "machine", "python_version"):
        if not isinstance(renderer[key], str) or not renderer[key] or len(renderer[key]) > 1024:
            raise VerificationError(f"manifest renderer {key} is invalid")
    if not isinstance(renderer["executable_sha256"], str) or not _SHA_RE.fullmatch(renderer["executable_sha256"]):
        raise VerificationError("manifest renderer executable SHA-256 is invalid")

    formats = _exact(manifest["formats"], {"png_sizes", "ico_sizes"}, "manifest.formats")
    png_sizes = _int_list(formats["png_sizes"], label="manifest png_sizes", maximum=1024)
    ico_sizes = _int_list(formats["ico_sizes"], label="manifest ico_sizes", maximum=256)
    required_png = {16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024}
    required_ico = {16, 20, 24, 32, 40, 48, 64, 128, 256}
    if not required_png.issubset(png_sizes) or not required_ico.issubset(ico_sizes) or not set(ico_sizes).issubset(png_sizes):
        raise VerificationError("manifest export sizes do not satisfy the release profile")

    routing = _exact(manifest["routing"], {"png", "ico"}, "manifest.routing")
    if not isinstance(routing["png"], dict) or not isinstance(routing["ico"], dict):
        raise VerificationError("manifest routing values must be objects")
    expected_png_keys = {str(size) for size in png_sizes}
    expected_ico_keys = {str(size) for size in ico_sizes}
    if set(routing["png"]) != expected_png_keys or set(routing["ico"]) != expected_ico_keys:
        raise VerificationError("manifest routing keys do not exactly match export sizes")
    for table_name, sizes in (("png", png_sizes), ("ico", ico_sizes)):
        for size in sizes:
            tier = routing[table_name][str(size)]
            if tier not in {"small", "large"}:
                raise VerificationError("manifest routing tier is invalid")
    if {routing["png"][str(size)] for size in png_sizes} != {"small", "large"}:
        raise VerificationError("both optical tiers must be used for PNG")
    if {routing["ico"][str(size)] for size in ico_sizes} != {"small", "large"}:
        raise VerificationError("both optical tiers must be used for ICO")
    for size in (16, 20, 24, 32):
        if routing["png"].get(str(size)) != "small" or routing["ico"].get(str(size)) != "small":
            raise VerificationError(f"{size}px must route to the small source tier")
    for size in png_sizes:
        if size >= 48 and routing["png"][str(size)] != "large":
            raise VerificationError(f"{size}px must route to the large source tier")
    for size in ico_sizes:
        if size >= 48 and routing["ico"][str(size)] != "large":
            raise VerificationError(f"ICO {size}px must route to the large source tier")

    provenance = _exact(manifest["provenance"], {"path", "entry_count", "sha256"}, "manifest.provenance")
    if provenance["path"] != "provenance.json" or isinstance(provenance["entry_count"], bool) or not isinstance(provenance["entry_count"], int) or provenance["entry_count"] < 0:
        raise VerificationError("manifest provenance summary is invalid")
    if not isinstance(provenance["sha256"], str) or not _SHA_RE.fullmatch(provenance["sha256"]):
        raise VerificationError("manifest provenance SHA-256 is invalid")

    visual = _exact(
        manifest["visual_review"],
        {
            "path", "status", "total", "selected_concept", "sha256",
            "review_source_sha256", "review_input_sha256", "review_output_sha256",
        },
        "manifest.visual_review",
    )
    if visual["path"] != "review/visual-review.json" or visual["status"] != "pass":
        raise VerificationError("manifest visual review is not a pass")
    if isinstance(visual["total"], bool) or not isinstance(visual["total"], int) or not 10 <= visual["total"] <= 12:
        raise VerificationError("manifest visual review total is invalid")
    if not isinstance(visual["selected_concept"], str) or not visual["selected_concept"]:
        raise VerificationError("manifest selected concept is invalid")
    for key in ("sha256", "review_source_sha256", "review_input_sha256", "review_output_sha256"):
        if not isinstance(visual[key], str) or not _SHA_RE.fullmatch(visual[key]):
            raise VerificationError(f"manifest visual review {key} is invalid")

    evidence_summary = _exact(
        manifest["review_evidence"],
        {"path", "sha256", "review_source_sha256", "review_input_sha256", "review_output_sha256"},
        "manifest.review_evidence",
    )
    if evidence_summary["path"] != "review/review-evidence.json":
        raise VerificationError("manifest review evidence path is invalid")
    for key in ("sha256", "review_source_sha256", "review_input_sha256", "review_output_sha256"):
        if not isinstance(evidence_summary[key], str) or not _SHA_RE.fullmatch(evidence_summary[key]):
            raise VerificationError(f"manifest review evidence {key} is invalid")
    if any(
        evidence_summary[key] != visual[key]
        for key in ("review_source_sha256", "review_input_sha256", "review_output_sha256")
    ):
        raise VerificationError("manifest review and evidence binding hashes differ")

    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise VerificationError("manifest files must be a non-empty object")
    for member in files:
        validate_archive_name(member)
        if Path(member).suffix.lower() in _FORBIDDEN_EXTENSIONS:
            raise VerificationError(f"executable or script extension is forbidden in package: {member}")

    expected_files = {
        "source/iconforge.json",
        "source/icon-large.svg",
        "source/icon-small.svg",
        "provenance.json",
        "review/visual-review.json",
        "review/review-evidence.json",
        *(f"exports/png/{project_id}-{size}.png" for size in png_sizes),
        f"exports/windows/{project_id}.ico",
        f"review/{project_id}-review.svg",
        f"review/{project_id}-review.png",
    }
    if style_value is not None:
        expected_files.add("source/style-lock.json")
    if set(files) != expected_files:
        raise VerificationError(
            f"manifest file allowlist mismatch; missing={sorted(expected_files-set(files))}, extra={sorted(set(files)-expected_files)}"
        )

    package_value = manifest["package_members"]
    if not isinstance(package_value, list) or not all(isinstance(item, str) for item in package_value):
        raise VerificationError("manifest package_members must be an array of strings")
    package_members = tuple(package_value)
    expected_package = tuple(sorted((*expected_files, "manifest.json", "SHA256SUMS")))
    if package_members != expected_package or len(package_members) != len(set(package_members)):
        raise VerificationError("manifest package_members is not the exact sorted allowlist")

    return {
        "project": project,
        "project_id": project_id,
        "project_version": project["version"],
        "bundle_name": f"{project_id}-v{project['version']}",
        "preset": preset,
        "style_summary": style_value,
        "quality_policy": quality,
        "renderer": renderer,
        "png_sizes": png_sizes,
        "ico_sizes": ico_sizes,
        "routing": routing,
        "provenance_summary": provenance,
        "visual_summary": visual,
        "evidence_summary": evidence_summary,
        "files": files,
        "package_members": package_members,
        "expected_files": expected_files,
    }


def _record_common(member: str, record: Any, data: bytes) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise VerificationError(f"manifest file record must be an object: {member}")
    if not _COMMON_RECORD.issubset(record):
        raise VerificationError(f"manifest file record lacks common fields: {member}")
    if isinstance(record["bytes"], bool) or not isinstance(record["bytes"], int) or record["bytes"] != len(data):
        raise VerificationError(f"manifest byte count mismatch: {member}")
    if not isinstance(record["sha256"], str) or not _SHA_RE.fullmatch(record["sha256"]) or record["sha256"] != _sha256(data):
        raise VerificationError(f"manifest SHA-256 mismatch: {member}")
    if not isinstance(record["role"], str) or not isinstance(record["media_type"], str):
        raise VerificationError(f"manifest role/media type is invalid: {member}")
    return record


def _write_temp_members(member_bytes: dict[str, bytes]) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(prefix="iconforge-verify-")
    root = Path(temporary.name)
    for member, data in member_bytes.items():
        path = root.joinpath(*member.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)
    return temporary, root


def _validate_packaged_config(data: bytes, contract: dict[str, Any]) -> dict[str, Any]:
    try:
        value = loads_strict(data, label="source/iconforge.json")
    except JsonSecurityError as exc:
        raise VerificationError(str(exc)) from exc
    keys = {
        "schema_version", "project", "sources", "style_lock", "provenance",
        "visual_review", "preset", "exports", "preview", "renderer",
    }
    root = _exact(value, keys, "source/iconforge.json")
    if data != canonical_json_bytes(root):
        raise VerificationError("source/iconforge.json is not canonical JSON")
    if root["schema_version"] != 2:
        raise VerificationError("packaged project config schema is unsupported")
    if _exact(root["project"], {"id", "title", "version"}, "packaged config project") != contract["project"]:
        raise VerificationError("packaged project config identity differs from manifest")
    preset = root["preset"]
    expected_preset = None if contract["preset"] is None else {
        "id": contract["preset"].id, "version": contract["preset"].version
    }
    if preset != expected_preset:
        raise VerificationError("packaged project config preset differs from manifest")
    exports = _exact(root["exports"], {"png_sizes", "ico_sizes", "small_sizes", "large_sizes"}, "packaged config exports")
    if tuple(exports["png_sizes"]) != contract["png_sizes"] or tuple(exports["ico_sizes"]) != contract["ico_sizes"]:
        raise VerificationError("packaged project config export sizes differ from manifest")
    small = set(exports["small_sizes"] if isinstance(exports["small_sizes"], list) else [])
    large = set(exports["large_sizes"] if isinstance(exports["large_sizes"], list) else [])
    for size in contract["png_sizes"]:
        expected = "small" if size in small else "large" if size in large else None
        if expected != contract["routing"]["png"][str(size)]:
            raise VerificationError("packaged project config routing differs from manifest")
    renderer = _exact(root["renderer"], {"lock_id"}, "packaged config renderer")
    if renderer["lock_id"] != contract["renderer"]["lock_id"]:
        raise VerificationError("packaged project config renderer lock differs from manifest")
    if (root["style_lock"] is None) != (contract["style_summary"] is None):
        raise VerificationError("packaged project config style-lock mode differs from manifest")
    return root


def _verify_package_bytes(manifest: dict[str, Any], contract: dict[str, Any], member_bytes: dict[str, bytes]) -> None:
    expected_members = set(contract["package_members"])
    if set(member_bytes) != expected_members:
        raise VerificationError("package bytes do not exactly match manifest package_members")
    manifest_bytes = member_bytes["manifest.json"]
    if _parse_manifest(manifest_bytes) != manifest:
        raise VerificationError("manifest changed during package verification")

    files = contract["files"]
    for member, record in files.items():
        _record_common(member, record, member_bytes[member])

    temporary, root = _write_temp_members(member_bytes)
    try:
        config_data = member_bytes["source/iconforge.json"]
        packaged_config = _validate_packaged_config(config_data, contract)
        config_record = files["source/iconforge.json"]
        if (
            set(config_record) != _COMMON_RECORD | {"schema_version"}
            or config_record["role"] != "project-config"
            or config_record["media_type"] != "application/json"
            or config_record["schema_version"] != 2
        ):
            raise VerificationError("project config file record is invalid")

        large = sanitize_svg_bytes(member_bytes["source/icon-large.svg"])
        small = sanitize_svg_bytes(member_bytes["source/icon-small.svg"])
        if large.data != member_bytes["source/icon-large.svg"] or small.data != member_bytes["source/icon-small.svg"]:
            raise VerificationError("packaged source SVG is not canonical sanitizer output")
        if large.geometry_sha256 == small.geometry_sha256:
            raise VerificationError("packaged small SVG is geometrically identical to large SVG")

        large_record = _record_common("source/icon-large.svg", files["source/icon-large.svg"], large.data)
        small_record = _record_common("source/icon-small.svg", files["source/icon-small.svg"], small.data)
        expected_source_keys = _COMMON_RECORD | {"view_box", "geometry_sha256", "element_count", "attribute_count"}
        for role, svg, record in (("large", large, large_record), ("small", small, small_record)):
            if set(record) != expected_source_keys or record["role"] != f"source-svg-{role}" or record["media_type"] != "image/svg+xml":
                raise VerificationError(f"{role} SVG record schema is invalid")
            if record["view_box"] != list(svg.viewbox) or record["geometry_sha256"] != svg.geometry_sha256:
                raise VerificationError(f"{role} SVG metadata mismatch")
            if record["element_count"] != svg.element_count or record["attribute_count"] != svg.attribute_count:
                raise VerificationError(f"{role} SVG structural counts mismatch")

        style_lock = None
        if contract["style_summary"] is not None:
            style_lock = load_style_lock(root / "source/style-lock.json", expected_preset=contract["preset"])
            validate_svg_pair_against_style_lock(style_lock, large.data, small.data)
            summary = contract["style_summary"]
            if (
                summary["style_id"] != style_lock.style_id
                or summary["style_version"] != style_lock.style_version
                or summary["sha256"] != style_lock.sha256
            ):
                raise VerificationError("manifest style lock summary does not match packaged style lock")
            record = files["source/style-lock.json"]
            if set(record) != _COMMON_RECORD | {"style_id", "style_version", "preset_id", "preset_version"}:
                raise VerificationError("style lock file record schema is invalid")
            if record["role"] != "style-lock" or record["media_type"] != "application/json":
                raise VerificationError("style lock file record role is invalid")
            if (
                record["style_id"], record["style_version"], record["preset_id"], record["preset_version"]
            ) != (style_lock.style_id, style_lock.style_version, style_lock.preset_id, style_lock.preset_version):
                raise VerificationError("style lock file record metadata mismatch")

        effective_policy = effective_quality_policy(style_lock)
        expected_quality = {
            "id": effective_policy.policy_id,
            "safe_margin_px": effective_policy.safe_margin_px,
            "optical_center_tolerance_px": effective_policy.optical_center_tolerance_px,
            "visual_weight_minimum": effective_policy.visual_weight_minimum,
            "visual_weight_maximum": effective_policy.visual_weight_maximum,
            "transparent_corners": effective_policy.transparent_corners,
            "full_bleed_allowed": effective_policy.full_bleed_allowed,
        }
        if contract["quality_policy"] != expected_quality:
            raise VerificationError("manifest effective quality policy does not match the packaged style mode")

        provenance = load_provenance(root / "provenance.json")
        if provenance.sha256 != contract["provenance_summary"]["sha256"] or provenance.entry_count != contract["provenance_summary"]["entry_count"]:
            raise VerificationError("manifest provenance summary mismatch")
        provenance_record = files["provenance.json"]
        if set(provenance_record) != _COMMON_RECORD | {"entry_count"} or provenance_record["entry_count"] != provenance.entry_count:
            raise VerificationError("provenance file record mismatch")

        visual = load_visual_review(root / "review/visual-review.json")
        summary = contract["visual_summary"]
        if (
            visual.sha256 != summary["sha256"] or visual.status != summary["status"]
            or visual.final_total != summary["total"] or visual.selected_concept != summary["selected_concept"]
            or visual.review_source_sha256 != summary["review_source_sha256"]
            or visual.review_input_sha256 != summary["review_input_sha256"]
            or visual.review_output_sha256 != summary["review_output_sha256"]
        ):
            raise VerificationError("manifest visual review summary mismatch")
        visual_record = files["review/visual-review.json"]
        if set(visual_record) != _COMMON_RECORD | {"status", "total", "selected_concept"}:
            raise VerificationError("visual review record schema is invalid")
        if (
            visual_record["status"], visual_record["total"], visual_record["selected_concept"]
        ) != (visual.status, visual.final_total, visual.selected_concept):
            raise VerificationError("visual review record metadata mismatch")

        evidence = load_review_evidence_bytes(member_bytes["review/review-evidence.json"])
        evidence_summary = contract["evidence_summary"]
        if (
            evidence.sha256 != evidence_summary["sha256"]
            or evidence.review_source_sha256 != evidence_summary["review_source_sha256"]
            or evidence.review_input_sha256 != evidence_summary["review_input_sha256"]
            or evidence.review_output_sha256 != evidence_summary["review_output_sha256"]
        ):
            raise VerificationError("manifest review evidence summary mismatch")
        evidence_record = files["review/review-evidence.json"]
        evidence_keys = _COMMON_RECORD | {
            "review_source_sha256", "review_input_sha256", "review_output_sha256"
        }
        if (
            set(evidence_record) != evidence_keys
            or evidence_record["role"] != "review-evidence"
            or evidence_record["media_type"] != "application/json"
        ):
            raise VerificationError("review evidence file record is invalid")
        if any(
            evidence_record[key] != evidence_summary[key]
            for key in ("review_source_sha256", "review_input_sha256", "review_output_sha256")
        ):
            raise VerificationError("review evidence file record metadata mismatch")
        expected_style_hash = None if style_lock is None else style_lock.sha256
        if evidence.data["source"] != {
            "iconforge_sha256": _sha256(config_data),
            "large_svg_sha256": large.sha256,
            "small_svg_sha256": small.sha256,
            "style_lock_sha256": expected_style_hash,
        }:
            raise VerificationError("review evidence source hashes do not match packaged inputs")
        expected_renderer = {
            "name": contract["renderer"]["name"],
            "version_output": contract["renderer"]["version_output"],
            "lock_id": contract["renderer"]["lock_id"],
            "executable_sha256": contract["renderer"]["executable_sha256"],
        }
        if evidence.data["renderer"] != expected_renderer:
            raise VerificationError("review evidence renderer identity differs from manifest")
        expected_environment = {
            "platform": contract["renderer"]["platform"],
            "machine": contract["renderer"]["machine"],
            "python_version": contract["renderer"]["python_version"],
        }
        if evidence.data["environment"] != expected_environment:
            raise VerificationError("review evidence environment differs from manifest")
        if (
            visual.review_source_sha256 != evidence.review_source_sha256
            or visual.review_input_sha256 != evidence.review_input_sha256
            or visual.review_output_sha256 != evidence.review_output_sha256
        ):
            raise VerificationError("final visual review is not bound to packaged review evidence")

        require_corners = effective_policy.transparent_corners
        full_bleed = effective_policy.full_bleed_allowed
        pngs: dict[int, bytes] = {}
        png_infos: dict[int, Any] = {}
        margins: dict[int, int] = {}
        for size in contract["png_sizes"]:
            member = f"exports/png/{contract['project_id']}-{size}.png"
            data = member_bytes[member]
            record = files[member]
            expected_keys = _COMMON_RECORD | {
                "width", "height", "source_tier", "source_svg_sha256", "alpha_bbox", "safe_margin",
                "visual_weight", "optical_center",
            }
            if set(record) != expected_keys or record["role"] != "png-export" or record["media_type"] != "image/png":
                raise VerificationError(f"PNG record schema is invalid: {member}")
            tier = contract["routing"]["png"][str(size)]
            if record["width"] != size or record["height"] != size or record["source_tier"] != tier:
                raise VerificationError(f"PNG dimensions or routing mismatch: {member}")
            expected_source_hash = small.sha256 if tier == "small" else large.sha256
            if record["source_svg_sha256"] != expected_source_hash:
                raise VerificationError(f"PNG source SVG hash mismatch: {member}")
            margin = 0 if full_bleed else scaled_canvas_pixels(effective_policy.safe_margin_px, size)
            info = inspect_png(
                data,
                expected_width=size,
                expected_height=size,
                require_transparency=not full_bleed,
                require_transparent_corners=require_corners,
                minimum_safe_margin=margin,
            )
            validate_rendered_metrics(style_lock, info, size)
            if data != encode_rgba_png(info.width, info.height, info.rgba):
                raise VerificationError(f"PNG is not canonical RGBA encoding: {member}")
            if record["alpha_bbox"] != list(info.alpha_bbox) or record["safe_margin"] != list(info.safe_margin):
                raise VerificationError(f"PNG alpha metrics mismatch: {member}")
            if record["visual_weight"] != round(info.visual_weight, 8):
                raise VerificationError(f"PNG visual weight mismatch: {member}")
            if record["optical_center"] != [round(info.optical_center[0], 8), round(info.optical_center[1], 8)]:
                raise VerificationError(f"PNG optical center mismatch: {member}")
            pngs[size] = data
            png_infos[size] = info
            margins[size] = margin

        ico_member = f"exports/windows/{contract['project_id']}.ico"
        ico_record = files[ico_member]
        if set(ico_record) != _COMMON_RECORD | {"frames"} or ico_record["role"] != "windows-ico":
            raise VerificationError("ICO record schema is invalid")
        try:
            ico_info = inspect_ico(member_bytes[ico_member])
        except IcoError as exc:
            raise VerificationError(f"ICO validation failed: {exc}") from exc
        if ico_info.sizes != contract["ico_sizes"]:
            raise VerificationError("ICO frame sizes do not match manifest")
        expected_frames = []
        for size in contract["ico_sizes"]:
            if ico_info.frames[size].payload != pngs[size]:
                raise VerificationError(f"ICO {size}px payload differs from exact PNG export")
            tier = contract["routing"]["ico"][str(size)]
            if tier != contract["routing"]["png"][str(size)]:
                raise VerificationError(f"ICO/PNG source routing differs at {size}px")
            expected_frames.append({"size": size, "sha256": _sha256(pngs[size]), "source_tier": tier})
        if ico_record["frames"] != expected_frames:
            raise VerificationError("ICO frame manifest metadata mismatch")

        review_svg_member = f"review/{contract['project_id']}-review.svg"
        review_png_member = f"review/{contract['project_id']}-review.png"
        routing_int = {size: contract["routing"]["png"][str(size)] for size in contract["png_sizes"]}
        expected_sheet = build_review_svg(
            contract["project_id"],
            pngs,
            routing_int,
            safe_margin_by_size=margins,
            prevalidated_infos=png_infos,
        )
        review_svg_record = files[review_svg_member]
        if set(review_svg_record) != _COMMON_RECORD | {"width", "height", "embedded_sizes"}:
            raise VerificationError("review SVG record schema is invalid")
        if member_bytes[review_svg_member] != expected_sheet.data:
            raise VerificationError("review SVG is stale or not generated from packaged PNGs")
        if (
            review_svg_record["width"] != expected_sheet.width
            or review_svg_record["height"] != expected_sheet.height
            or review_svg_record["embedded_sizes"] != list(expected_sheet.embedded_sizes)
        ):
            raise VerificationError("review SVG metadata mismatch")
        review_png_record = files[review_png_member]
        if set(review_png_record) != _COMMON_RECORD | {"width", "height"}:
            raise VerificationError("review PNG record schema is invalid")
        try:
            review_info = inspect_png(
                member_bytes[review_png_member],
                expected_width=expected_sheet.width,
                expected_height=expected_sheet.height,
                require_transparency=False,
                analyze_metrics=False,
            )
        except PngError as exc:
            raise VerificationError(f"review PNG validation failed: {exc}") from exc
        if member_bytes[review_png_member] != encode_rgba_png(review_info.width, review_info.height, review_info.rgba):
            raise VerificationError("review PNG is not canonical RGBA encoding")
        if review_png_record["width"] != expected_sheet.width or review_png_record["height"] != expected_sheet.height:
            raise VerificationError("review PNG metadata mismatch")

        reviewed_assets = evidence.data["reviewed_assets"]
        expected_evidence_pngs = [
            {"size": size, "sha256": _sha256(pngs[size])}
            for size in contract["png_sizes"]
        ]
        if reviewed_assets["png"] != expected_evidence_pngs:
            raise VerificationError("review evidence PNG hashes do not match packaged export pixels")
        if reviewed_assets["review_svg_sha256"] != _sha256(member_bytes[review_svg_member]):
            raise VerificationError("review evidence SVG hash does not match the packaged review sheet")
        if reviewed_assets["review_png_sha256"] != _sha256(member_bytes[review_png_member]):
            raise VerificationError("review evidence PNG hash does not match the packaged review sheet")

        checksums = member_bytes["SHA256SUMS"]
        try:
            checksum_text = checksums.decode("ascii")
        except UnicodeDecodeError as exc:
            raise VerificationError("SHA256SUMS must be ASCII") from exc
        checksum_names = tuple(sorted((*contract["expected_files"], "manifest.json")))
        expected_checksums = "".join(f"{_sha256(member_bytes[name])}  {name}\n" for name in checksum_names).encode("ascii")
        if checksums != expected_checksums or not checksum_text.endswith("\n"):
            raise VerificationError("SHA256SUMS is stale, malformed, or non-canonical")
    except (SvgSecurityError, JsonSecurityError, StyleLockError, VisualReviewError) as exc:
        raise VerificationError(str(exc)) from exc
    finally:
        temporary.cleanup()


def _read_package_zip(path: Path | bytes) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    with open_safe_zip(path, canonical=True) as (archive, inventory):
        if "manifest.json" not in inventory.infos:
            raise VerificationError("ZIP has no manifest.json")
        manifest_bytes = read_zip_member(archive, inventory.infos["manifest.json"], maximum=_MAX_MANIFEST_BYTES)
        manifest = _parse_manifest(manifest_bytes)
        contract = _manifest_contract(manifest)
        if inventory.names != contract["package_members"]:
            raise VerificationError("ZIP exact member list differs from manifest allowlist")
        member_bytes = {"manifest.json": manifest_bytes}
        for name in inventory.names:
            if name == "manifest.json":
                continue
            member_bytes[name] = read_zip_member(archive, inventory.infos[name])
    return manifest, contract, member_bytes


def verify_package_zip(path: Path) -> VerificationReport:
    path = Path(path)
    manifest, contract, member_bytes = _read_package_zip(path)
    _verify_package_bytes(manifest, contract, member_bytes)
    return VerificationReport(
        path.resolve(strict=True),
        contract["project_id"],
        contract["project_version"],
        len(member_bytes),
        _sha256(_read_regular(path, maximum=128 * 1024 * 1024)),
        True,
    )


def verify_output(output: Path) -> VerificationReport:
    output = Path(output)
    try:
        mode = output.lstat().st_mode
    except OSError as exc:
        raise VerificationError(f"verification target is unavailable: {output}") from exc
    if stat.S_ISREG(mode) and not stat.S_ISLNK(mode):
        return verify_package_zip(output)
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise VerificationError("verification target must be a package directory or regular ZIP file")
    output = output.resolve(strict=True)
    actual_files, actual_directories = _collect_tree(output)
    if "manifest.json" not in actual_files:
        raise VerificationError("output has no manifest.json")
    manifest_bytes = _read_regular(output / "manifest.json", maximum=_MAX_MANIFEST_BYTES)
    manifest = _parse_manifest(manifest_bytes)
    contract = _manifest_contract(manifest)
    archive_name = f"{contract['bundle_name']}.zip"
    sidecar_name = f"{archive_name}.sha256"
    expected_actual = set(contract["package_members"]) | {archive_name, sidecar_name}
    if actual_files != expected_actual:
        raise VerificationError(
            f"output exact file set mismatch; missing={sorted(expected_actual-actual_files)}, extra={sorted(actual_files-expected_actual)}"
        )
    expected_dirs: set[str] = set()
    for member in expected_actual:
        parent = Path(member).parent
        while parent.as_posix() != ".":
            expected_dirs.add(parent.as_posix())
            parent = parent.parent
    if actual_directories != expected_dirs:
        raise VerificationError("output contains missing or unexpected directories")

    _preflight_directory_members(output, contract, manifest_size=len(manifest_bytes))
    member_bytes = {name: _read_regular(output / name) for name in contract["package_members"]}
    _verify_package_bytes(manifest, contract, member_bytes)

    archive_path = output / archive_name
    archive_bytes = _read_regular(archive_path, maximum=128 * 1024 * 1024)
    sidecar = _read_regular(output / sidecar_name, maximum=1024)
    expected_sidecar = f"{_sha256(archive_bytes)}  {archive_name}\n".encode("ascii")
    if sidecar != expected_sidecar:
        raise VerificationError("outer ZIP SHA-256 sidecar mismatch")
    zip_manifest, zip_contract, zip_members = _read_package_zip(archive_bytes)
    if zip_manifest != manifest or zip_contract["package_members"] != contract["package_members"]:
        raise VerificationError("embedded ZIP manifest differs from output manifest")
    if zip_members != member_bytes:
        raise VerificationError("embedded ZIP payload is stale or differs from output files")
    # Exact byte equality with the already verified directory payload proves the
    # embedded package has the same semantics; a second full PNG/SVG pass would
    # only repeat expensive work without adding evidence.

    return VerificationReport(
        output,
        contract["project_id"],
        contract["project_version"],
        len(actual_files),
        _sha256(archive_bytes),
        False,
    )
