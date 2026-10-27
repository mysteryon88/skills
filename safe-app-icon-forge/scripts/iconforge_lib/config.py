from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError, JsonSecurityError, PathSafetyError
from .json_safe import canonical_json_bytes, load_json_file
from .paths import assert_no_case_collisions, confined_path

SKILL_VERSION = "3"
DEFAULT_PNG_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024)
DEFAULT_ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
DEFAULT_SMALL_SIZES = (16, 20, 24, 32)
DEFAULT_LARGE_SIZES = (40, 48, 64, 128, 256, 512, 1024)
DEFAULT_ACTUAL_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_LOCK_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

_TOP_KEYS = {
    "schema_version", "project", "sources", "style_lock", "provenance",
    "visual_review", "preset", "exports", "preview", "renderer",
}
_PROJECT_KEYS = {"id", "title", "version"}
_SOURCE_KEYS = {"large_svg", "small_svg"}
_PRESET_KEYS = {"id", "version"}
_EXPORT_KEYS = {"png_sizes", "ico_sizes", "small_sizes", "large_sizes"}
_PREVIEW_KEYS = {
    "enabled", "actual_sizes", "backgrounds", "taskbar",
    "safe_margin_overlay", "optical_center_overlay",
}
_RENDERER_KEYS = {"lock_id"}


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    id: str
    title: str
    version: str


@dataclass(frozen=True, slots=True)
class PresetRef:
    id: str
    version: str


@dataclass(frozen=True, slots=True)
class PreviewConfig:
    enabled: bool
    actual_sizes: tuple[int, ...]
    backgrounds: tuple[str, ...]
    taskbar: bool
    safe_margin_overlay: bool
    optical_center_overlay: bool


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    project_dir: Path
    config_path: Path
    project: ProjectIdentity
    large_svg: Path
    small_svg: Path
    style_lock_path: Path | None
    provenance_path: Path
    visual_review_path: Path
    preset: PresetRef | None
    png_sizes: tuple[int, ...]
    ico_sizes: tuple[int, ...]
    small_sizes: tuple[int, ...]
    large_sizes: tuple[int, ...]
    preview: PreviewConfig
    renderer_lock_id: str
    canonical: bytes
    sha256: str

    @property
    def bundle_name(self) -> str:
        return f"{self.project.id}-v{self.project.version}"

    def source_tier(self, size: int) -> str:
        if size in self.small_sizes:
            return "small"
        if size in self.large_sizes:
            return "large"
        raise ConfigError(f"size {size} has no optical source tier")


