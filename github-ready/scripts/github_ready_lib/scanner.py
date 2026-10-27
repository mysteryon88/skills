from __future__ import annotations

import hashlib
import re
import stat
from pathlib import Path, PurePosixPath

from .git_repo import GitBudgetExceeded, GitCommandError, GitRepository
from .model import SCHEMA_VERSION, coverage_gap
from .policy import classify_path


_ASSIGNMENT_PREFIX = (
    rb"(?im)^[ \t]*(?:export[ \t]+)?(?:[A-Za-z0-9]+[_-])*"
    rb"(?:api[_-]?key|auth[_-]?token|password|secret|token)[ \t]*[:=][ \t]*"
)
SECRET_DETECTORS: tuple[tuple[str, re.Pattern[bytes], int], ...] = (
    ("github-token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36}\b"), 0),
    ("openai-api-key", re.compile(rb"\bsk-[A-Za-z0-9]{20,}\b"), 0),
    (
        "private-key-header",
        re.compile(rb"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----"),
        0,
    ),
    (
        "credential-assignment",
        re.compile(
            _ASSIGNMENT_PREFIX
            + rb'"((?:\\.|[^"\\\r\n]){8,})"[ \t]*(?:[#;][^\r\n]*)?\r?$'
        ),
        1,
    ),
    (
        "credential-assignment",
        re.compile(
            _ASSIGNMENT_PREFIX
            + rb"'((?:\\.|[^'\\\r\n]){8,})'[ \t]*(?:[#;][^\r\n]*)?\r?$"
        ),
        1,
    ),
    (
        "credential-assignment",
        re.compile(
            _ASSIGNMENT_PREFIX
            + rb"([A-Za-z0-9_./+=!:@%?,~*\-]{8,})[ \t]*(?:[#;][^\r\n]*)?\r?$"
        ),
        1,
    ),
)
_METADATA_ASSIGNMENT_PREFIX = (
    rb"(?i)(?<![A-Za-z0-9_-])(?:[A-Za-z0-9]+[_-])*"
    rb"(?:api[_-]?key|auth[_-]?token|password|secret|token)[ \t]*[:=][ \t]*"
)
METADATA_SECRET_DETECTORS: tuple[tuple[str, re.Pattern[bytes], int], ...] = (
    *SECRET_DETECTORS[:3],
    (
        "credential-assignment",
        re.compile(_METADATA_ASSIGNMENT_PREFIX + rb'"((?:\\.|[^"\\\r\n]){8,})"'),
        1,
    ),
    (
        "credential-assignment",
        re.compile(_METADATA_ASSIGNMENT_PREFIX + rb"'((?:\\.|[^'\\\r\n]){8,})'"),
        1,
    ),
    (
        "credential-assignment",
        re.compile(
            _METADATA_ASSIGNMENT_PREFIX
            + rb"([A-Za-z0-9_./+=!:@%?,~*\-]{8,})"
        ),
        1,
    ),
)

_MANIFEST_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "cargo.lock",
    "cargo.toml",
    "package-lock.json",
    "package.json",
    "pipfile",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "yarn.lock",
}
_LOCAL_DEPENDENCY_REFERENCE = re.compile(
    rb"(?i)(?:file:(?://)?(?:/[A-Za-z0-9._~!@%+,:=\\/-]+|[A-Z]:[\\/][A-Za-z0-9._~!@%+,:=\\/-]+)"
    rb"|(?:[A-Z]:[\\/]|/(?:home|users|private|tmp|var|opt)/)[A-Za-z0-9._~!@%+,:=\\/-]+)"
)
_ROOT_README_NAMES = {"readme", "readme.md", "readme.rst", "readme.txt"}
_ROOT_LICENSE_NAMES = {
    "copying",
    "copying.md",
    "copying.txt",
    "license",
    "license.md",
    "license.txt",
}
_GIT_BYTES_MARKER = "git-bytes:hex:"
_GIT_TEXT_MARKER = "git-text:hex:"


def masked_fingerprint(secret: bytes) -> str:
    return "sha256:" + hashlib.sha256(secret).hexdigest()[:12]


