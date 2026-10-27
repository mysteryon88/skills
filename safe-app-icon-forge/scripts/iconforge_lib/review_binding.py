from __future__ import annotations

import hashlib
import platform
import re
import sys
from dataclasses import dataclass
from typing import Any, Mapping

from .config import SKILL_VERSION
from .errors import JsonSecurityError, VisualReviewError
from .json_safe import canonical_json_bytes, loads_strict

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPORTED_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024)
_EVIDENCE_TOP = {
    "schema_version",
    "skill_version",
    "source",
    "renderer",
    "environment",
    "review_source_sha256",
    "review_input_sha256",
    "reviewed_assets",
    "review_output_sha256",
}
_SOURCE_KEYS = {
    "iconforge_sha256",
    "large_svg_sha256",
    "small_svg_sha256",
    "style_lock_sha256",
}
_RENDERER_KEYS = {"name", "version_output", "lock_id", "executable_sha256"}
_ENVIRONMENT_KEYS = {"platform", "machine", "python_version"}
_ASSET_KEYS = {"png", "review_svg_sha256", "review_png_sha256"}


@dataclass(frozen=True, slots=True)
class ReviewSource:
    source: dict[str, Any]
    review_source_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewInput:
    source: dict[str, Any]
    renderer: dict[str, str]
    environment: dict[str, str]
    review_source_sha256: str
    review_input_sha256: str


@dataclass(frozen=True, slots=True)
class ReviewEvidence:
    data: dict[str, Any]
    canonical: bytes
    sha256: str
    review_source_sha256: str
    review_input_sha256: str
    review_output_sha256: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_object(value: Any) -> str:
    return _sha256(canonical_json_bytes(value, pretty=False))


def current_environment() -> dict[str, str]:
    return {
        "platform": platform.system().lower() or "unknown",
        "machine": platform.machine().lower() or "unknown",
        "python_version": sys.version.split()[0],
    }


def renderer_payload(identity: Any) -> dict[str, str]:
    name = getattr(identity, "name", None)
    version = getattr(identity, "version", None)
    lock_id = getattr(identity, "lock_id", None)
    executable_sha256 = getattr(identity, "executable_sha256", None)
    return _normalize_renderer(
        {
            "name": name,
            "version_output": version,
            "lock_id": lock_id,
            "executable_sha256": executable_sha256,
        }
    )


