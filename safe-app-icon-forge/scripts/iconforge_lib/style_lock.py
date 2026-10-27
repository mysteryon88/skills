from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import PresetRef, is_semver
from .errors import JsonSecurityError, StyleLockError
from .json_safe import canonical_json_bytes, load_json_file

_HEX_RE = re.compile(r"^#[0-9A-F]{6}$")
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_TOP = {
    "schema_version", "style_id", "style_version", "preset_id", "preset_version",
    "canvas", "palette", "outline", "geometry", "lighting", "form_character",
    "visual_weight", "small_size", "transparency",
}
_CANVAS = {"view_box", "safe_margin_px", "optical_center_tolerance_px"}
_PALETTE = {"roles"}
_OUTLINE = {"large_width", "small_width", "linecap", "linejoin"}
_GEOMETRY = {"radii", "proportions", "eyes", "bounds", "metaphor_zone", "forbidden_zones"}
_LIGHTING = {"direction", "softness"}
_VISUAL_WEIGHT = {"target", "minimum", "maximum"}
_SMALL = {"simplifications", "minimum_element_px", "minimum_gap_px"}
_TRANSPARENCY = {"transparent_corners", "full_bleed_allowed"}

DEFAULT_QUALITY_POLICY_ID = "iconforge-default-v1"
DEFAULT_SAFE_MARGIN_PX = 32
DEFAULT_OPTICAL_CENTER_TOLERANCE_PX = 96
DEFAULT_VISUAL_WEIGHT_MINIMUM = 0.18
DEFAULT_VISUAL_WEIGHT_MAXIMUM = 0.86


@dataclass(frozen=True, slots=True)
class EffectiveQualityPolicy:
    policy_id: str
    safe_margin_px: int
    optical_center_tolerance_px: int
    visual_weight_minimum: float
    visual_weight_maximum: float
    transparent_corners: bool
    full_bleed_allowed: bool


def effective_quality_policy(lock: "StyleLock | None") -> EffectiveQualityPolicy:
    if lock is None:
        return EffectiveQualityPolicy(
            DEFAULT_QUALITY_POLICY_ID,
            DEFAULT_SAFE_MARGIN_PX,
            DEFAULT_OPTICAL_CENTER_TOLERANCE_PX,
            DEFAULT_VISUAL_WEIGHT_MINIMUM,
            DEFAULT_VISUAL_WEIGHT_MAXIMUM,
            True,
            False,
        )
    visual = lock.data["visual_weight"]
    return EffectiveQualityPolicy(
        f"style-lock:{lock.style_id}@{lock.style_version}",
        lock.safe_margin_px,
        lock.optical_center_tolerance_px,
        float(visual["minimum"]),
        float(visual["maximum"]),
        lock.transparent_corners,
        lock.full_bleed_allowed,
    )


@dataclass(frozen=True, slots=True)
class StyleLock:
    path: Path
    data: dict[str, Any]
    canonical: bytes
    sha256: str
    style_id: str
    style_version: str
    preset_id: str | None
    preset_version: str | None
    safe_margin_px: int
    optical_center_tolerance_px: int
    transparent_corners: bool
    full_bleed_allowed: bool


def scaled_canvas_pixels(value: int, size: int) -> int:
    return math.ceil(value * size / 1024)


def validate_rendered_metrics(lock: StyleLock | None, info: Any, size: int) -> None:
    policy = effective_quality_policy(lock)
    if not policy.visual_weight_minimum <= info.visual_weight <= policy.visual_weight_maximum:
        raise StyleLockError(
            f"{size}px visual weight {info.visual_weight:.6f} is outside "
            f"[{policy.visual_weight_minimum}, {policy.visual_weight_maximum}] "
            f"for {policy.policy_id}"
        )
    center = (size - 1) / 2
    delta = math.hypot(info.optical_center[0] - center, info.optical_center[1] - center)
    tolerance = policy.optical_center_tolerance_px * size / 1024
    if delta > tolerance:
        raise StyleLockError(
            f"{size}px optical center delta {delta:.6f}px exceeds {tolerance:.6f}px "
            f"for {policy.policy_id}"
        )


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StyleLockError(f"{label} must be a JSON object")
    missing = sorted(keys - set(value))
    unknown = sorted(set(value) - keys)
    if missing or unknown:
        raise StyleLockError(f"{label} key mismatch; missing={missing}, unknown={unknown}")
    return value


def _number(value: Any, label: str, *, minimum: float = -1e9, maximum: float = 1e9) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StyleLockError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise StyleLockError(f"{label} is outside the supported finite range")
    return number


