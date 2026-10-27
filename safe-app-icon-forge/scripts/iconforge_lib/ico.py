from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Mapping

from .errors import IcoError, PngError
from .png import inspect_png


@dataclass(frozen=True, slots=True)
class IcoFrame:
    width: int
    height: int
    payload: bytes
    offset: int
    bytes_in_res: int


@dataclass(frozen=True, slots=True)
class IcoInfo:
    sizes: tuple[int, ...]
    frames: dict[int, IcoFrame]


def _encoded_dimension(size: int) -> int:
    return 0 if size == 256 else size


def build_ico(frames: Mapping[int, bytes]) -> bytes:
    """Build a canonical ICO containing one exact PNG payload per size."""

    if not frames:
        raise IcoError("ICO requires at least one frame")
    if len(frames) > 256:
        raise IcoError("ICO has too many frames")

    ordered: list[tuple[int, bytes]] = []
    for size in sorted(frames):
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 256:
            raise IcoError(f"unsupported ICO frame size: {size!r}")
        payload = frames[size]
        if not isinstance(payload, bytes):
            raise IcoError(f"ICO frame {size} payload must be bytes")
        try:
            inspect_png(
                payload,
                expected_width=size,
                expected_height=size,
                require_transparency=True,
            )
        except PngError as exc:
            raise IcoError(f"invalid PNG payload for {size}px ICO frame: {exc}") from exc
        ordered.append((size, payload))

    header = struct.pack("<HHH", 0, 1, len(ordered))
    payload_offset = 6 + 16 * len(ordered)
    directory = bytearray()
    payloads = bytearray()
    for size, payload in ordered:
        directory.extend(
            struct.pack(
                "<BBBBHHII",
                _encoded_dimension(size),
                _encoded_dimension(size),
                0,
                0,
                1,
                32,
                len(payload),
                payload_offset,
            )
        )
        payloads.extend(payload)
        payload_offset += len(payload)

    result = header + bytes(directory) + bytes(payloads)
    inspected = inspect_ico(result)
    if inspected.sizes != tuple(size for size, _ in ordered):
        raise IcoError("internal ICO validation produced a different frame set")
    for size, payload in ordered:
        if inspected.frames[size].payload != payload:
            raise IcoError(f"internal ICO validation changed the {size}px frame")
    return result


def inspect_ico(data: bytes) -> IcoInfo:
    """Validate the canonical PNG-backed ICO profile emitted by this tool."""

    if not isinstance(data, bytes):
        raise IcoError("ICO input must be bytes")
    if len(data) < 6:
        raise IcoError("truncated ICO header")
    reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
    if (reserved, icon_type) != (0, 1):
        raise IcoError("invalid ICO header")
    if count == 0 or count > 256:
        raise IcoError("ICO frame count is outside the supported range")

    directory_end = 6 + 16 * count
    if directory_end > len(data):
        raise IcoError("truncated ICO directory")

    entries: list[tuple[int, int, int, int]] = []
    seen_sizes: set[int] = set()
    for index in range(count):
        entry_offset = 6 + 16 * index
        (
            width_byte,
            height_byte,
            color_count,
            entry_reserved,
            planes,
            bit_count,
            bytes_in_res,
            image_offset,
        ) = struct.unpack_from("<BBBBHHII", data, entry_offset)
        width = 256 if width_byte == 0 else width_byte
        height = 256 if height_byte == 0 else height_byte
        if width != height:
            raise IcoError(f"ICO frame {index} is not square")
        if width in seen_sizes:
            raise IcoError(f"duplicate ICO frame size {width}")
        seen_sizes.add(width)
        if color_count != 0 or entry_reserved != 0 or planes != 1 or bit_count != 32:
            raise IcoError(f"ICO frame {width}px has non-canonical directory fields")
        if bytes_in_res == 0:
            raise IcoError(f"ICO frame {width}px has an empty payload")
        if image_offset < directory_end:
            raise IcoError(f"ICO frame {width}px overlaps the directory")
        end = image_offset + bytes_in_res
        if end < image_offset or end > len(data):
            raise IcoError(f"ICO frame {width}px payload is out of bounds")
        entries.append((width, image_offset, bytes_in_res, end))

    sizes = tuple(width for width, _, _, _ in entries)
    if sizes != tuple(sorted(sizes)):
        raise IcoError("ICO directory frames must be sorted by size")

    expected_offset = directory_end
    frames: dict[int, IcoFrame] = {}
    for width, image_offset, bytes_in_res, end in entries:
        if image_offset != expected_offset:
            raise IcoError("ICO payloads must be contiguous and non-overlapping")
        payload = data[image_offset:end]
        try:
            png_info = inspect_png(
                payload,
                expected_width=width,
                expected_height=width,
                require_transparency=True,
            )
        except PngError as exc:
            raise IcoError(f"ICO frame {width}px is not the expected RGBA PNG: {exc}") from exc
        frames[width] = IcoFrame(
            width=png_info.width,
            height=png_info.height,
            payload=payload,
            offset=image_offset,
            bytes_in_res=bytes_in_res,
        )
        expected_offset = end
    if expected_offset != len(data):
        raise IcoError("ICO contains trailing or unreferenced bytes")

    return IcoInfo(sizes=sizes, frames=frames)
