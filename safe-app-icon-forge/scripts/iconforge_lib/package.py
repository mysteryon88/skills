from __future__ import annotations

import contextlib
import io
import os
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Iterable, Iterator

from .errors import VerificationError
from .paths import confined_path

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class ZipLimits:
    max_archive_bytes: int = 128 * 1024 * 1024
    max_members: int = 512
    max_member_bytes: int = 64 * 1024 * 1024
    max_total_uncompressed: int = 128 * 1024 * 1024
    max_compression_ratio: float = 250.0
    max_name_bytes: int = 1024


@dataclass(frozen=True, slots=True)
class ZipInventory:
    names: tuple[str, ...]
    infos: dict[str, zipfile.ZipInfo]
    total_uncompressed: int


DEFAULT_ZIP_LIMITS = ZipLimits()


def validate_archive_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise VerificationError("ZIP member name must be a non-empty string")
    if len(name.encode("utf-8")) > DEFAULT_ZIP_LIMITS.max_name_bytes:
        raise VerificationError("ZIP member name is too long")
    if name != unicodedata.normalize("NFC", name):
        raise VerificationError(f"ZIP member name must use NFC Unicode normalization: {name!r}")
    if "\\" in name:
        raise VerificationError("ZIP member names must use forward slashes")
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).is_absolute() or PureWindowsPath(name).drive:
        raise VerificationError(f"absolute or drive-qualified ZIP member name is forbidden: {name!r}")
    parts = name.split("/")
    if any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts):
        raise VerificationError(f"non-canonical ZIP member name is forbidden: {name!r}")
    canonical = PurePosixPath(*parts).as_posix()
    if canonical != name:
        raise VerificationError(f"non-canonical ZIP member name is forbidden: {name!r}")
    return canonical


def _regular_mode(info: zipfile.ZipInfo) -> bool:
    file_type = (info.external_attr >> 16) & 0o170000
    return file_type in {0, stat.S_IFREG}


def preflight_zip(
    archive: zipfile.ZipFile,
    *,
    limits: ZipLimits = DEFAULT_ZIP_LIMITS,
    canonical: bool,
    expected_names: tuple[str, ...] | None = None,
) -> ZipInventory:
    if archive.comment:
        raise VerificationError("ZIP archive comment must be empty")
    infos = archive.infolist()
    if not infos:
        raise VerificationError("ZIP archive is empty")
    if len(infos) > limits.max_members:
        raise VerificationError("ZIP archive contains too many members")

    names: list[str] = []
    by_name: dict[str, zipfile.ZipInfo] = {}
    folded: dict[str, str] = {}
    total = 0
    for info in infos:
        raw_name = getattr(info, "orig_filename", info.filename)
        name = validate_archive_name(raw_name)
        if name != info.filename:
            raise VerificationError(f"ZIP member name was normalized by the runtime: {raw_name!r}")
        if name in by_name:
            raise VerificationError(f"ZIP contains duplicate member name: {name}")
        fold = unicodedata.normalize("NFC", name).casefold()
        previous = folded.get(fold)
        if previous is not None and previous != name:
            raise VerificationError(f"ZIP contains a case-insensitive name collision: {previous!r} vs {name!r}")
        folded[fold] = name
        if info.is_dir() or name.endswith("/"):
            raise VerificationError(f"ZIP must not contain directory members: {name}")
        if info.flag_bits & 0x1:
            raise VerificationError(f"encrypted ZIP member is forbidden: {name}")
        if not _regular_mode(info):
            raise VerificationError(f"ZIP member is not a regular file: {name}")
        if info.file_size < 0 or info.compress_size < 0:
            raise VerificationError(f"ZIP member has invalid size metadata: {name}")
        if info.file_size > limits.max_member_bytes:
            raise VerificationError(f"ZIP member exceeds the uncompressed size limit before read: {name}")
        if info.compress_size == 0:
            if info.file_size != 0:
                raise VerificationError(f"ZIP member has an impossible compression size: {name}")
        elif info.file_size / info.compress_size > limits.max_compression_ratio:
            raise VerificationError(f"ZIP member compression ratio exceeds the limit before read: {name}")
        total += info.file_size
        if total > limits.max_total_uncompressed:
            raise VerificationError("ZIP cumulative uncompressed size exceeds the limit before read")
        if info.compress_type not in {zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED}:
            raise VerificationError(f"ZIP member uses unsupported compression: {name}")
        if canonical:
            if info.date_time != _FIXED_ZIP_TIME:
                raise VerificationError(f"ZIP member has a non-deterministic timestamp: {name}")
            if ((info.external_attr >> 16) & 0o777) != 0o644:
                raise VerificationError(f"ZIP member permissions are not 0644: {name}")
            if info.compress_type != zipfile.ZIP_DEFLATED:
                raise VerificationError(f"ZIP member compression is not canonical: {name}")
        names.append(name)
        by_name[name] = info

    names_tuple = tuple(names)
    if expected_names is not None and names_tuple != expected_names:
        raise VerificationError("ZIP member set or ordering does not match the expected exact list")
    return ZipInventory(names_tuple, by_name, total)