def _require_sha(value: Any, *, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise VisualReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _normalize_renderer(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != _RENDERER_KEYS:
        raise VisualReviewError("review renderer identity has invalid keys")
    result: dict[str, str] = {}
    for key in ("name", "version_output", "lock_id"):
        item = value[key]
        if not isinstance(item, str) or not item or len(item) > 1024:
            raise VisualReviewError(f"review renderer {key} is invalid")
        result[key] = item
    digest = _require_sha(value["executable_sha256"], label="review renderer executable_sha256")
    assert isinstance(digest, str)
    result["executable_sha256"] = digest
    return result


def _normalize_environment(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != _ENVIRONMENT_KEYS:
        raise VisualReviewError("review environment has invalid keys")
    result: dict[str, str] = {}
    for key in sorted(_ENVIRONMENT_KEYS):
        item = value[key]
        if not isinstance(item, str) or not item or len(item) > 256:
            raise VisualReviewError(f"review environment {key} is invalid")
        result[key] = item
    return result


def make_review_source(
    *,
    iconforge_sha256: str,
    large_svg_sha256: str,
    small_svg_sha256: str,
    style_lock_sha256: str | None,
) -> ReviewSource:
    source = {
        "iconforge_sha256": _require_sha(iconforge_sha256, label="iconforge_sha256"),
        "large_svg_sha256": _require_sha(large_svg_sha256, label="large_svg_sha256"),
        "small_svg_sha256": _require_sha(small_svg_sha256, label="small_svg_sha256"),
        "style_lock_sha256": _require_sha(
            style_lock_sha256, label="style_lock_sha256", nullable=True
        ),
    }
    source_payload = {
        "schema_version": 1,
        "skill_version": SKILL_VERSION,
        "source": source,
    }
    return ReviewSource(source, _hash_object(source_payload))


def make_review_input(
    *,
    iconforge_sha256: str,
    large_svg_sha256: str,
    small_svg_sha256: str,
    style_lock_sha256: str | None,
    renderer: Any | Mapping[str, Any],
    environment: Mapping[str, Any] | None = None,
) -> ReviewInput:
    review_source = make_review_source(
        iconforge_sha256=iconforge_sha256,
        large_svg_sha256=large_svg_sha256,
        small_svg_sha256=small_svg_sha256,
        style_lock_sha256=style_lock_sha256,
    )
    renderer_data = (
        _normalize_renderer(renderer)
        if isinstance(renderer, Mapping)
        else renderer_payload(renderer)
    )
    environment_data = _normalize_environment(environment or current_environment())
    input_payload = {
        "schema_version": 1,
        "review_source_sha256": review_source.review_source_sha256,
        "renderer": renderer_data,
        "environment": environment_data,
    }
    input_hash = _hash_object(input_payload)
    return ReviewInput(
        review_source.source, renderer_data, environment_data,
        review_source.review_source_sha256, input_hash
    )


def _asset_payload(
    pngs: Mapping[int, bytes | str],
    *,
    review_svg: bytes | str,
    review_png: bytes | str,
) -> dict[str, Any]:
    if set(pngs) != set(_EXPORTED_SIZES):
        raise VisualReviewError(f"review evidence PNG sizes must be exactly {list(_EXPORTED_SIZES)}")

    def digest(value: bytes | str, label: str) -> str:
        if isinstance(value, bytes):
            return _sha256(value)
        checked = _require_sha(value, label=label)
        assert isinstance(checked, str)
        return checked

    return {
        "png": [
            {"size": size, "sha256": digest(pngs[size], f"review PNG {size}px SHA-256")}
            for size in _EXPORTED_SIZES
        ],
        "review_svg_sha256": digest(review_svg, "review SVG SHA-256"),
        "review_png_sha256": digest(review_png, "review sheet PNG SHA-256"),
    }


def make_review_evidence(
    review_input: ReviewInput,
    pngs: Mapping[int, bytes | str],
    *,
    review_svg: bytes | str,
    review_png: bytes | str,
) -> ReviewEvidence:
    assets = _asset_payload(pngs, review_svg=review_svg, review_png=review_png)
    output_payload = {
        "schema_version": 1,
        "review_input_sha256": review_input.review_input_sha256,
        "reviewed_assets": assets,
    }
    output_hash = _hash_object(output_payload)
    data = {
        "schema_version": 1,
        "skill_version": SKILL_VERSION,
        "source": review_input.source,
        "renderer": review_input.renderer,
        "environment": review_input.environment,
        "review_source_sha256": review_input.review_source_sha256,
        "review_input_sha256": review_input.review_input_sha256,
        "reviewed_assets": assets,
        "review_output_sha256": output_hash,
    }
    canonical = canonical_json_bytes(data)
    return ReviewEvidence(
        data=data,
        canonical=canonical,
        sha256=_sha256(canonical),
        review_source_sha256=review_input.review_source_sha256,
        review_input_sha256=review_input.review_input_sha256,
        review_output_sha256=output_hash,
    )


def load_review_evidence_bytes(data: bytes) -> ReviewEvidence:
    try:
        value = loads_strict(data, label="review-evidence.json")
    except JsonSecurityError as exc:
        raise VisualReviewError(str(exc)) from exc
    if not isinstance(value, dict) or set(value) != _EVIDENCE_TOP:
        raise VisualReviewError("review-evidence.json has an invalid top-level schema")
    if value["schema_version"] != 1 or value["skill_version"] != SKILL_VERSION:
        raise VisualReviewError("review-evidence.json schema or skill version is unsupported")
    source = value["source"]
    if not isinstance(source, dict) or set(source) != _SOURCE_KEYS:
        raise VisualReviewError("review evidence source object is invalid")
    review_input = make_review_input(
        iconforge_sha256=source["iconforge_sha256"],
        large_svg_sha256=source["large_svg_sha256"],
        small_svg_sha256=source["small_svg_sha256"],
        style_lock_sha256=source["style_lock_sha256"],
        renderer=value["renderer"],
        environment=value["environment"],
    )
    if value["review_source_sha256"] != review_input.review_source_sha256:
        raise VisualReviewError("review evidence source hash is stale")
    if value["review_input_sha256"] != review_input.review_input_sha256:
        raise VisualReviewError("review evidence input hash is stale")
    assets = value["reviewed_assets"]
    if not isinstance(assets, dict) or set(assets) != _ASSET_KEYS:
        raise VisualReviewError("review evidence asset object is invalid")
    png = assets["png"]
    if not isinstance(png, list) or len(png) != len(_EXPORTED_SIZES):
        raise VisualReviewError("review evidence PNG list is invalid")
    png_hashes: dict[int, str] = {}
    for expected_size, item in zip(_EXPORTED_SIZES, png, strict=True):
        if not isinstance(item, dict) or set(item) != {"size", "sha256"}:
            raise VisualReviewError("review evidence PNG record is invalid")
        if item["size"] != expected_size:
            raise VisualReviewError("review evidence PNG sizes are not canonical")
        digest = _require_sha(item["sha256"], label=f"review evidence {expected_size}px SHA-256")
        assert isinstance(digest, str)
        png_hashes[expected_size] = digest
    regenerated = make_review_evidence(
        review_input,
        png_hashes,
        review_svg=assets["review_svg_sha256"],
        review_png=assets["review_png_sha256"],
    )
    canonical = canonical_json_bytes(value)
    if data != canonical:
        raise VisualReviewError("review-evidence.json must use canonical JSON formatting")
    if value["review_output_sha256"] != regenerated.review_output_sha256:
        raise VisualReviewError("review evidence output hash is stale")
    return ReviewEvidence(
        data=value,
        canonical=canonical,
        sha256=_sha256(canonical),
        review_source_sha256=review_input.review_source_sha256,
        review_input_sha256=review_input.review_input_sha256,
        review_output_sha256=regenerated.review_output_sha256,
    )
