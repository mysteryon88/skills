#!/usr/bin/env python3
"""Recompute bundled TON ordinary-cell and addr_std representation-hash vectors."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


BOC_MAGIC = bytes.fromhex("b5ee9c72")


def _read_uint(data: bytes, offset: int, size: int, label: str) -> tuple[int, int]:
    end = offset + size
    if size < 1 or end > len(data):
        raise ValueError(f"truncated {label}")
    return int.from_bytes(data[offset:end], "big"), end


def _crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return (~crc) & 0xFFFFFFFF


def _decode_boc(value: Any, path: str) -> tuple[dict[str, Any], dict[str, bool]]:
    if not isinstance(value, str) or len(value) % 2:
        raise ValueError(f"{path}.bocHex must be even-length hexadecimal")
    try:
        data = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{path}.bocHex must be hexadecimal") from exc
    if data[:4] != BOC_MAGIC:
        raise ValueError(f"{path}.bocHex must use the b5ee9c72 BoC format")
    if len(data) < 6:
        raise ValueError(f"{path}.bocHex has a truncated header")

    offset = 4
    flags_byte = data[offset]
    offset += 1
    has_index = bool(flags_byte & 0x80)
    has_crc32 = bool(flags_byte & 0x40)
    has_cache_bits = bool(flags_byte & 0x20)
    reserved_flags = (flags_byte >> 3) & 0x03
    size_bytes = flags_byte & 0x07
    if has_cache_bits or reserved_flags:
        raise ValueError(f"{path}.bocHex uses unsupported cache or reserved flags")
    if not 1 <= size_bytes <= 4:
        raise ValueError(f"{path}.bocHex has invalid cell-index width")
    off_bytes = data[offset]
    offset += 1
    if not 1 <= off_bytes <= 8:
        raise ValueError(f"{path}.bocHex has invalid offset width")

    cells, offset = _read_uint(data, offset, size_bytes, "cell count")
    roots, offset = _read_uint(data, offset, size_bytes, "root count")
    absent, offset = _read_uint(data, offset, size_bytes, "absent-cell count")
    total_size, offset = _read_uint(data, offset, off_bytes, "cell-data size")
    if cells < 1 or roots != 1 or absent != 0:
        raise ValueError(f"{path}.bocHex must be a complete single-root BoC")
    root_indices: list[int] = []
    for _ in range(roots):
        root_index, offset = _read_uint(data, offset, size_bytes, "root index")
        root_indices.append(root_index)
    if any(index >= cells for index in root_indices):
        raise ValueError(f"{path}.bocHex has an out-of-range root index")

    declared_ends: list[int] | None = None
    if has_index:
        declared_ends = []
        for _ in range(cells):
            cell_end, offset = _read_uint(data, offset, off_bytes, "cell index")
            declared_ends.append(cell_end)
        if declared_ends != sorted(set(declared_ends)) or declared_ends[-1] != total_size:
            raise ValueError(f"{path}.bocHex has an invalid cumulative cell index")

    cell_data_end = offset + total_size
    crc_end = cell_data_end + (4 if has_crc32 else 0)
    if crc_end != len(data):
        raise ValueError(f"{path}.bocHex length does not match its header")
    if has_crc32:
        expected_crc = _crc32c(data[:cell_data_end]).to_bytes(4, "little")
        if data[cell_data_end:crc_end] != expected_crc:
            raise ValueError(f"{path}.bocHex CRC32C mismatch")

    records: list[tuple[dict[str, Any], list[int]]] = []
    actual_ends: list[int] = []
    cursor = offset
    for cell_index in range(cells):
        if cursor + 2 > cell_data_end:
            raise ValueError(f"{path}.bocHex truncates cell {cell_index}")
        descriptor_one = data[cursor]
        descriptor_two = data[cursor + 1]
        cursor += 2
        ref_count = descriptor_one & 0x07
        if ref_count > 4 or descriptor_one != ref_count:
            raise ValueError(f"{path}.bocHex must contain ordinary level-0 cells without stored hashes")
        data_bytes = (descriptor_two + 1) // 2
        if cursor + data_bytes + ref_count * size_bytes > cell_data_end:
            raise ValueError(f"{path}.bocHex truncates cell {cell_index} data or refs")
        stored = bytearray(data[cursor : cursor + data_bytes])
        cursor += data_bytes
        if descriptor_two % 2:
            if not stored or stored[-1] == 0:
                raise ValueError(f"{path}.bocHex has invalid top-up bits in cell {cell_index}")
            trailing_zeros = (stored[-1] & -stored[-1]).bit_length() - 1
            bit_length = data_bytes * 8 - trailing_zeros - 1
            stored[-1] &= ~(1 << trailing_zeros)
        else:
            bit_length = data_bytes * 8
        refs: list[int] = []
        for _ in range(ref_count):
            ref_index, cursor = _read_uint(data, cursor, size_bytes, "cell reference")
            if ref_index <= cell_index or ref_index >= cells:
                raise ValueError(f"{path}.bocHex reference order is not topological")
            refs.append(ref_index)
        records.append(({"bitsHex": bytes(stored).hex(), "bitLength": bit_length, "refs": []}, refs))
        actual_ends.append(cursor - offset)
    if cursor != cell_data_end:
        raise ValueError(f"{path}.bocHex has trailing bytes inside cell_data")
    if declared_ends is not None and declared_ends != actual_ends:
        raise ValueError(f"{path}.bocHex index does not match decoded cell boundaries")

    built: list[dict[str, Any] | None] = [None] * cells
    for index in range(cells - 1, -1, -1):
        cell, refs = records[index]
        children = [built[ref] for ref in refs]
        if any(child is None for child in children):
            raise ValueError(f"{path}.bocHex contains an unresolved reference")
        cell["refs"] = children
        built[index] = cell
    root = built[root_indices[0]]
    if root is None:
        raise ValueError(f"{path}.bocHex has no decoded root")
    return root, {"hasIndex": has_index, "hasCrc32": has_crc32}


def _pack_raw_bits(bits: str) -> tuple[bytes, int]:
    bit_length = len(bits)
    padding = (-bit_length) % 8
    padded = bits + ("0" * padding)
    return (int(padded, 2).to_bytes(len(padded) // 8, "big") if padded else b""), bit_length


def _cell_data(raw: bytes, bit_length: int) -> bytes:
    expected_bytes = (bit_length + 7) // 8
    if len(raw) != expected_bytes:
        raise ValueError(f"bitsHex must contain exactly {expected_bytes} bytes for bitLength={bit_length}")
    if bit_length == 0:
        return b""
    unused = (-bit_length) % 8
    if unused == 0:
        return raw
    if raw[-1] & ((1 << unused) - 1):
        raise ValueError("bitsHex has non-zero bits after bitLength")
    result = bytearray(raw)
    result[-1] |= 1 << (unused - 1)
    return bytes(result)


def _cell_hash(cell: Any, path: str) -> tuple[bytes, int, str]:
    if not isinstance(cell, dict):
        raise ValueError(f"{path} must be an object")
    bit_length = cell.get("bitLength")
    bits_hex = cell.get("bitsHex")
    refs = cell.get("refs")
    if not isinstance(bit_length, int) or isinstance(bit_length, bool) or not 0 <= bit_length <= 1023:
        raise ValueError(f"{path}.bitLength must be an integer in 0..1023")
    if not isinstance(bits_hex, str) or len(bits_hex) % 2:
        raise ValueError(f"{path}.bitsHex must be even-length hexadecimal")
    try:
        raw = bytes.fromhex(bits_hex)
    except ValueError as exc:
        raise ValueError(f"{path}.bitsHex must be hexadecimal") from exc
    if not isinstance(refs, list) or len(refs) > 4:
        raise ValueError(f"{path}.refs must be an array with at most four cells")
    data = _cell_data(raw, bit_length)
    children = [_cell_hash(ref, f"{path}.refs[{index}]") for index, ref in enumerate(refs)]
    descriptor_one = len(children)
    descriptor_two = (bit_length // 8) + ((bit_length + 7) // 8)
    representation = bytes((descriptor_one, descriptor_two)) + data
    representation += b"".join(depth.to_bytes(2, "big") for _, depth, _ in children)
    representation += b"".join(digest for digest, _, _ in children)
    depth = 0 if not children else max(item[1] for item in children) + 1
    return hashlib.sha256(representation).digest(), depth, data.hex()


def _address_cell(workchain: int, account_id_hex: str, anycast: str) -> dict[str, Any]:
    if anycast != "none":
        raise ValueError("only addr_std without anycast is defined by this profile")
    if not isinstance(workchain, int) or isinstance(workchain, bool) or not -128 <= workchain <= 127:
        raise ValueError("addr_std workchain must be a signed int8")
    try:
        account = bytes.fromhex(account_id_hex)
    except (TypeError, ValueError) as exc:
        raise ValueError("accountIdHex must be 32-byte hexadecimal") from exc
    if len(account) != 32:
        raise ValueError("accountIdHex must be 32-byte hexadecimal")
    bits = "10" + "0" + format(workchain & 0xFF, "08b") + "".join(format(byte, "08b") for byte in account)
    raw, bit_length = _pack_raw_bits(bits)
    return {"bitsHex": raw.hex(), "bitLength": bit_length, "refs": []}


def _check_expected(item: dict[str, Any], digest: bytes, data_hex: str, path: str) -> list[str]:
    errors: list[str] = []
    expected = item.get("expectedRepresentationHashHex")
    if expected != digest.hex():
        errors.append(f"{path} hash mismatch: expected {expected!r}, recomputed {digest.hex()}")
    if item.get("expectedHigh128Hex") != digest[:16].hex():
        errors.append(f"{path} high128 limb mismatch")
    if item.get("expectedLow128Hex") != digest[16:].hex():
        errors.append(f"{path} low128 limb mismatch")
    declared_data = item.get("expectedCellDataWithTopUpHex")
    if declared_data is not None and declared_data != data_hex:
        errors.append(f"{path} top-up data mismatch: expected {declared_data!r}, recomputed {data_hex}")
    return errors


def verify_vectors(payload: Any) -> list[str]:
    """Return deterministic vector consistency errors without requiring a TON SDK."""

    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        return ["root schemaVersion must be integer 1"]
    errors: list[str] = []
    cell_hashes: dict[str, str] = {}

    addresses = payload.get("addressVectors")
    if not isinstance(addresses, list) or not addresses:
        errors.append("addressVectors must be a non-empty array")
    else:
        for index, item in enumerate(addresses):
            path = f"addressVectors[{index}]"
            try:
                if not isinstance(item, dict):
                    raise ValueError(f"{path} must be an object")
                cell = _address_cell(item.get("workchain"), item.get("accountIdHex"), item.get("anycast"))
                digest, _, data_hex = _cell_hash(cell, path)
                if item.get("expectedCellBitLength") != cell["bitLength"]:
                    errors.append(f"{path} expectedCellBitLength mismatch")
                errors.extend(_check_expected(item, digest, data_hex, path))
            except ValueError as exc:
                errors.append(f"{path}: {exc}")

    cells = payload.get("cellVectors")
    if not isinstance(cells, list) or not cells:
        errors.append("cellVectors must be a non-empty array")
    else:
        for index, item in enumerate(cells):
            path = f"cellVectors[{index}]"
            try:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise ValueError(f"{path} must contain a string id")
                digest, _, data_hex = _cell_hash(item.get("cell"), path)
                cell_hashes[item["id"]] = digest.hex()
                errors.extend(_check_expected(item, digest, data_hex, path))
            except ValueError as exc:
                errors.append(f"{path}: {exc}")

    transports = payload.get("transportEquivalence")
    if not isinstance(transports, list) or not transports:
        errors.append("transportEquivalence must be a non-empty array")
    else:
        for index, item in enumerate(transports):
            path = f"transportEquivalence[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{path} must be an object")
                continue
            expected = cell_hashes.get(item.get("cellVectorId"))
            if expected is None:
                errors.append(f"{path}.cellVectorId does not reference a cell vector")
            if item.get("expectedRepresentationHashHex") != expected:
                errors.append(f"{path} representation hash must equal the referenced logical cell hash")
            variants = item.get("bocVariants")
            if not isinstance(variants, list) or len(variants) < 2:
                errors.append(f"{path}.bocVariants must contain at least two serialized BoCs")
            elif len({json.dumps(value, sort_keys=True) for value in variants}) != len(variants):
                errors.append(f"{path}.bocVariants must be distinct")
            else:
                cell_vector = next(
                    (
                        value
                        for value in cells
                        if isinstance(value, dict) and value.get("id") == item.get("cellVectorId")
                    ),
                    None,
                )
                declared_cell = cell_vector.get("cell") if isinstance(cell_vector, dict) else None
                for variant_index, variant in enumerate(variants):
                    variant_path = f"{path}.bocVariants[{variant_index}]"
                    try:
                        if not isinstance(variant, dict):
                            raise ValueError(f"{variant_path} must be an object")
                        decoded_cell, flags = _decode_boc(variant.get("bocHex"), variant_path)
                        for flag_name in ("hasIndex", "hasCrc32"):
                            if variant.get(flag_name) is not flags[flag_name]:
                                errors.append(f"{variant_path}.{flag_name} does not match the serialized BoC header")
                        if decoded_cell != declared_cell:
                            errors.append(f"{variant_path} decoded cell graph does not match {item.get('cellVectorId')}")
                        digest, _, _ = _cell_hash(decoded_cell, variant_path)
                        if digest.hex() != expected:
                            errors.append(f"{variant_path} decoded representation hash mismatch")
                    except ValueError as exc:
                        errors.append(str(exc))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "vectors",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "ton-encoding-vectors.json",
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.vectors.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    errors = verify_vectors(payload)
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("TON encoding vectors verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
