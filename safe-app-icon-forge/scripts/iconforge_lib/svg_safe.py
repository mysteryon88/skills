from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import SvgSecurityError

SVG_NS = "http://www.w3.org/2000/svg"
_MAX_BYTES = 1024 * 1024
_MAX_ELEMENTS = 10_000
_MAX_DEPTH = 64
_MAX_ATTRIBUTES_PER_ELEMENT = 64
_MAX_TOTAL_ATTRIBUTES = 100_000
_MAX_COORDINATE = 8192.0
_REQUIRED_VIEWBOX = (0.0, 0.0, 1024.0, 1024.0)
_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$")
_LOCAL_URL_RE = re.compile(r"^url\(\s*#([A-Za-z_][A-Za-z0-9_.:-]{0,127})\s*\)$")
_SCHEME_RE = re.compile(r"(?i)(?:https?|file|data|javascript|ftp|mailto):|//")
_PATH_RE = re.compile(r"^[0-9eE+.,\-\sMmZzLlHhVvCcSsQqTtAa]*$")
_POINTS_RE = re.compile(r"^[0-9eE+.,\-\s]*$")
_TRANSFORM_RE = re.compile(r"^[A-Za-z0-9eE+.,\-\s()]*$")
_PAINT_RE = re.compile(r"^[A-Za-z0-9#%(),.\-+\s]*$")
_NUMBER_RE = re.compile(r"^[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?%?$")
_NUMBER_TOKEN_RE = re.compile(r"[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?")

_ALLOWED_ELEMENTS = {
    "svg", "g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "title", "desc",
}
_COMMON_ATTRS = {
    "id", "fill", "fill-opacity", "fill-rule", "stroke", "stroke-opacity", "stroke-width",
    "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "opacity", "transform", "clip-path", "mask",
}
_ELEMENT_ATTRS = {
    "svg": {"viewBox", "preserveAspectRatio"},
    "g": set(),
    "defs": set(),
    "path": {"d", "pathLength"},
    "rect": {"x", "y", "width", "height", "rx", "ry", "pathLength"},
    "circle": {"cx", "cy", "r", "pathLength"},
    "ellipse": {"cx", "cy", "rx", "ry", "pathLength"},
    "line": {"x1", "y1", "x2", "y2", "pathLength"},
    "polyline": {"points", "pathLength"},
    "polygon": {"points", "pathLength"},
    "linearGradient": {"x1", "y1", "x2", "y2", "gradientUnits", "gradientTransform", "spreadMethod"},
    "radialGradient": {"cx", "cy", "r", "fx", "fy", "fr", "gradientUnits", "gradientTransform", "spreadMethod"},
    "stop": {"offset", "stop-color", "stop-opacity"},
    "clipPath": {"clipPathUnits"},
    "mask": {"x", "y", "width", "height", "maskUnits", "maskContentUnits"},
    "title": set(),
    "desc": set(),
}
_NUMERIC_ATTRS = {
    "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "fx", "fy", "fr", "x1", "y1",
    "x2", "y2", "pathLength", "offset", "fill-opacity", "stroke-opacity", "stroke-width",
    "stroke-miterlimit", "opacity", "stop-opacity",
}
_NONNEGATIVE_ATTRS = {
    "width", "height", "rx", "ry", "r", "fr", "pathLength", "stroke-width", "stroke-miterlimit",
}
_ENUMS = {
    "fill-rule": {"nonzero", "evenodd"},
    "stroke-linecap": {"butt", "round", "square"},
    "stroke-linejoin": {"miter", "miter-clip", "round", "bevel", "arcs"},
    "gradientUnits": {"objectBoundingBox", "userSpaceOnUse"},
    "spreadMethod": {"pad", "reflect", "repeat"},
    "clipPathUnits": {"userSpaceOnUse", "objectBoundingBox"},
    "maskUnits": {"userSpaceOnUse", "objectBoundingBox"},
    "maskContentUnits": {"userSpaceOnUse", "objectBoundingBox"},
}
_DRAWING_ELEMENTS = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}


@dataclass(frozen=True, slots=True)
class SanitizedSvg:
    data: bytes
    viewbox: tuple[float, float, float, float]
    sha256: str
    geometry_sha256: str
    element_count: int
    attribute_count: int

    @property
    def viewbox_width(self) -> float:
        return self.viewbox[2]

    @property
    def viewbox_height(self) -> float:
        return self.viewbox[3]