def _encode_git_name_for_output(value: str) -> str:
    data = value.encode("utf-8", errors="surrogateescape")
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _GIT_BYTES_MARKER + data.hex()
    if decoded.startswith((_GIT_BYTES_MARKER, _GIT_TEXT_MARKER)):
        return _GIT_TEXT_MARKER + data.hex()
    return decoded


def _decode_git_name_from_output(value: str) -> str:
    if value.startswith(_GIT_BYTES_MARKER):
        return bytes.fromhex(value[len(_GIT_BYTES_MARKER) :]).decode(
            "utf-8", errors="surrogateescape"
        )
    if value.startswith(_GIT_TEXT_MARKER):
        return bytes.fromhex(value[len(_GIT_TEXT_MARKER) :]).decode(
            "utf-8", errors="strict"
        )
    return value


def _redact_metadata_string(value: str) -> str:
    data = value.encode("utf-8", errors="surrogateescape")
    spans: list[tuple[int, int, str]] = []
    for _, pattern, group in METADATA_SECRET_DETECTORS:
        for match in pattern.finditer(data):
            secret = match.group(group)
            start, end = match.span(group)
            spans.append((start, end, "redacted:" + masked_fingerprint(secret)))
    if spans:
        selected: list[tuple[int, int, str]] = []
        cursor = -1
        for start, end, replacement in sorted(
            spans, key=lambda item: (item[0], -item[1])
        ):
            if start < cursor:
                continue
            selected.append((start, end, replacement))
            cursor = end
        chunks: list[bytes] = []
        cursor = 0
        for start, end, replacement in selected:
            chunks.append(data[cursor:start])
            chunks.append(replacement.encode("ascii"))
            cursor = end
        chunks.append(data[cursor:])
        data = b"".join(chunks)
    return _encode_git_name_for_output(
        data.decode("utf-8", errors="surrogateescape")
    )


def _redact_metadata(value: object) -> object:
    if isinstance(value, str):
        return _redact_metadata_string(value)
    if isinstance(value, list):
        return [_redact_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_metadata(item) for item in value)
    if isinstance(value, dict):
        return {
            _redact_metadata_string(key) if isinstance(key, str) else key: _redact_metadata(item)
            for key, item in value.items()
        }
    return value


def _redact_result(result: dict[str, object]) -> dict[str, object]:
    redacted = _redact_metadata(result)
    assert isinstance(redacted, dict)
    return redacted


def scan_secret_candidates(
    data: bytes,
    *,
    location: dict[str, object],
    budget: GitRepository | None = None,
) -> list[dict[str, object]]:
    """Detect byte-pattern secrets without retaining matched bytes in the result."""
    raw_path = location.get("path")
    path = str(raw_path) if raw_path is not None else None
    object_id = str(location["object_id"])
    candidates: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    specific_spans: list[tuple[int, int]] = []
    for detector, pattern, group in SECRET_DETECTORS:
        if budget is not None:
            budget.consume_work()
        for match in pattern.finditer(data):
            if budget is not None:
                budget.consume_work()
            secret = match.group(group)
            span = match.span(group)
            if detector == "credential-assignment" and any(
                span[0] < end and start < span[1] for start, end in specific_spans
            ):
                continue
            if detector in {"github-token", "openai-api-key"}:
                specific_spans.append(span)
            fingerprint = masked_fingerprint(secret)
            key = (detector, fingerprint, path or "", object_id)
            if key in seen:
                continue
            seen.add(key)
            candidate: dict[str, object] = {
                "kind": "secret",
                "severity": "BLOCKER",
                "action": "review",
                "detector": detector,
                "fingerprint": fingerprint,
                "line": data.count(b"\n", 0, match.start(group)) + 1,
                "object_id": object_id,
                "evidence": "redacted secret candidate",
                "recommendation": "Triage the candidate without disclosure and follow approved remediation only if confirmed.",
            }
            if path is not None:
                candidate["path"] = path
            if budget is not None:
                budget.consume_work(
                    0,
                    retained_bytes=sum(
                        len(value.encode("utf-8", errors="surrogateescape"))
                        for value in candidate.values()
                        if isinstance(value, str)
                    ),
                )
            candidates.append(candidate)
    return candidates