def read_zip_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    maximum: int | None = None,
    chunk_size: int = 64 * 1024,
) -> bytes:
    cap = DEFAULT_ZIP_LIMITS.max_member_bytes if maximum is None else maximum
    if info.file_size > cap:
        raise VerificationError(f"ZIP member exceeds its read limit before payload access: {info.filename}")
    result = bytearray()
    total = 0
    try:
        with archive.open(info, mode="r") as stream:
            while True:
                chunk = stream.read(min(chunk_size, cap + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > cap or total > info.file_size:
                    raise VerificationError(f"ZIP member exceeded its declared or configured size: {info.filename}")
                result.extend(chunk)
    except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise VerificationError(f"cannot read ZIP member {info.filename}: {exc}") from exc
    if total != info.file_size:
        raise VerificationError(f"ZIP member length differs from central-directory metadata: {info.filename}")
    return bytes(result)


@contextlib.contextmanager
def open_safe_zip(
    source: Path | bytes,
    *,
    limits: ZipLimits = DEFAULT_ZIP_LIMITS,
    canonical: bool,
    expected_names: tuple[str, ...] | None = None,
) -> Iterator[tuple[zipfile.ZipFile, ZipInventory]]:
    file_object: BinaryIO | io.BytesIO
    descriptor: int | None = None
    if isinstance(source, bytes):
        if len(source) > limits.max_archive_bytes:
            raise VerificationError("ZIP archive exceeds its compressed size limit")
        file_object = io.BytesIO(source)
    else:
        path = Path(source)
        try:
            initial = path.lstat()
        except OSError as exc:
            raise VerificationError(f"ZIP archive is unavailable: {path}") from exc
        if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
            raise VerificationError("ZIP archive must be a regular non-symlink file")
        if initial.st_size > limits.max_archive_bytes:
            raise VerificationError("ZIP archive exceeds its compressed size limit")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise VerificationError(f"cannot open ZIP archive safely: {path}") from exc
        after_open = os.fstat(descriptor)
        if not stat.S_ISREG(after_open.st_mode) or after_open.st_size != initial.st_size:
            os.close(descriptor)
            raise VerificationError("ZIP archive changed before it was opened")
        file_object = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = None
    try:
        with file_object:
            try:
                with zipfile.ZipFile(file_object, mode="r") as archive:
                    inventory = preflight_zip(
                        archive,
                        limits=limits,
                        canonical=canonical,
                        expected_names=expected_names,
                    )
                    yield archive, inventory
            except zipfile.BadZipFile as exc:
                raise VerificationError(f"invalid ZIP archive: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_regular_member(path: Path, *, maximum: int) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VerificationError(f"cannot open ZIP source member safely: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise VerificationError(f"ZIP source member is not a bounded regular file: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise VerificationError(f"ZIP source member exceeds its size limit: {path}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ) or total != after.st_size:
            raise VerificationError(f"ZIP source member changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def create_deterministic_zip(root: Path, destination: Path, members: Iterable[str]) -> bytes:
    root = Path(root)
    destination = Path(destination)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise VerificationError("ZIP source root must be an existing non-symlink directory")
    validated = [validate_archive_name(member) for member in members]
    if len(validated) != len(set(validated)):
        raise VerificationError("ZIP member list contains duplicates")
    ordered = sorted(validated)

    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
        for member in ordered:
            try:
                source = confined_path(root, member, must_exist=True, require_file=True)
            except Exception as exc:
                raise VerificationError(f"unsafe ZIP source member {member!r}: {exc}") from exc
            payload = _read_regular_member(source, maximum=DEFAULT_ZIP_LIMITS.max_member_bytes)
            size = len(payload)
            total += size
            if total > DEFAULT_ZIP_LIMITS.max_total_uncompressed:
                raise VerificationError("ZIP source members exceed the cumulative size limit")
            info = zipfile.ZipInfo(filename=member, date_time=_FIXED_ZIP_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    archive_bytes = buffer.getvalue()
    if len(archive_bytes) > DEFAULT_ZIP_LIMITS.max_archive_bytes:
        raise VerificationError("generated ZIP exceeds the compressed size limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(archive_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise VerificationError(f"refusing to overwrite existing ZIP: {destination}") from exc
    with open_safe_zip(archive_bytes, canonical=True, expected_names=tuple(ordered)):
        pass
    return archive_bytes
