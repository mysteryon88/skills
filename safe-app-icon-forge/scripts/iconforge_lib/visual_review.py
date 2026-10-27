from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import JsonSecurityError, VisualReviewError
from .json_safe import canonical_json_bytes, load_json_file

_TOP = {"schema_version", "draft", "concepts", "selected_concept", "final", "notes"}
_CONCEPT = {"id", "summary", "scores", "total"}
_CONCEPT_SCORES = {
    "metaphor_clarity", "silhouette_uniqueness", "small_size_readability",
    "brand_or_series_fit", "optical_simplification", "association_safety",
}
_FINAL = {
    "status", "scores", "total", "reviewed_sizes", "backgrounds", "reviewer",
    "view_scale_percent", "review_source_sha256", "review_input_sha256",
    "review_output_sha256",
}
_FINAL_SCORES = {
    "silhouette", "metaphor_recognition", "small_size_readability",
    "visual_weight", "optical_center", "style_coherence",
}
_REQUIRED_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class VisualReview:
    path: Path
    data: dict[str, Any]
    canonical: bytes
    sha256: str
    selected_concept: str
    selected_concept_total: int
    final_total: int | None
    status: str
    draft: bool
    review_source_sha256: str | None
    review_input_sha256: str | None
    review_output_sha256: str | None

    def matches_source(self, digest: str) -> bool:
        return self.status == "pass" and self.review_source_sha256 == digest

    def matches_input(self, digest: str) -> bool:
        return self.status == "pass" and self.review_input_sha256 == digest

    def matches_output(self, digest: str) -> bool:
        return self.status == "pass" and self.review_output_sha256 == digest


def _scores(value: Any, keys: set[str], *, minimum: int, maximum: int, label: str) -> tuple[dict[str, int], int]:
    if not isinstance(value, dict) or set(value) != keys:
        raise VisualReviewError(f"{label} score keys are invalid")
    result: dict[str, int] = {}
    for key in sorted(keys):
        score = value[key]
        if isinstance(score, bool) or not isinstance(score, int) or not minimum <= score <= maximum:
            raise VisualReviewError(f"{label}.{key} must be an integer from {minimum} to {maximum}")
        result[key] = score
    return result, sum(result.values())


def _sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise VisualReviewError(f"{label} must be a lowercase SHA-256")
    return value


def load_visual_review(path: Path, *, require_pass: bool = True) -> VisualReview:
    try:
        value, raw = load_json_file(path, maximum=256 * 1024, label="visual-review.json")
    except JsonSecurityError as exc:
        raise VisualReviewError(str(exc)) from exc
    if not isinstance(value, dict) or set(value) != _TOP or value["schema_version"] != 2:
        raise VisualReviewError("visual-review.json has an invalid top-level schema")
    draft = value["draft"]
    if not isinstance(draft, bool):
        raise VisualReviewError("draft must be a JSON boolean")

    concepts = value["concepts"]
    if not isinstance(concepts, list) or len(concepts) != 3:
        raise VisualReviewError("visual review must contain exactly three concepts")
    ids: list[str] = []
    ranking: dict[str, tuple[int, int, int, int]] = {}
    concept_scores: dict[str, dict[str, int]] = {}
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict) or set(concept) != _CONCEPT:
            raise VisualReviewError(f"concepts[{index}] has invalid keys")
        concept_id = concept["id"]
        summary = concept["summary"]
        if not isinstance(concept_id, str) or not concept_id or concept_id in ids or len(concept_id) > 160:
            raise VisualReviewError(f"concepts[{index}].id is invalid or duplicated")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 500:
            raise VisualReviewError(f"concepts[{index}].summary is invalid")
        score_map, total = _scores(
            concept["scores"],
            _CONCEPT_SCORES,
            minimum=1,
            maximum=5,
            label=f"concepts[{index}].scores",
        )
        if concept["total"] != total:
            raise VisualReviewError(f"concepts[{index}].total does not match its scores")
        ids.append(concept_id)
        concept_scores[concept_id] = score_map
        ranking[concept_id] = (
            total,
            score_map["small_size_readability"],
            score_map["silhouette_uniqueness"],
            score_map["brand_or_series_fit"],
        )

    selected = value["selected_concept"]
    if selected not in ranking:
        raise VisualReviewError("selected_concept must identify one of the three concepts")
    best = max(ranking.values())
    if ranking[selected] != best:
        raise VisualReviewError(
            "selected_concept must follow the ranking: total, then small-size readability, "
            "then silhouette uniqueness, then brand/series fit"
        )
    selected_total = ranking[selected][0]
    if not draft:
        if selected_total < 24:
            raise VisualReviewError("selected concept must score at least 24/30 before artwork preview")
        weak = sorted(key for key, score in concept_scores[selected].items() if score < 3)
        if weak:
            raise VisualReviewError(f"selected concept has critical scores below 3/5: {weak}")

    final = value["final"]
    review_source_sha256: str | None = None
    review_input_sha256: str | None = None
    review_output_sha256: str | None = None
    if final is None:
        status = "pending"
        final_total = None
        if require_pass:
            raise VisualReviewError("final visual review is pending")
    else:
        if draft:
            raise VisualReviewError("draft visual review cannot contain a final approval")
        if not isinstance(final, dict) or set(final) != _FINAL:
            raise VisualReviewError("final review has invalid keys")
        score_map, final_total = _scores(
            final["scores"], _FINAL_SCORES, minimum=0, maximum=2, label="final.scores"
        )
        if final["total"] != final_total:
            raise VisualReviewError("final.total does not match its scores")
        if final["status"] not in {"pass", "fail"}:
            raise VisualReviewError("final.status must be pass or fail")
        status = final["status"]
        if status == "pass":
            if final_total < 10:
                raise VisualReviewError("final visual review cannot pass below 10/12")
            zero_scores = sorted(key for key, score in score_map.items() if score == 0)
            if zero_scores:
                raise VisualReviewError(f"final visual review cannot pass with critical zero scores: {zero_scores}")
        if final["reviewed_sizes"] != _REQUIRED_SIZES:
            raise VisualReviewError(f"final.reviewed_sizes must be exactly {_REQUIRED_SIZES}")
        if final["backgrounds"] != ["light", "dark", "neutral", "taskbar"]:
            raise VisualReviewError("final.backgrounds must cover light, dark, neutral, and taskbar")
        if final["view_scale_percent"] != 100 or isinstance(final["view_scale_percent"], bool):
            raise VisualReviewError("final.view_scale_percent must be exactly 100")
        if not isinstance(final["reviewer"], str) or not final["reviewer"].strip() or len(final["reviewer"]) > 160:
            raise VisualReviewError("final.reviewer must be a non-empty string")
        review_source_sha256 = _sha(final["review_source_sha256"], label="final.review_source_sha256")
        review_input_sha256 = _sha(final["review_input_sha256"], label="final.review_input_sha256")
        review_output_sha256 = _sha(final["review_output_sha256"], label="final.review_output_sha256")
        if require_pass and status == "fail":
            raise VisualReviewError("project is blocked by a failed visual review")

    if not isinstance(value["notes"], str) or len(value["notes"]) > 4000:
        raise VisualReviewError("notes must be a bounded string")

    canonical = canonical_json_bytes(value)
    if raw != canonical:
        raise VisualReviewError("visual-review.json must use canonical JSON formatting")
    return VisualReview(
        Path(path),
        value,
        canonical,
        hashlib.sha256(canonical).hexdigest(),
        selected,
        selected_total,
        final_total,
        status,
        draft,
        review_source_sha256,
        review_input_sha256,
        review_output_sha256,
    )
