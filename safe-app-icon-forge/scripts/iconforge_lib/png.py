from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass
from typing import Iterable

from .errors import PngError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_DIMENSION = 8192
_MAX_PIXELS = 16_777_216
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_COMPRESSED_BYTES = 64 * 1024 * 1024
_MAX_CHUNKS = 100_000


@dataclass(frozen=True, slots=True)
class PngInfo:
    width: int
    height: int
    bit_depth: int
    color_type: int
    rgba: bytes
    has_visible_pixels: bool
    has_transparent_pixels: bool
    alpha_bbox: tuple[int, int, int, int]
    safe_margin: tuple[int, int, int, int]
    corner_alphas: tuple[int, int, int, int]
    visual_weight: float
    optical_center: tuple[float, float]


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _paeth(left: int, up: int, upper_left: int) -> int:
    prediction = left + up - upper_left
    distance_left = abs(prediction - left)
    distance_up = abs(prediction - up)
    distance_upper_left = abs(prediction - upper_left)
    if distance_left <= distance_up and distance_left <= distance_upper_left:
        return left
    if distance_up <= distance_upper_left:
        return up
    return upper_left


def _decode_scanlines(filtered: bytes, width: int, height: int) -> bytes:
    stride = width * 4
    expected = height * (stride + 1)
    if len(filtered) != expected:
        raise PngError(f"decoded PNG byte count is {len(filtered)}, expected {expected}")
    output = bytearray(height * stride)
    source_offset = 0
    for row_index in range(height):
        filter_type = filtered[source_offset]
        source_offset += 1
        if filter_type > 4:
            raise PngError(f"unsupported PNG filter type {filter_type}")
        row_start = row_index * stride
        previous_start = row_start - stride
        if filter_type == 0:
            output[row_start : row_start + stride] = filtered[source_offset : source_offset + stride]
            source_offset += stride
            continue
        for column in range(stride):
            raw = filtered[source_offset + column]
            left = output[row_start + column - 4] if column >= 4 else 0
            up = output[previous_start + column] if row_index else 0
            upper_left = output[previous_start + column - 4] if row_index and column >= 4 else 0
            if filter_type == 1:
                value = raw + left
            elif filter_type == 2:
                value = raw + up
            elif filter_type == 3:
                value = raw + ((left + up) // 2)
            else:
                value = raw + _paeth(left, up, upper_left)
            output[row_start + column] = value & 0xFF
        source_offset += stride
    return bytes(output)


def _bounded_decompress(chunks: Iterable[bytes], expected: int) -> bytes:
    """Decode exactly *expected* bytes without ever materializing more.

    ``zlib.decompressobj.flush()`` is deliberately not used: its length argument
    is a buffer hint, not a trustworthy hard cap across Python/zlib versions.
    """

    if expected < 0 or expected > _MAX_PIXELS * 4 + _MAX_DIMENSION:
        raise PngError("PNG decoded size is outside the supported range")
    decompressor = zlib.decompressobj()
    output = bytearray()
    remaining = expected
    total_input = 0
    try:
        for chunk in chunks:
            total_input += len(chunk)
            if total_input > _MAX_COMPRESSED_BYTES:
                raise PngError("PNG compressed stream exceeds its size limit")
            pending = chunk
            while pending:
                before_len = len(pending)
                produced = decompressor.decompress(pending, remaining + 1)
                if len(produced) > remaining:
                    raise PngError("PNG decompressed stream exceeds the expected size")
                output.extend(produced)
                remaining -= len(produced)
                if decompressor.unused_data:
                    raise PngError("PNG zlib stream contains trailing compressed data")
                next_pending = decompressor.unconsumed_tail
                if next_pending and len(next_pending) == before_len and not produced:
                    raise PngError("PNG zlib decoder made no progress")
                pending = next_pending
                if remaining == 0 and pending:
                    probe = decompressor.decompress(pending, 1)
                    if probe or decompressor.unconsumed_tail:
                        raise PngError("PNG decompressed stream exceeds the expected size")
                    pending = b""
        if not decompressor.eof:
            produced = decompressor.decompress(b"", remaining + 1)
            if len(produced) > remaining:
                raise PngError("PNG decompressed stream exceeds the expected size")
            output.extend(produced)
            remaining -= len(produced)
        if not decompressor.eof:
            raise PngError("PNG zlib stream is truncated")
        if decompressor.unused_data or decompressor.unconsumed_tail:
            raise PngError("PNG zlib stream contains trailing or unconsumed data")
    except zlib.error as exc:
        raise PngError(f"invalid PNG zlib stream: {exc}") from exc
    if remaining != 0 or len(output) != expected:
        raise PngError(f"PNG decompressed stream has {len(output)} bytes, expected {expected}")
    return bytes(output)


def _metrics(rgba: bytes, width: int, height: int) -> tuple[
    tuple[int, int, int, int], tuple[int, int, int, int], tuple[int, int, int, int], float, tuple[float, float]
]:
    min_x, min_y = width, height
    max_x = max_y = -1
    visible = 0
    alpha_sum = 0
    weighted_x = 0
    weighted_y = 0
    for y in range(height):
        for x in range(width):
            alpha = rgba[(y * width + x) * 4 + 3]
            if alpha:
                visible += 1
                alpha_sum += alpha
                weighted_x += x * alpha
                weighted_y += y * alpha
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < 0:
        raise PngError("PNG is completely transparent")
    bbox = (min_x, min_y, max_x, max_y)
    margins = (min_x, min_y, width - 1 - max_x, height - 1 - max_y)
    corner_indices = (3, (width - 1) * 4 + 3, ((height - 1) * width) * 4 + 3, (width * height - 1) * 4 + 3)
    corners = tuple(rgba[index] for index in corner_indices)
    weight = visible / (width * height)
    center = (weighted_x / alpha_sum, weighted_y / alpha_sum)
    return bbox, margins, corners, weight, center


def inspect_png(
    data: bytes,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
    require_transparency: bool = False,
    require_transparent_corners: bool = False,
    minimum_safe_margin: int = 0,
    analyze_metrics: bool = True,
) -> PngInfo:
    if not isinstance(data, bytes):
        raise PngError("PNG input must be bytes")
    if len(data) > _MAX_FILE_BYTES:
        raise PngError("PNG file exceeds its size limit")
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    saw_iend = False
    total_idat = 0
    while offset < len(data):
        if len(chunks) >= _MAX_CHUNKS:
            raise PngError("PNG contains too many chunks")
        if len(data) - offset < 12:
            raise PngError("truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        if length > _MAX_COMPRESSED_BYTES:
            raise PngError("PNG chunk is unreasonably large")
        if len(data) - offset < 4 + length + 4:
            raise PngError("truncated PNG chunk payload")
        kind = data[offset : offset + 4]
        offset += 4
        payload = data[offset : offset + length]
        offset += length
        stored_crc = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != stored_crc:
            raise PngError(f"CRC mismatch in {kind!r} chunk")
        if not all(65 <= byte <= 90 or 97 <= byte <= 122 for byte in kind):
            raise PngError("invalid PNG chunk type")
        if kind == b"IDAT":
            total_idat += len(payload)
            if total_idat > _MAX_COMPRESSED_BYTES:
                raise PngError("PNG compressed stream exceeds its size limit")
        chunks.append((kind, payload))
        if kind == b"IEND":
            saw_iend = True
            break

    if not saw_iend:
        raise PngError("PNG has no IEND chunk")
    if offset != len(data):
        raise PngError("PNG contains trailing bytes after IEND")
    if not chunks or chunks[0][0] != b"IHDR":
        raise PngError("IHDR must be the first PNG chunk")
    if sum(kind == b"IHDR" for kind, _ in chunks) != 1:
        raise PngError("PNG must contain exactly one IHDR chunk")
    if chunks[-1] != (b"IEND", b""):
        raise PngError("IEND must be the final empty PNG chunk")

    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        raise PngError("invalid IHDR length")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", ihdr)
    if width == 0 or height == 0 or width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise PngError("PNG dimensions are outside the supported range")
    pixels = width * height
    if pixels > _MAX_PIXELS:
        raise PngError("PNG pixel count is outside the supported range")
    if expected_width is not None and width != expected_width:
        raise PngError(f"PNG width is {width}, expected {expected_width}")
    if expected_height is not None and height != expected_height:
        raise PngError(f"PNG height is {height}, expected {expected_height}")
    if bit_depth != 8 or color_type != 6:
        raise PngError("PNG must use 8-bit RGBA pixels")
    if (compression, filter_method, interlace) != (0, 0, 0):
        raise PngError("PNG must use standard compression/filtering and be non-interlaced")

    known_critical = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
    for kind, _payload in chunks:
        if 65 <= kind[0] <= 90 and kind not in known_critical:
            raise PngError(f"unsupported critical PNG chunk {kind.decode('ascii', 'replace')}")
    if any(kind == b"PLTE" for kind, _ in chunks):
        raise PngError("PLTE is not valid in the accepted RGBA profile")
    idat_indices = [index for index, (kind, _) in enumerate(chunks) if kind == b"IDAT"]
    if not idat_indices:
        raise PngError("PNG has no IDAT data")
    if idat_indices != list(range(idat_indices[0], idat_indices[-1] + 1)):
        raise PngError("PNG IDAT chunks must be consecutive")

    expected_decoded = height * (width * 4 + 1)
    filtered = _bounded_decompress((chunks[index][1] for index in idat_indices), expected_decoded)
    rgba = _decode_scanlines(filtered, width, height)
    if not isinstance(analyze_metrics, bool):
        raise PngError("analyze_metrics must be a boolean")
    if isinstance(minimum_safe_margin, bool) or not isinstance(minimum_safe_margin, int) or minimum_safe_margin < 0:
        raise PngError("minimum_safe_margin must be a non-negative integer")
    if not analyze_metrics:
        if require_transparency or require_transparent_corners or minimum_safe_margin:
            raise PngError("alpha requirements need analyze_metrics=True")
        corner_indices = (3, (width - 1) * 4 + 3, ((height - 1) * width) * 4 + 3, (width * height - 1) * 4 + 3)
        corners = tuple(rgba[index] for index in corner_indices)
        return PngInfo(
            width=width, height=height, bit_depth=bit_depth, color_type=color_type, rgba=rgba,
            has_visible_pixels=True, has_transparent_pixels=False,
            alpha_bbox=(0, 0, width - 1, height - 1), safe_margin=(0, 0, 0, 0),
            corner_alphas=corners, visual_weight=0.0,
            optical_center=((width - 1) / 2, (height - 1) / 2),
        )

    has_transparent = any(alpha != 255 for alpha in rgba[3::4])
    if require_transparency and not has_transparent:
        raise PngError("PNG has no transparent pixel")
    bbox, margins, corners, weight, center = _metrics(rgba, width, height)
    if require_transparent_corners and any(corners):
        raise PngError("PNG corners must be fully transparent")
    if min(margins) < minimum_safe_margin:
        raise PngError(f"PNG alpha bounds violate the {minimum_safe_margin}px safe margin")
    if not math.isfinite(weight) or not all(math.isfinite(value) for value in center):
        raise PngError("PNG metrics are not finite")

    return PngInfo(
        width=width,
        height=height,
        bit_depth=bit_depth,
        color_type=color_type,
        rgba=rgba,
        has_visible_pixels=True,
        has_transparent_pixels=has_transparent,
        alpha_bbox=bbox,
        safe_margin=margins,
        corner_alphas=corners,
        visual_weight=weight,
        optical_center=center,
    )


def encode_rgba_png(width: int, height: int, rgba: bytes) -> bytes:
    if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int):
        raise PngError("PNG dimensions must be integers")
    if width <= 0 or height <= 0 or width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise PngError("PNG dimensions are outside the supported range")
    if width * height > _MAX_PIXELS:
        raise PngError("PNG pixel count is outside the supported range")
    if len(rgba) != width * height * 4:
        raise PngError("RGBA byte count does not match PNG dimensions")
    rows = bytearray()
    stride = width * 4
    for row in range(height):
        rows.append(0)
        start = row * stride
        rows.extend(rgba[start : start + stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"sRGB", b"\x00") + _chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + _chunk(b"IEND", b"")


def normalize_png_with_info(
    data: bytes,
    *,
    expected_width: int,
    expected_height: int,
    require_transparency: bool,
    require_transparent_corners: bool = False,
    minimum_safe_margin: int = 0,
    analyze_metrics: bool = True,
) -> tuple[bytes, PngInfo]:
    """Return canonical PNG bytes plus metrics from the exact decoded pixels.

    The untrusted renderer output is fully decoded and measured once. The local
    canonical encoder preserves those RGBA pixels exactly, so a second expensive
    metric pass would be redundant. We still parse the encoded result without
    metric analysis to prove that the canonical bytes are structurally valid.
    """

    info = inspect_png(
        data,
        expected_width=expected_width,
        expected_height=expected_height,
        require_transparency=require_transparency,
        require_transparent_corners=require_transparent_corners,
        minimum_safe_margin=minimum_safe_margin,
        analyze_metrics=analyze_metrics,
    )
    normalized = encode_rgba_png(info.width, info.height, info.rgba)
    inspect_png(
        normalized,
        expected_width=expected_width,
        expected_height=expected_height,
        require_transparency=False,
        require_transparent_corners=False,
        minimum_safe_margin=0,
        analyze_metrics=False,
    )
    return normalized, info


def normalize_png(
    data: bytes,
    *,
    expected_width: int,
    expected_height: int,
    require_transparency: bool,
    require_transparent_corners: bool = False,
    minimum_safe_margin: int = 0,
    analyze_metrics: bool = True,
) -> bytes:
    normalized, _info = normalize_png_with_info(
        data,
        expected_width=expected_width,
        expected_height=expected_height,
        require_transparency=require_transparency,
        require_transparent_corners=require_transparent_corners,
        minimum_safe_margin=minimum_safe_margin,
        analyze_metrics=analyze_metrics,
    )
    return normalized
