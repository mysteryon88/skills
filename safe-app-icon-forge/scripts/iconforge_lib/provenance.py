from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import JsonSecurityError, ProvenanceError
from .json_safe import canonical_json_bytes, load_json_file

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_TOP = {"schema_version", "references"}
_ENTRY = {
    "id", "kind", "source", "author", "rights_holder", "license", "accessed_at",
    "permission", "sha256", "inspiration_only", "copied_asset",
}


@dataclass(frozen=True, slots=True)
class Provenance:
    path: Path
    data: dict[str, Any]
    canonical: bytes
    sha256: str
    entry_count: int


def load_provenance(path: Path) -> Provenance:
    try:
        value, raw = load_json_file(path, maximum=512 * 1024, label="provenance.json")
    except JsonSecurityError as exc:
        raise ProvenanceError(str(exc)) from exc
    if not isinstance(value, dict) or set(value) != _TOP or value["schema_version"] != 1:
        raise ProvenanceError("provenance.json must use schema_version 1 and only the references key")
    references = value["references"]
    if not isinstance(references, list) or len(references) > 256:
        raise ProvenanceError("references must be an array with at most 256 entries")
    seen: set[str] = set()
    for index, entry in enumerate(references):
        label = f"references[{index}]"
        if not isinstance(entry, dict) or set(entry) != _ENTRY:
            raise ProvenanceError(f"{label} has missing or unknown keys")
        entry_id = entry["id"]
        if not isinstance(entry_id, str) or not _ID_RE.fullmatch(entry_id) or entry_id in seen:
            raise ProvenanceError(f"{label}.id is invalid or duplicated")
        seen.add(entry_id)
        if entry["kind"] not in {"local", "url", "user-provided", "original"}:
            raise ProvenanceError(f"{label}.kind is invalid")
        for key in ("source", "author", "rights_holder", "license", "accessed_at", "permission"):
            if entry[key] is not None and (not isinstance(entry[key], str) or len(entry[key]) > 2048):
                raise ProvenanceError(f"{label}.{key} must be null or a bounded string")
        digest = entry["sha256"]
        if digest is not None and (not isinstance(digest, str) or not _SHA_RE.fullmatch(digest)):
            raise ProvenanceError(f"{label}.sha256 must be null or lowercase SHA-256")
        if not isinstance(entry["inspiration_only"], bool) or not isinstance(entry["copied_asset"], bool):
            raise ProvenanceError(f"{label} flags must be booleans")
        if entry["copied_asset"] and (not entry["license"] or not entry["permission"]):
            raise ProvenanceError(f"{label} copied assets require license and permission metadata")
    canonical = canonical_json_bytes(value)
    if raw != canonical:
        raise ProvenanceError("provenance.json must use canonical JSON formatting")
    return Provenance(Path(path), value, canonical, hashlib.sha256(canonical).hexdigest(), len(references))
