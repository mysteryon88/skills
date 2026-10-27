from __future__ import annotations

import os
import stat
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath

from .errors import PathSafetyError

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _validate_component(component: str) -> str:
    if component in {"", ".", ".."}:
        raise PathSafetyError("empty, dot, and parent path components are forbidden")
    if component != unicodedata.normalize("NFC", component):
        raise PathSafetyError(f"path component must use NFC Unicode normalization: {component!r}")
    if component.endswith((" ", ".")):
        raise PathSafetyError(f"path component has a Windows-unsafe trailing character: {component!r}")
    stem = component.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise PathSafetyError(f"Windows-reserved path component is forbidden: {component!r}")
    if any(ord(ch) < 32 or ch in '<>:"|?*' for ch in component):
        raise PathSafetyError(f"path component contains unsupported characters: {component!r}")
    return component


def relative_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PathSafetyError("path must be a non-empty string without NUL bytes")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise PathSafetyError(f"absolute or drive-qualified paths are forbidden: {value!r}")
    if "\\" in value:
        raise PathSafetyError("paths must use forward slashes")
    parts = tuple(_validate_component(part) for part in value.split("/"))
    if PurePosixPath(*parts).as_posix() != value:
        raise PathSafetyError(f"path is not canonical: {value!r}")
    return parts


def assert_no_case_collisions(values: list[str] | tuple[str, ...], *, label: str = "paths") -> None:
    seen: dict[str, str] = {}
    for value in values:
        folded = unicodedata.normalize("NFC", value).casefold()
        previous = seen.get(folded)
        if previous is not None and previous != value:
            raise PathSafetyError(f"case-insensitive collision in {label}: {previous!r} vs {value!r}")
        seen[folded] = value


def _assert_not_symlink(path: Path) -> None:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode):
        raise PathSafetyError(f"symlink paths are forbidden: {path}")


def confined_path(root: Path, value: str, *, must_exist: bool, require_file: bool = False) -> Path:
    root = Path(root)
    try:
        mode = root.lstat().st_mode
    except OSError as exc:
        raise PathSafetyError(f"root is unavailable: {root}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise PathSafetyError(f"root must be a regular non-symlink directory: {root}")
    root_resolved = root.resolve(strict=True)
    parts = relative_parts(value)

    current = root_resolved
    for part in parts:
        current = current / part
        _assert_not_symlink(current)

    candidate = root_resolved.joinpath(*parts)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathSafetyError(f"path escapes root: {value!r}") from exc

    if must_exist:
        try:
            candidate_mode = candidate.lstat().st_mode
        except OSError as exc:
            raise PathSafetyError(f"required path does not exist: {value!r}") from exc
        if stat.S_ISLNK(candidate_mode):
            raise PathSafetyError(f"symlink paths are forbidden: {value!r}")
        if require_file and not stat.S_ISREG(candidate_mode):
            raise PathSafetyError(f"path must be a regular file: {value!r}")
    return resolved


def relative_posix(path: Path, root: Path) -> str:
    root_resolved = Path(root).resolve(strict=True)
    resolved = Path(path).resolve(strict=False)
    try:
        relative = resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathSafetyError(f"path is outside root: {path}") from exc
    value = PurePosixPath(*relative.parts).as_posix()
    relative_parts(value)
    return value