def _exact_object(value: Any, keys: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ConfigError(f"{label} must be a JSON object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise ConfigError(f"{label} key mismatch; missing={missing}, unknown={unknown}")
    return value


def _semver(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SEMVER_RE.fullmatch(value):
        raise ConfigError(f"{label} must be a valid SemVer string")
    return value


def _identifier(value: Any, *, label: str, lock: bool = False) -> str:
    pattern = _LOCK_ID_RE if lock else _ID_RE
    if not isinstance(value, str) or not pattern.fullmatch(value) or "--" in value:
        raise ConfigError(f"{label} has an invalid identifier")
    return value


def _strict_bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be a JSON boolean")
    return value


def _sizes(value: Any, *, label: str, maximum: int) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{label} must be a non-empty array")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ConfigError(f"{label} must contain integers only")
    if any(item < 1 or item > maximum for item in value):
        raise ConfigError(f"{label} entries must be between 1 and {maximum}")
    if value != sorted(value) or len(value) != len(set(value)):
        raise ConfigError(f"{label} must be strictly increasing with no duplicates")
    return tuple(value)


def _resolve_file(project_dir: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str):
        raise ConfigError(f"{label} must be a project-relative path string")
    try:
        return confined_path(project_dir, value, must_exist=True, require_file=True)
    except PathSafetyError as exc:
        raise ConfigError(f"{label}: {exc}") from exc


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        left_stat = left.stat()
        right_stat = right.stat()
        return (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino)


def load_project(project_dir: Path) -> ProjectConfig:
    project_dir = Path(project_dir)
    try:
        mode = project_dir.lstat().st_mode
    except OSError as exc:
        raise ConfigError(f"project directory is unavailable: {project_dir}") from exc
    if project_dir.is_symlink() or not project_dir.is_dir():
        raise ConfigError("project directory must be a regular non-symlink directory")
    project_dir = project_dir.resolve(strict=True)
    try:
        config_path = confined_path(project_dir, "iconforge.json", must_exist=True, require_file=True)
        data, raw = load_json_file(config_path, maximum=256 * 1024, label="iconforge.json")
    except (PathSafetyError, JsonSecurityError) as exc:
        raise ConfigError(str(exc)) from exc

    root = _exact_object(data, _TOP_KEYS, label="iconforge.json")
    canonical = canonical_json_bytes(root)
    if raw != canonical:
        raise ConfigError("iconforge.json must use canonical JSON formatting")
    if root["schema_version"] != 2 or isinstance(root["schema_version"], bool):
        raise ConfigError("schema_version must be exactly 2")

    project_data = _exact_object(root["project"], _PROJECT_KEYS, label="project")
    project_id = _identifier(project_data["id"], label="project.id")
    title = project_data["title"]
    if not isinstance(title, str) or not title.strip() or len(title) > 160 or any(ord(c) < 32 for c in title):
        raise ConfigError("project.title must be 1-160 printable characters")
    project_version = _semver(project_data["version"], label="project.version")
    project = ProjectIdentity(project_id, title.strip(), project_version)

    source_data = _exact_object(root["sources"], _SOURCE_KEYS, label="sources")
    large_svg = _resolve_file(project_dir, source_data["large_svg"], label="sources.large_svg")
    small_svg = _resolve_file(project_dir, source_data["small_svg"], label="sources.small_svg")
    if _same_file(large_svg, small_svg):
        raise ConfigError("large_svg and small_svg must be different regular files")

    style_value = root["style_lock"]
    style_lock_path = None if style_value is None else _resolve_file(project_dir, style_value, label="style_lock")
    provenance_path = _resolve_file(project_dir, root["provenance"], label="provenance")
    visual_review_path = _resolve_file(project_dir, root["visual_review"], label="visual_review")

    preset_value = root["preset"]
    if preset_value is None:
        preset = None
    else:
        preset_data = _exact_object(preset_value, _PRESET_KEYS, label="preset")
        preset = PresetRef(
            _identifier(preset_data["id"], label="preset.id"),
            _semver(preset_data["version"], label="preset.version"),
        )
        if style_lock_path is None:
            raise ConfigError("a preset requires a style_lock")

    exports = _exact_object(root["exports"], _EXPORT_KEYS, label="exports")
    png_sizes = _sizes(exports["png_sizes"], label="exports.png_sizes", maximum=1024)
    ico_sizes = _sizes(exports["ico_sizes"], label="exports.ico_sizes", maximum=256)
    small_sizes = _sizes(exports["small_sizes"], label="exports.small_sizes", maximum=1024)
    large_sizes = _sizes(exports["large_sizes"], label="exports.large_sizes", maximum=1024)

    if not set(DEFAULT_PNG_SIZES).issubset(png_sizes):
        raise ConfigError(f"png_sizes must include required sizes {list(DEFAULT_PNG_SIZES)}")
    if not set(DEFAULT_ICO_SIZES).issubset(ico_sizes):
        raise ConfigError(f"ico_sizes must include required sizes {list(DEFAULT_ICO_SIZES)}")
    if not set(ico_sizes).issubset(png_sizes):
        raise ConfigError("ico_sizes must be a subset of png_sizes")
    if set(small_sizes) & set(large_sizes):
        raise ConfigError("small_sizes and large_sizes must not overlap")
    if set(small_sizes) | set(large_sizes) != set(png_sizes):
        raise ConfigError("small_sizes and large_sizes must exactly cover png_sizes")
    if not small_sizes or not large_sizes:
        raise ConfigError("both optical source tiers must be used")
    if not set(ico_sizes) & set(small_sizes) or not set(ico_sizes) & set(large_sizes):
        raise ConfigError("ICO must contain at least one small-tier and one large-tier frame")
    for required in DEFAULT_SMALL_SIZES:
        if required in png_sizes and required not in small_sizes:
            raise ConfigError(f"{required}px must use the small SVG tier")
    for size in png_sizes:
        if size >= 48 and size not in large_sizes:
            raise ConfigError(f"{size}px must use the large SVG tier")

    preview_data = _exact_object(root["preview"], _PREVIEW_KEYS, label="preview")
    actual_sizes = _sizes(preview_data["actual_sizes"], label="preview.actual_sizes", maximum=1024)
    if tuple(actual_sizes) != DEFAULT_ACTUAL_SIZES:
        raise ConfigError(f"preview.actual_sizes must be exactly {list(DEFAULT_ACTUAL_SIZES)}")
    if not set(actual_sizes).issubset(png_sizes):
        raise ConfigError("preview.actual_sizes must be a subset of png_sizes")
    backgrounds = preview_data["backgrounds"]
    if backgrounds != ["light", "dark", "neutral"]:
        raise ConfigError("preview.backgrounds must be exactly ['light', 'dark', 'neutral']")
    preview = PreviewConfig(
        enabled=_strict_bool(preview_data["enabled"], label="preview.enabled"),
        actual_sizes=actual_sizes,
        backgrounds=tuple(backgrounds),
        taskbar=_strict_bool(preview_data["taskbar"], label="preview.taskbar"),
        safe_margin_overlay=_strict_bool(preview_data["safe_margin_overlay"], label="preview.safe_margin_overlay"),
        optical_center_overlay=_strict_bool(preview_data["optical_center_overlay"], label="preview.optical_center_overlay"),
    )
    if not preview.enabled or not preview.taskbar:
        raise ConfigError("preview and taskbar review are mandatory for release builds")
    if not preview.safe_margin_overlay or not preview.optical_center_overlay:
        raise ConfigError("safe-margin and optical-center overlays are mandatory for release builds")

    renderer_data = _exact_object(root["renderer"], _RENDERER_KEYS, label="renderer")
    renderer_lock_id = _identifier(renderer_data["lock_id"], label="renderer.lock_id", lock=True)

    configured_paths = [
        source_data["large_svg"], source_data["small_svg"], root["provenance"], root["visual_review"]
    ]
    if style_value is not None:
        configured_paths.append(style_value)
    try:
        assert_no_case_collisions(configured_paths, label="configured project paths")
    except PathSafetyError as exc:
        raise ConfigError(str(exc)) from exc

    return ProjectConfig(
        project_dir=project_dir,
        config_path=config_path,
        project=project,
        large_svg=large_svg,
        small_svg=small_svg,
        style_lock_path=style_lock_path,
        provenance_path=provenance_path,
        visual_review_path=visual_review_path,
        preset=preset,
        png_sizes=png_sizes,
        ico_sizes=ico_sizes,
        small_sizes=small_sizes,
        large_sizes=large_sizes,
        preview=preview,
        renderer_lock_id=renderer_lock_id,
        canonical=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def is_semver(value: str) -> bool:
    return bool(_SEMVER_RE.fullmatch(value))