def _split_qname(name: str) -> tuple[str | None, str]:
    if name.startswith("{"):
        namespace, local = name[1:].split("}", 1)
        return namespace, local
    return None, name


def _parse_viewbox(value: str) -> tuple[float, float, float, float]:
    tokens = _NUMBER_TOKEN_RE.findall(value.replace(",", " "))
    residue = _NUMBER_TOKEN_RE.sub("", value.replace(",", " "))
    if residue.strip() or len(tokens) != 4:
        raise SvgSecurityError("viewBox must contain exactly four finite numbers")
    numbers = tuple(float(token) for token in tokens)
    if not all(math.isfinite(number) for number in numbers):
        raise SvgSecurityError("viewBox numbers must be finite")
    if numbers != _REQUIRED_VIEWBOX:
        raise SvgSecurityError("viewBox must be exactly '0 0 1024 1024'")
    return numbers


def _bounded_numbers(value: str, *, label: str) -> None:
    numbers = [float(token) for token in _NUMBER_TOKEN_RE.findall(value)]
    if any(not math.isfinite(number) or abs(number) > _MAX_COORDINATE for number in numbers):
        raise SvgSecurityError(f"{label} contains non-finite or out-of-range coordinates")


def _validate_value(attribute: str, value: str) -> str | None:
    if len(value) > (65_536 if attribute in {"d", "points"} else 4_096):
        raise SvgSecurityError(f"attribute {attribute!r} exceeds the length limit")
    if any(ord(ch) < 32 and ch not in "\t\r\n" for ch in value):
        raise SvgSecurityError(f"attribute {attribute!r} contains control characters")
    if _SCHEME_RE.search(value):
        raise SvgSecurityError(f"attribute {attribute!r} contains an external or active URL")
    if attribute.lower().startswith("on") or attribute in {"style", "class", "href"}:
        raise SvgSecurityError(f"attribute {attribute!r} is forbidden")

    if attribute in {"clip-path", "mask"}:
        match = _LOCAL_URL_RE.fullmatch(value)
        if not match:
            raise SvgSecurityError(f"{attribute} must be a same-document url(#id) reference")
        return match.group(1)
    if "url(" in value.lower():
        if attribute not in {"fill", "stroke"}:
            raise SvgSecurityError(f"URL references are forbidden in {attribute!r}")
        match = _LOCAL_URL_RE.fullmatch(value)
        if not match:
            raise SvgSecurityError("paint URLs must be same-document url(#id) references")
        return match.group(1)

    if attribute == "id":
        if not _ID_RE.fullmatch(value):
            raise SvgSecurityError("id contains unsupported characters or is too long")
    elif attribute == "d":
        if not value.strip() or not _PATH_RE.fullmatch(value):
            raise SvgSecurityError("path data contains unsupported syntax")
        _bounded_numbers(value, label="path data")
    elif attribute == "points":
        if not value.strip() or not _POINTS_RE.fullmatch(value):
            raise SvgSecurityError("points contains unsupported syntax")
        _bounded_numbers(value, label="points")
    elif attribute in {"transform", "gradientTransform"}:
        if not _TRANSFORM_RE.fullmatch(value):
            raise SvgSecurityError(f"{attribute} contains unsupported syntax")
        functions = re.findall(r"([A-Za-z]+)\s*\(", value)
        if any(name not in {"matrix", "translate", "scale", "rotate", "skewX", "skewY"} for name in functions):
            raise SvgSecurityError(f"{attribute} contains an unsupported transform function")
        _bounded_numbers(value, label=attribute)
    elif attribute in _NUMERIC_ATTRS:
        token = value.strip()
        if not _NUMBER_RE.fullmatch(token):
            raise SvgSecurityError(f"{attribute} must be one finite number, optionally a percentage")
        number = float(token.rstrip("%"))
        if not math.isfinite(number) or abs(number) > _MAX_COORDINATE:
            raise SvgSecurityError(f"{attribute} must be finite and bounded")
        if attribute in _NONNEGATIVE_ATTRS and number < 0:
            raise SvgSecurityError(f"{attribute} must not be negative")
        if attribute in {"opacity", "fill-opacity", "stroke-opacity", "stop-opacity"} and not token.endswith("%") and number > 1:
            raise SvgSecurityError(f"{attribute} must be between 0 and 1")
    elif attribute in _ENUMS:
        if value not in _ENUMS[attribute]:
            raise SvgSecurityError(f"unsupported {attribute} value: {value!r}")
    elif attribute == "preserveAspectRatio":
        if not re.fullmatch(r"(?:none|x(?:Min|Mid|Max)Y(?:Min|Mid|Max))(?:\s+(?:meet|slice))?", value):
            raise SvgSecurityError("unsupported preserveAspectRatio value")
    elif attribute in {"fill", "stroke", "stop-color"}:
        if not value or not _PAINT_RE.fullmatch(value):
            raise SvgSecurityError(f"unsupported paint value in {attribute}")
    return None