def _is_dependency_manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].casefold()
    return name in _MANIFEST_NAMES or (
        name.startswith("requirements-") and name.endswith(".txt")
    )


def _scan_local_dependency_candidates(
    data: bytes,
    *,
    location: dict[str, object],
    budget: GitRepository | None = None,
) -> list[dict[str, object]]:
    raw_path = location.get("path")
    if raw_path is None:
        return []
    path = str(raw_path)
    if not _is_dependency_manifest(path):
        return []
    object_id = str(location["object_id"])
    candidates: list[dict[str, object]] = []
    seen_lines: set[int] = set()
    if budget is not None:
        budget.consume_work()
    for match in _LOCAL_DEPENDENCY_REFERENCE.finditer(data):
        if budget is not None:
            budget.consume_work()
        line = data.count(b"\n", 0, match.start()) + 1
        if line in seen_lines:
            continue
        seen_lines.add(line)
        candidate: dict[str, object] = {
            "kind": "local-dependency-path",
            "severity": "WARNING",
            "action": "review",
            "path": path,
            "line": line,
            "object_id": object_id,
            "evidence": "redacted absolute local dependency reference",
            "recommendation": "Replace it with a portable dependency reference before publication.",
        }
        if budget is not None:
            budget.consume_work(
                0,
                retained_bytes=sum(
                    len(value.encode("utf-8", errors="surrogateescape"))
                    for value in candidate.values()
                    if isinstance(value, str)
                ),
            )
        candidates.append(candidate)
    return candidates


def _empty_result() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "inventory": {"tracked": [], "untracked": [], "ignored": []},
        "candidates": [],
        "coverage": {
            "refs": [],
            "shallow": False,
            "unique_blobs": 0,
            "non_text_blobs": [],
            "gaps": [],
            "complete": True,
        },
    }


def _append_gap(
    result: dict[str, object],
    *,
    path: str | None,
    object_id: str | None,
    evidence: str,
    size: int | None = None,
) -> None:
    gap = coverage_gap(path=path, object_id=object_id, evidence=evidence, size=size)
    coverage = result["coverage"]
    assert isinstance(coverage, dict)
    gaps = coverage["gaps"]
    assert isinstance(gaps, list)
    if gap not in gaps:
        gaps.append(gap)
    coverage["complete"] = False


def _has_root_repository_evidence(
    paths: list[str], names: set[str], budget: GitRepository | None = None
) -> bool:
    for path in paths:
        if budget is not None:
            budget.consume_work()
        if "/" not in path and path.casefold() in names:
            return True
    return False