def _numeric_tree(value: Any, label: str, *, depth: int = 0) -> None:
    if depth > 8:
        raise StyleLockError(f"{label} is too deeply nested")
    if isinstance(value, dict):
        if not value or not all(isinstance(k, str) and k for k in value):
            raise StyleLockError(f"{label} must use non-empty string keys")
        for key, child in value.items():
            _numeric_tree(child, f"{label}.{key}", depth=depth + 1)
    elif isinstance(value, list):
        if not value or len(value) > 64:
            raise StyleLockError(f"{label} must be a non-empty bounded array")
        for index, child in enumerate(value):
            _numeric_tree(child, f"{label}[{index}]", depth=depth + 1)
    else:
        _number(value, label, minimum=-8192, maximum=8192)


def load_style_lock(path: Path, *, expected_preset: PresetRef | None) -> StyleLock:
    try:
        data, raw = load_json_file(path, maximum=512 * 1024, label="style-lock.json")
    except JsonSecurityError as exc:
        raise StyleLockError(str(exc)) from exc
    root = _exact(data, _TOP, "style-lock.json")
    if root["schema_version"] != 1 or isinstance(root["schema_version"], bool):
        raise StyleLockError("style-lock schema_version must be exactly 1")
    style_id = root["style_id"]
    if not isinstance(style_id, str) or not _ID_RE.fullmatch(style_id):
        raise StyleLockError("style_id is invalid")
    style_version = root["style_version"]
    if not isinstance(style_version, str) or not is_semver(style_version):
        raise StyleLockError("style_version must be SemVer")

    preset_id = root["preset_id"]
    preset_version = root["preset_version"]
    if (preset_id is None) != (preset_version is None):
        raise StyleLockError("preset_id and preset_version must both be null or both be set")
    if preset_id is not None:
        if not isinstance(preset_id, str) or not _ID_RE.fullmatch(preset_id):
            raise StyleLockError("preset_id is invalid")
        if not isinstance(preset_version, str) or not is_semver(preset_version):
            raise StyleLockError("preset_version must be SemVer")
    if expected_preset is None:
        if preset_id is not None:
            raise StyleLockError("style lock declares a preset but project preset is null")
    elif (preset_id, preset_version) != (expected_preset.id, expected_preset.version):
        raise StyleLockError("style lock preset identity does not match iconforge.json")

    canvas = _exact(root["canvas"], _CANVAS, "canvas")
    view_box = canvas["view_box"]
    if view_box != [0, 0, 1024, 1024]:
        raise StyleLockError("canvas.view_box must be exactly [0, 0, 1024, 1024]")
    safe_margin = canvas["safe_margin_px"]
    tolerance = canvas["optical_center_tolerance_px"]
    if isinstance(safe_margin, bool) or not isinstance(safe_margin, int) or not 0 <= safe_margin <= 256:
        raise StyleLockError("canvas.safe_margin_px must be an integer from 0 to 256")
    if isinstance(tolerance, bool) or not isinstance(tolerance, int) or not 0 <= tolerance <= 256:
        raise StyleLockError("canvas.optical_center_tolerance_px must be an integer from 0 to 256")

    palette = _exact(root["palette"], _PALETTE, "palette")
    roles = palette["roles"]
    if not isinstance(roles, dict) or not roles or len(roles) > 64:
        raise StyleLockError("palette.roles must be a non-empty bounded object")
    for role, color in roles.items():
        if not isinstance(role, str) or not role or not isinstance(color, str) or not _HEX_RE.fullmatch(color):
            raise StyleLockError("palette roles must map names to uppercase #RRGGBB colors")
    if "outline" not in roles:
        raise StyleLockError("palette.roles must define outline")

    outline = _exact(root["outline"], _OUTLINE, "outline")
    large_width = _number(outline["large_width"], "outline.large_width", minimum=0.1, maximum=512)
    small_width = _number(outline["small_width"], "outline.small_width", minimum=0.1, maximum=512)
    if small_width < large_width:
        raise StyleLockError("small outline width must be greater than or equal to large outline width")
    if outline["linecap"] not in {"butt", "round", "square"}:
        raise StyleLockError("outline.linecap is invalid")
    if outline["linejoin"] not in {"miter", "round", "bevel"}:
        raise StyleLockError("outline.linejoin is invalid")

    geometry = _exact(root["geometry"], _GEOMETRY, "geometry")
    for key in ("radii", "proportions", "eyes", "bounds", "metaphor_zone"):
        _numeric_tree(geometry[key], f"geometry.{key}")
    forbidden = geometry["forbidden_zones"]
    if not isinstance(forbidden, list) or len(forbidden) > 32:
        raise StyleLockError("geometry.forbidden_zones must be a bounded array")
    for index, zone in enumerate(forbidden):
        if not isinstance(zone, list) or len(zone) != 4:
            raise StyleLockError(f"geometry.forbidden_zones[{index}] must contain four numbers")
        _numeric_tree(zone, f"geometry.forbidden_zones[{index}]")

    lighting = _exact(root["lighting"], _LIGHTING, "lighting")
    if lighting["direction"] not in {"top-left", "top", "top-right", "none"}:
        raise StyleLockError("lighting.direction is invalid")
    _number(lighting["softness"], "lighting.softness", minimum=0, maximum=1)
    if not isinstance(root["form_character"], str) or not root["form_character"].strip() or len(root["form_character"]) > 256:
        raise StyleLockError("form_character must be a short non-empty string")

    visual = _exact(root["visual_weight"], _VISUAL_WEIGHT, "visual_weight")
    target = _number(visual["target"], "visual_weight.target", minimum=0, maximum=1)
    minimum = _number(visual["minimum"], "visual_weight.minimum", minimum=0, maximum=1)
    maximum = _number(visual["maximum"], "visual_weight.maximum", minimum=0, maximum=1)
    if not minimum <= target <= maximum:
        raise StyleLockError("visual weight must satisfy minimum <= target <= maximum")

    small = _exact(root["small_size"], _SMALL, "small_size")
    simplifications = small["simplifications"]
    if not isinstance(simplifications, list) or not simplifications or len(simplifications) > 64:
        raise StyleLockError("small_size.simplifications must be a non-empty bounded array")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 240 for item in simplifications):
        raise StyleLockError("small_size.simplifications contains an invalid item")
    _number(small["minimum_element_px"], "small_size.minimum_element_px", minimum=0.1, maximum=16)
    _number(small["minimum_gap_px"], "small_size.minimum_gap_px", minimum=0.1, maximum=16)

    transparency = _exact(root["transparency"], _TRANSPARENCY, "transparency")
    if not isinstance(transparency["transparent_corners"], bool) or not isinstance(transparency["full_bleed_allowed"], bool):
        raise StyleLockError("transparency flags must be booleans")
    if transparency["transparent_corners"] and transparency["full_bleed_allowed"]:
        raise StyleLockError("transparent_corners and full_bleed_allowed cannot both be true")

    canonical = canonical_json_bytes(root)
    if raw != canonical:
        raise StyleLockError("style-lock.json must use canonical JSON formatting")
    return StyleLock(
        path=Path(path),
        data=root,
        canonical=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
        style_id=style_id,
        style_version=style_version,
        preset_id=preset_id,
        preset_version=preset_version,
        safe_margin_px=safe_margin,
        optical_center_tolerance_px=tolerance,
        transparent_corners=transparency["transparent_corners"],
        full_bleed_allowed=transparency["full_bleed_allowed"],
    )


