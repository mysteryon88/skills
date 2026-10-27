from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, TypeVar

from .errors import JsonSecurityError

TError = TypeVar("TError", bound=Exception)


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise JsonSecurityError("JSON object keys must be strings")
        if key in result:
            raise JsonSecurityError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def canonical_json_bytes(value: Any, *, pretty: bool = True) -> bytes:
    if pretty:
        text = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
            allow_nan=False,
        )
    else:
        text = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return (text + "\n").encode("utf-8")


def _read_regular_nofollow(path: Path, *, maximum: int, label: str) -> bytes:
    path = Path(path)
    try:
        initial = path.lstat()
    except OSError as exc:
        raise JsonSecurityError(f"{label} is unavailable: {path}") from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise JsonSecurityError(f"{label} must be a regular non-symlink file")
    if initial.st_size < 1 or initial.st_size > maximum:
        raise JsonSecurityError(f"{label} must be between 1 and {maximum} bytes")

    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise JsonSecurityError(f"cannot open {label} safely: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise JsonSecurityError(f"{label} changed or exceeds its size limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise JsonSecurityError(f"{label} exceeds its size limit")
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or total != after.st_size
        ):
            raise JsonSecurityError(f"{label} changed while it was being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def loads_strict(data: bytes, *, label: str = "JSON") -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsonSecurityError(f"{label} must be UTF-8") from exc
    if text.startswith("\ufeff"):
        raise JsonSecurityError(f"{label} must not contain a UTF-8 BOM")
    try:
        return json.loads(text, object_pairs_hook=reject_duplicate_keys, parse_constant=_reject_constant)
    except JsonSecurityError:
        raise
    except json.JSONDecodeError as exc:
        raise JsonSecurityError(f"invalid {label}: {exc}") from exc


def _reject_constant(value: str) -> None:
    raise JsonSecurityError(f"non-finite JSON number is forbidden: {value}")


def load_json_file(path: Path, *, maximum: int, label: str) -> tuple[Any, bytes]:
    raw = _read_regular_nofollow(path, maximum=maximum, label=label)
    return loads_strict(raw, label=label), raw


def require_canonical_json(data: bytes, value: Any, *, label: str) -> None:
    if data != canonical_json_bytes(value):
        raise JsonSecurityError(f"{label} is not canonical JSON")


def translate_json_error(exc: JsonSecurityError, error_type: Callable[[str], TError]) -> TError:
    return error_type(str(exc))