def _read_source_safely(source: Path) -> bytes:
    try:
        initial = source.lstat()
    except OSError as exc:
        raise SvgSecurityError(f"cannot inspect SVG: {source}") from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise SvgSecurityError("SVG source must be a regular non-symlink file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise SvgSecurityError(f"cannot open SVG safely: {source}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= _MAX_BYTES:
            raise SvgSecurityError(f"SVG must be between 1 byte and {_MAX_BYTES} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, _MAX_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_BYTES:
                raise SvgSecurityError(f"SVG must be between 1 byte and {_MAX_BYTES} bytes")
        after = os.fstat(descriptor)
        if (
            before.st_dev != after.st_dev or before.st_ino != after.st_ino or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns or total != after.st_size
        ):
            raise SvgSecurityError("SVG changed while it was being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _geometry_lines(root: ET.Element) -> Iterable[str]:
    for element in root.iter():
        _namespace, name = _split_qname(element.tag)
        if name in {"title", "desc"}:
            continue
        attrs = []
        for raw_name, value in sorted(element.attrib.items()):
            _attr_ns, attr_name = _split_qname(raw_name)
            if attr_name == "id":
                continue
            attrs.append(f"{attr_name}={value}")
        yield f"{name}|{'|'.join(attrs)}"


def _is_in_definitions(ancestors: tuple[str, ...]) -> bool:
    return any(name in {"defs", "clipPath", "mask"} for name in ancestors)


def sanitize_svg(source: Path) -> SanitizedSvg:
    raw = _read_source_safely(Path(source))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SvgSecurityError("SVG must be UTF-8 XML without a BOM") from exc
    if text.startswith("\ufeff"):
        raise SvgSecurityError("SVG must not contain a UTF-8 BOM")
    if re.search(r"(?is)<!\s*(?:DOCTYPE|ENTITY)\b", text):
        raise SvgSecurityError("DOCTYPE and entity declarations are forbidden")
    without_declaration = re.sub(r"^\s*<\?xml\s+[^?]*\?>", "", text, count=1, flags=re.IGNORECASE)
    if "<?" in without_declaration:
        raise SvgSecurityError("XML processing instructions are forbidden")
    if "<![CDATA[" in text:
        raise SvgSecurityError("CDATA sections are forbidden")

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SvgSecurityError(f"invalid SVG XML: {exc}") from exc
    namespace, local = _split_qname(root.tag)
    if namespace != SVG_NS or local != "svg":
        raise SvgSecurityError("root must be an SVG-namespace <svg> element")
    viewbox_value = root.attrib.get("viewBox")
    if viewbox_value is None:
        raise SvgSecurityError("root SVG must have viewBox='0 0 1024 1024'")
    viewbox = _parse_viewbox(viewbox_value)

    ids: set[str] = set()
    references: list[str] = []
    element_count = 0
    attribute_count = 0
    visible_drawing_count = 0

    def rebuild(element: ET.Element, depth: int, ancestors: tuple[str, ...]) -> ET.Element:
        nonlocal element_count, attribute_count, visible_drawing_count
        element_count += 1
        if element_count > _MAX_ELEMENTS:
            raise SvgSecurityError(f"SVG exceeds the {_MAX_ELEMENTS}-element limit")
        if depth > _MAX_DEPTH:
            raise SvgSecurityError(f"SVG exceeds the {_MAX_DEPTH}-level nesting limit")
        element_ns, element_name = _split_qname(element.tag)
        if element_ns != SVG_NS:
            raise SvgSecurityError(f"foreign namespace is forbidden on element {element_name!r}")
        if element_name not in _ALLOWED_ELEMENTS:
            raise SvgSecurityError(f"element <{element_name}> is outside the static SVG profile")
        if len(element.attrib) > _MAX_ATTRIBUTES_PER_ELEMENT:
            raise SvgSecurityError(f"element <{element_name}> has too many attributes")
        attribute_count += len(element.attrib)
        if attribute_count > _MAX_TOTAL_ATTRIBUTES:
            raise SvgSecurityError("SVG has too many attributes")

        allowed = _COMMON_ATTRS | _ELEMENT_ATTRS[element_name]
        clean_attributes: dict[str, str] = {}
        for raw_name, value in element.attrib.items():
            attr_ns, attr_name = _split_qname(raw_name)
            if attr_ns is not None:
                raise SvgSecurityError(f"namespaced attribute {raw_name!r} is forbidden")
            if attr_name not in allowed:
                raise SvgSecurityError(f"attribute {attr_name!r} is not allowed on <{element_name}>")
            reference = _validate_value(attr_name, value)
            cleaned = value.strip()
            if attr_name == "id":
                if cleaned in ids:
                    raise SvgSecurityError(f"duplicate id: {cleaned}")
                ids.add(cleaned)
            if reference:
                references.append(reference)
            clean_attributes[attr_name] = cleaned

        if element_name == "svg" and depth != 0:
            raise SvgSecurityError("nested <svg> elements are not allowed")
        if element_name == "svg" and clean_attributes.get("viewBox") != "0 0 1024 1024":
            raise SvgSecurityError("root viewBox must use canonical text '0 0 1024 1024'")
        if element_name in {"title", "desc"}:
            if list(element):
                raise SvgSecurityError(f"<{element_name}> cannot contain child elements")
            content = element.text or ""
            if len(content) > 1024 or any(ord(ch) < 32 and ch not in "\t\r\n" for ch in content):
                raise SvgSecurityError(f"<{element_name}> text is too long or contains controls")
        elif element.text and element.text.strip():
            raise SvgSecurityError(f"text content is not allowed inside <{element_name}>")
        if element.tail and element.tail.strip():
            raise SvgSecurityError("non-whitespace XML tail text is forbidden")

        if element_name in _DRAWING_ELEMENTS and not _is_in_definitions(ancestors):
            opacity = clean_attributes.get("opacity", "1")
            fill = clean_attributes.get("fill")
            stroke = clean_attributes.get("stroke")
            if opacity in {"0", "0.0", "0%"}:
                raise SvgSecurityError(f"invisible <{element_name}> object is forbidden")
            if fill == "none" and (stroke is None or stroke == "none"):
                raise SvgSecurityError(f"paintless <{element_name}> object is forbidden")
            visible_drawing_count += 1

        clean = ET.Element(f"{{{SVG_NS}}}{element_name}")
        for key in sorted(clean_attributes):
            clean.set(key, clean_attributes[key])
        if element_name in {"title", "desc"} and element.text:
            clean.text = element.text.strip()
        next_ancestors = ancestors + (element_name,)
        for child in list(element):
            clean.append(rebuild(child, depth + 1, next_ancestors))
        return clean

    clean_root = rebuild(root, 0, ())
    missing = sorted(set(references) - ids)
    if missing:
        raise SvgSecurityError(f"same-document references point to missing ids: {', '.join(missing)}")
    if visible_drawing_count == 0:
        raise SvgSecurityError("SVG contains no visible drawing elements")

    ET.register_namespace("", SVG_NS)
    serialized = ET.tostring(clean_root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)
    geometry = ("\n".join(_geometry_lines(clean_root)) + "\n").encode("utf-8")
    return SanitizedSvg(
        data=serialized,
        viewbox=viewbox,
        sha256=hashlib.sha256(serialized).hexdigest(),
        geometry_sha256=hashlib.sha256(geometry).hexdigest(),
        element_count=element_count,
        attribute_count=attribute_count,
    )


def sanitize_svg_bytes(data: bytes) -> SanitizedSvg:
    """Sanitize bounded SVG bytes through the same no-follow path implementation."""

    if not isinstance(data, bytes) or not 1 <= len(data) <= _MAX_BYTES:
        raise SvgSecurityError(f"SVG bytes must be between 1 and {_MAX_BYTES} bytes")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="iconforge-svg-bytes-") as temporary:
        path = Path(temporary) / "input.svg"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_BINARY", 0)
        )
        descriptor = os.open(path, flags, 0o600)
        try:
            offset = 0
            while offset < len(data):
                offset += os.write(descriptor, data[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return sanitize_svg(path)