def validate_svg_pair_against_style_lock(lock: StyleLock, large_svg: bytes, small_svg: bytes) -> None:
    """Check the measurable contract items that can be established statically."""

    import xml.etree.ElementTree as ET

    try:
        large_root = ET.fromstring(large_svg)
        small_root = ET.fromstring(small_svg)
    except ET.ParseError as exc:  # Sanitizer should have caught this first.
        raise StyleLockError(f"cannot compare SVG pair with style lock: {exc}") from exc

    outline = lock.data["palette"]["roles"]["outline"]
    large_width = str(lock.data["outline"]["large_width"])
    small_width = str(lock.data["outline"]["small_width"])

    def values(root: ET.Element, attribute: str) -> set[str]:
        return {element.attrib[attribute] for element in root.iter() if attribute in element.attrib}

    def literal_palette(root: ET.Element) -> set[str]:
        colors: set[str] = set()
        for element in root.iter():
            for attribute in ("fill", "stroke", "stop-color"):
                value = element.attrib.get(attribute)
                if value is not None and _HEX_RE.fullmatch(value.upper()):
                    colors.add(value.upper())
        return colors

    if outline not in values(large_root, "stroke") or outline not in values(small_root, "stroke"):
        raise StyleLockError("both SVG tiers must use the locked outline color")
    if large_width not in values(large_root, "stroke-width"):
        raise StyleLockError(f"large SVG does not use locked outline width {large_width}")
    if small_width not in values(small_root, "stroke-width"):
        raise StyleLockError(f"small SVG does not use locked outline width {small_width}")

    locked_colors = set(lock.data["palette"]["roles"].values())
    actual_colors = literal_palette(large_root) | literal_palette(small_root)
    undeclared = sorted(actual_colors - locked_colors)
    if undeclared:
        raise StyleLockError(
            "SVG tiers use literal colors that are absent from palette.roles: " + ", ".join(undeclared)
        )
