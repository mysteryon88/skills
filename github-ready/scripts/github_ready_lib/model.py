SCHEMA_VERSION = 1


def coverage_gap(
    *,
    path: str | None,
    object_id: str | None,
    evidence: str,
    size: int | None = None,
) -> dict[str, object]:
    """Build a JSON-safe record for a part of reachable history not scanned."""
    gap: dict[str, object] = {
        "kind": "coverage-gap",
        "severity": "BLOCKER",
        "action": "review",
        "evidence": evidence,
        "recommendation": "Resolve the coverage gap before publishing the repository.",
    }
    if path is not None:
        gap["path"] = path
    if object_id is not None:
        gap["object_id"] = object_id
    if size is not None:
        gap["size"] = size
    return gap