def _conflicting_lockfiles(
    paths: list[str], budget: GitRepository | None = None
) -> set[str]:
    groups = (
        {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"},
        {"poetry.lock", "pipfile.lock"},
    )
    by_owner: dict[str, list[str]] = {}
    for path in paths:
        if budget is not None:
            budget.consume_work()
        owner, _, _ = path.rpartition("/")
        by_owner.setdefault(owner, []).append(path)
    conflicts: set[str] = set()
    for owner_paths in by_owner.values():
        if budget is not None:
            budget.consume_work()
        names = {path.rsplit("/", 1)[-1].casefold() for path in owner_paths}
        for group in groups:
            if budget is not None:
                budget.consume_work()
            if len(group & names) > 1:
                for path in owner_paths:
                    if budget is not None:
                        budget.consume_work()
                    if path.rsplit("/", 1)[-1].casefold() in group:
                        conflicts.add(path)
    return conflicts


def _candidate_key(candidate: dict[str, object]) -> tuple[str, str, str, str]:
    kind = str(candidate["kind"])
    if kind == "secret":
        discriminator = f"{candidate.get('detector', '')}:{candidate.get('fingerprint', '')}"
    elif kind == "ai-file":
        discriminator = f"{candidate.get('commit', '')}:{candidate.get('ref', '')}"
    else:
        discriminator = str(candidate.get("line", ""))
    return (
        kind,
        discriminator,
        str(candidate.get("path", candidate.get("ref", ""))),
        "" if kind == "secret" else str(candidate["object_id"]),
    )


def _record_candidate(
    candidates: list[dict[str, object]],
    indexed: dict[tuple[str, str, str, str], dict[str, object]],
    candidate: dict[str, object],
    budget: GitRepository | None = None,
) -> dict[str, object]:
    key = _candidate_key(candidate)
    existing = indexed.get(key)
    if existing is None:
        if budget is not None:
            retained_bytes = sum(
                len(value.encode("utf-8", errors="surrogateescape"))
                for value in candidate.values()
                if isinstance(value, str)
            )
            budget.consume_work(retained_bytes=retained_bytes)
        candidates.append(candidate)
        indexed[key] = candidate
        return candidate
    same_object = candidate.get("object_id") == existing.get("object_id")
    has_provenance = candidate.get("commit") is not None or candidate.get("ref") is not None
    if has_provenance and (same_object or existing.get("history_only") is not False):
        existing["object_id"] = candidate["object_id"]
        for field in ("commit", "ref"):
            if candidate.get(field) is None:
                existing.pop(field, None)
            else:
                existing[field] = candidate[field]
    if candidate.get("history_only") is False:
        existing["history_only"] = False
    return existing


def _append_non_text(
    non_text_blobs: list[dict[str, object]],
    seen: set[tuple[str, str]],
    *,
    path: str | None,
    object_id: str,
    size: int,
) -> None:
    key = (path or "", object_id)
    if key in seen:
        return
    seen.add(key)
    item: dict[str, object] = {"object_id": object_id, "size": size}
    if path is not None:
        item["path"] = path
    non_text_blobs.append(item)


def _current_path(root: Path, path: str) -> Path | None:
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return candidate


def _budget_gap(result: dict[str, object], evidence: str = "audit budget exhausted") -> None:
    _append_gap(result, path=None, object_id=None, evidence=evidence)


def _scan_repository(
    root: Path,
    *,
    max_blob_bytes: int = 8_388_608,
    timeout_seconds: int = 30,
    deadline: float | None = None,
    max_git_commands: int = 64,
    max_total_bytes: int = 268_435_456,
    max_work_units: int = 1_000_000,
    max_locations: int = 250_000,
    result: dict[str, object] | None = None,
) -> dict[str, object]:
    if result is None:
        result = _empty_result()
    try:
        repository = GitRepository(
            root,
            timeout_seconds=timeout_seconds,
            deadline=deadline,
            max_git_commands=max_git_commands,
            max_total_bytes=max_total_bytes,
            max_work_units=max_work_units,
            max_locations=max_locations,
        )
    except GitBudgetExceeded as error:
        _budget_gap(result, str(error))
        return _redact_result(result)

    try:
        inventory = repository.status_entries()
        start_refs = repository.ref_snapshot()
        shallow = repository.is_shallow()
    except GitBudgetExceeded as error:
        _budget_gap(result, str(error))
        return _redact_result(result)
    except GitCommandError:
        _append_gap(
            result,
            path=None,
            object_id=None,
            evidence="Git repository metadata could not be read",
        )
        return _redact_result(result)

    result["inventory"] = inventory
    coverage = result["coverage"]
    assert isinstance(coverage, dict)
    coverage["refs"] = [record.name for record in start_refs]
    coverage["shallow"] = shallow
    if shallow:
        _append_gap(
            result,
            path=None,
            object_id=None,
            evidence="repository history is shallow",
        )

    candidates = result["candidates"]
    assert isinstance(candidates, list)
    for state, paths in inventory.items():
        repository.consume_work()
        for path in paths:
            repository.consume_work()
            candidates.extend(classify_path(path, state))
    tracked_paths = inventory["tracked"]
    if not _has_root_repository_evidence(
        tracked_paths, _ROOT_README_NAMES, repository
    ):
        candidates.extend(classify_path("README.md", "missing"))
    if not _has_root_repository_evidence(
        tracked_paths, _ROOT_LICENSE_NAMES, repository
    ):
        candidates.extend(classify_path("LICENSE", "missing"))
    for path in sorted(_conflicting_lockfiles(tracked_paths, repository)):
        repository.consume_work()
        candidates.extend(classify_path(path, "conflicting-lockfile"))

    non_text_blobs = coverage["non_text_blobs"]
    assert isinstance(non_text_blobs, list)
    non_text_seen: set[tuple[str, str]] = set()
    indexed_candidates: dict[
        tuple[str, str, str, str], dict[str, object]
    ] = {}
    current_object_ids: dict[str, str] = {}
    secret_bases_by_object_id: dict[str, list[dict[str, object]]] = {}
    dependency_bases_by_object_id: dict[str, list[dict[str, object]]] = {}

    def secret_bases(data: bytes, object_id: str) -> list[dict[str, object]]:
        bases = secret_bases_by_object_id.get(object_id)
        if bases is None:
            bases = scan_secret_candidates(
                data,
                location={"object_id": object_id},
                budget=repository,
            )
            secret_bases_by_object_id[object_id] = bases
        return bases

    def dependency_bases(
        data: bytes, object_id: str, path: str
    ) -> list[dict[str, object]]:
        if not _is_dependency_manifest(path):
            return []
        bases = dependency_bases_by_object_id.get(object_id)
        if bases is None:
            bases = _scan_local_dependency_candidates(
                data,
                location={"path": path, "object_id": object_id},
                budget=repository,
            )
            dependency_bases_by_object_id[object_id] = bases
        return bases

    current_paths = sorted(set(inventory["tracked"] + inventory["untracked"]))
    for path in current_paths:
        try:
            repository.consume_work()
        except GitBudgetExceeded as error:
            _budget_gap(result, str(error))
            break
        current_file = _current_path(repository.root, path)
        if current_file is None:
            _append_gap(
                result,
                path=path,
                object_id=None,
                evidence="current path escapes the repository and was not scanned",
            )
            continue
        try:
            file_stat = current_file.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            _append_gap(
                result,
                path=path,
                object_id=None,
                evidence="current path metadata could not be read",
            )
            continue
        if stat.S_ISLNK(file_stat.st_mode):
            _append_gap(
                result,
                path=path,
                object_id=None,
                size=file_stat.st_size,
                evidence="current symbolic link was not followed",
            )
            continue
        if not stat.S_ISREG(file_stat.st_mode):
            _append_gap(
                result,
                path=path,
                object_id=None,
                size=file_stat.st_size,
                evidence="current non-regular file was not scanned",
            )
            continue
        if file_stat.st_size > max_blob_bytes:
            _append_gap(
                result,
                path=path,
                object_id=None,
                size=file_stat.st_size,
                evidence="current file exceeds the configured scan limit",
            )
            continue
        if not repository.try_consume_bytes(file_stat.st_size):
            _append_gap(
                result,
                path=path,
                object_id=None,
                size=file_stat.st_size,
                evidence="audit total-byte budget exhausted before current file read",
            )
            continue
        try:
            data = current_file.read_bytes()
        except OSError:
            _append_gap(
                result,
                path=path,
                object_id=None,
                size=file_stat.st_size,
                evidence="current file could not be read",
            )
            continue
        if len(data) > max_blob_bytes:
            _append_gap(
                result,
                path=path,
                object_id=None,
                size=len(data),
                evidence="current file grew beyond the configured scan limit",
            )
            continue
        object_id = repository.hash_blob(data)
        current_object_ids[path] = object_id
        repository.consume_work(retained_bytes=len(data))
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            _append_non_text(
                non_text_blobs,
                non_text_seen,
                path=path,
                object_id=object_id,
                size=len(data),
            )
        for base in secret_bases(data, object_id):
            repository.consume_work()
            candidate = dict(base)
            candidate["path"] = path
            candidate["history_only"] = False
            _record_candidate(candidates, indexed_candidates, candidate, repository)
        for base in dependency_bases(data, object_id, path):
            repository.consume_work()
            candidate = dict(base)
            candidate["path"] = path
            candidate["history_only"] = False
            _record_candidate(candidates, indexed_candidates, candidate, repository)

    try:
        history = repository.history_snapshot(start_refs, max_blob_bytes=max_blob_bytes)
    except GitBudgetExceeded as error:
        _budget_gap(result, str(error))
        history = None
    except GitCommandError:
        _append_gap(
            result,
            path=None,
            object_id=None,
            evidence="reachable Git history could not be read",
        )
        history = None

    if history is not None:
        coverage["unique_blobs"] = len(history.blobs)
        blobs_by_id = {blob.object_id: blob for blob in history.blobs}
        for gap in history.gaps:
            repository.consume_work()
            blob = blobs_by_id.get(gap.object_id or "")
            path_set: set[str] = set()
            if blob is not None:
                for location in blob.locations:
                    repository.consume_work()
                    if location.path:
                        path_set.add(location.path)
            paths: list[str | None] = sorted(path_set)
            if not paths:
                paths = [None]
            for path in paths:
                repository.consume_work()
                _append_gap(
                    result,
                    path=path,
                    object_id=gap.object_id,
                    size=gap.size,
                    evidence=gap.evidence,
                )

        for blob in history.blobs:
            repository.consume_work()
            data = blob.data
            if data is None:
                continue
            repository.consume_work(retained_bytes=len(data))
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                for location in blob.locations:
                    repository.consume_work()
                    _append_non_text(
                        non_text_blobs,
                        non_text_seen,
                        path=location.path,
                        object_id=blob.object_id,
                        size=blob.size,
                    )

            secret_candidates = secret_bases(data, blob.object_id)
            for location in blob.locations:
                repository.consume_work()
                if (
                    location.path is not None
                    and location.path not in current_object_ids
                ):
                    for candidate in classify_path(location.path, "history"):
                        repository.consume_work()
                        candidate["object_id"] = blob.object_id
                        candidate["history_only"] = True
                        if location.commit is not None:
                            candidate["commit"] = location.commit
                        if location.ref is not None:
                            candidate["ref"] = location.ref
                        _record_candidate(
                            candidates, indexed_candidates, candidate, repository
                        )
                for base in secret_candidates:
                    repository.consume_work()
                    candidate = dict(base)
                    if location.path is not None:
                        candidate["path"] = location.path
                        candidate["history_only"] = (
                            current_object_ids.get(location.path) != blob.object_id
                        )
                    else:
                        candidate["history_only"] = True
                    if location.commit is not None:
                        candidate["commit"] = location.commit
                    if location.ref is not None:
                        candidate["ref"] = location.ref
                    _record_candidate(candidates, indexed_candidates, candidate, repository)
                if location.path is None:
                    continue
                for base in dependency_bases(data, blob.object_id, location.path):
                    repository.consume_work()
                    candidate = dict(base)
                    candidate["path"] = location.path
                    candidate["history_only"] = (
                        current_object_ids.get(location.path) != blob.object_id
                    )
                    if location.commit is not None:
                        candidate["commit"] = location.commit
                    if location.ref is not None:
                        candidate["ref"] = location.ref
                    _record_candidate(candidates, indexed_candidates, candidate, repository)

    try:
        end_inventory = repository.status_entries()
        end_refs = repository.ref_snapshot()
        if end_inventory != inventory or end_refs != start_refs:
            _append_gap(
                result,
                path=None,
                object_id=None,
                evidence="repository inventory or local refs changed during audit",
            )
    except GitBudgetExceeded as error:
        _budget_gap(result, str(error))
    except GitCommandError:
        _append_gap(
            result,
            path=None,
            object_id=None,
            evidence="final repository mutation check could not be completed",
        )
    return _redact_result(result)


def scan_repository(
    root: Path,
    *,
    max_blob_bytes: int = 8_388_608,
    timeout_seconds: int = 30,
    deadline: float | None = None,
    max_git_commands: int = 64,
    max_total_bytes: int = 268_435_456,
    max_work_units: int = 1_000_000,
    max_locations: int = 250_000,
) -> dict[str, object]:
    result = _empty_result()
    try:
        return _scan_repository(
            root,
            max_blob_bytes=max_blob_bytes,
            timeout_seconds=timeout_seconds,
            deadline=deadline,
            max_git_commands=max_git_commands,
            max_total_bytes=max_total_bytes,
            max_work_units=max_work_units,
            max_locations=max_locations,
            result=result,
        )
    except GitBudgetExceeded as error:
        _budget_gap(result, str(error))
        return _redact_result(result)
