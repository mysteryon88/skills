from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from typing import Mapping

from .errors import PngError, VerificationError
from .png import PngInfo, inspect_png

_REQUIRED_ORDER = (16, 20, 24, 32, 40, 48, 64, 128, 256)


@dataclass(frozen=True, slots=True)
class ReviewSheet:
    data: bytes
    width: int
    height: int
    embedded_sizes: tuple[int, ...]


def _image(payload: str, x: float, y: float, width: float, height: float, label: str, *, pixelated: bool = False) -> str:
    render = ' image-rendering="pixelated"' if pixelated else ""
    escaped = html.escape(label, quote=True)
    return (
        f'<image x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" '
        f'preserveAspectRatio="xMidYMid meet" aria-label="{escaped}"{render} '
        f'href="{payload}"/>'
    )


def _text(x: float, y: float, value: str, *, size: int = 18, fill: str = "#142039", weight: int = 600) -> str:
    return (
        f'<text x="{x:g}" y="{y:g}" font-family="DejaVu Sans, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}">{html.escape(value)}</text>'
    )


def _overlay(info: PngInfo, *, x: float, y: float, scale: float, safe_margin: int) -> list[str]:
    x0, y0, x1, y1 = info.alpha_bbox
    cx, cy = info.optical_center
    return [
        f'<rect x="{x + x0 * scale:g}" y="{y + y0 * scale:g}" '
        f'width="{(x1 - x0 + 1) * scale:g}" height="{(y1 - y0 + 1) * scale:g}" '
        f'fill="none" stroke="#FF3864" stroke-width="1"/>',
        f'<rect x="{x + safe_margin * scale:g}" y="{y + safe_margin * scale:g}" '
        f'width="{max(0, info.width - 2 * safe_margin) * scale:g}" '
        f'height="{max(0, info.height - 2 * safe_margin) * scale:g}" fill="none" '
        f'stroke="#00A67E" stroke-width="1" stroke-dasharray="4 3"/>',
        f'<path d="M{x + cx * scale - 5:g} {y + cy * scale:g}H{x + cx * scale + 5:g} '
        f'M{x + cx * scale:g} {y + cy * scale - 5:g}V{y + cy * scale + 5:g}" '
        f'stroke="#FFB000" stroke-width="1.5"/>',
    ]


def build_review_svg(
    name: str,
    pngs: Mapping[int, bytes],
    routing: Mapping[int, str],
    *,
    safe_margin_by_size: Mapping[int, int] | None = None,
    prevalidated_infos: Mapping[int, PngInfo] | None = None,
) -> ReviewSheet:
    if not isinstance(name, str) or not name:
        raise VerificationError("review sheet name must be a non-empty string")
    if tuple(size for size in _REQUIRED_ORDER if size in pngs) != _REQUIRED_ORDER:
        raise VerificationError(f"review sheet requires exact sizes {list(_REQUIRED_ORDER)}")
    if set(routing) < set(_REQUIRED_ORDER) or any(routing[size] not in {"small", "large"} for size in _REQUIRED_ORDER):
        raise VerificationError("review sheet routing is incomplete")
    margins = {} if safe_margin_by_size is None else dict(safe_margin_by_size)

    payloads: dict[int, str] = {}
    infos: dict[int, PngInfo] = {}
    supplied_infos = None if prevalidated_infos is None else dict(prevalidated_infos)
    if supplied_infos is not None and set(supplied_infos) < set(_REQUIRED_ORDER):
        raise VerificationError("prevalidated review PNG metrics are incomplete")
    for size in _REQUIRED_ORDER:
        try:
            if supplied_infos is None:
                info = inspect_png(
                    pngs[size], expected_width=size, expected_height=size, require_transparency=True
                )
            else:
                info = supplied_infos[size]
                if not isinstance(info, PngInfo) or info.width != size or info.height != size:
                    raise VerificationError(f"prevalidated {size}px PNG metrics are invalid")
        except (KeyError, PngError) as exc:
            raise VerificationError(f"invalid {size}px PNG for review sheet: {exc}") from exc
        payloads[size] = "data:image/png;base64," + base64.b64encode(pngs[size]).decode("ascii")
        infos[size] = info

    width = 2240
    height = 2140
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<title>{html.escape(name)} icon review sheet</title>',
        '<desc>Actual-size light, dark, neutral, taskbar, pixel, alpha-bound, safe-margin, optical-center, and visual-weight review.</desc>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#E9EDF4"/>',
        _text(64, 58, name.upper().replace("-", " "), size=30, weight=700),
        _text(64, 86, "Pink = alpha bounds · green = safe margin · amber = optical center", size=15, fill="#526178"),
        '<rect x="48" y="104" width="2144" height="52" rx="14" fill="#FFF1D6" stroke="#E58B00" stroke-width="2"/>',
        _text(74, 138, "REVIEW AT 100% / 1:1 — DO NOT FIT THE SHEET TO THE WINDOW", size=20, fill="#7A4300", weight=700),
    ]

    backgrounds = [
        ("LIGHT ACTUAL SIZE", "#FFFFFF", "#C8D0DE", "#142039"),
        ("DARK ACTUAL SIZE", "#101725", "#293348", "#DFE7F5"),
        ("NEUTRAL ACTUAL SIZE", "#8A909A", "#6F7680", "#FFFFFF"),
    ]
    panel_y = 172
    for title, background, border, text_fill in backgrounds:
        parts.append(f'<rect x="48" y="{panel_y}" width="2144" height="340" rx="26" fill="{background}" stroke="{border}" stroke-width="2"/>')
        parts.append(_text(78, panel_y + 38, title, size=18, fill=text_fill, weight=700))
        x = 76
        for size in _REQUIRED_ORDER:
            cell_w = 224
            icon_x = x + (cell_w - size) / 2
            icon_y = panel_y + 70 + (210 - size) / 2
            cell_fill = "#F7F8FB" if background == "#FFFFFF" else ("#171F30" if background == "#101725" else "#989EA7")
            parts.append(f'<rect x="{x}" y="{panel_y + 58}" width="{cell_w}" height="238" rx="16" fill="{cell_fill}" stroke="{border}"/>')
            parts.append(_image(payloads[size], icon_x, icon_y, size, size, f"{size}px {title.lower()}"))
            parts.extend(_overlay(infos[size], x=icon_x, y=icon_y, scale=1, safe_margin=margins.get(size, 0)))
            parts.append(_text(x + 12, panel_y + 322, f"{size}px · {routing[size]}", size=14, fill=text_fill, weight=600))
            x += 234
        panel_y += 360

    pixel_y = panel_y + 2
    parts.append(f'<rect x="48" y="{pixel_y}" width="2144" height="390" rx="26" fill="#FFFFFF" stroke="#C8D0DE" stroke-width="2"/>')
    parts.append(_text(78, pixel_y + 38, "PIXEL REVIEW — NEAREST-NEIGHBOUR ENLARGEMENT", size=18, fill="#43506A", weight=700))
    x = 78
    for size in (16, 20, 24, 32, 40, 48):
        target = 256
        scale = target / size
        parts.append(f'<rect x="{x}" y="{pixel_y + 58}" width="322" height="294" rx="16" fill="#F1F3F7" stroke="#D5DCE8"/>')
        parts.append(_image(payloads[size], x + 33, pixel_y + 74, target, target, f"{size}px enlarged", pixelated=True))
        parts.extend(_overlay(infos[size], x=x + 33, y=pixel_y + 74, scale=scale, safe_margin=margins.get(size, 0)))
        parts.append(_text(x + 14, pixel_y + 376, f"{size}px × {scale:g} · {routing[size]}", size=14, fill="#59667F"))
        x += 344

    task_y = pixel_y + 410
    parts.append(f'<rect x="48" y="{task_y}" width="2144" height="226" rx="26" fill="#FFFFFF" stroke="#C8D0DE" stroke-width="2"/>')
    parts.append(_text(78, task_y + 38, "TASKBAR SIMULATION", size=18, fill="#43506A", weight=700))
    parts.append(f'<rect x="78" y="{task_y + 62}" width="1010" height="120" rx="14" fill="#172033"/>')
    parts.append(f'<rect x="1120" y="{task_y + 62}" width="1040" height="120" rx="14" fill="#F5F7FA" stroke="#D3DAE6"/>')
    for index, size in enumerate((16, 20, 24, 32, 40, 48)):
        x_dark = 120 + index * 150
        x_light = 1160 + index * 150
        y = task_y + 122 - size / 2
        parts.append(_image(payloads[size], x_dark, y, size, size, f"{size}px dark taskbar"))
        parts.append(_image(payloads[size], x_light, y, size, size, f"{size}px light taskbar"))
        parts.append(_text(x_dark - 2, task_y + 208, f"{size} {routing[size][0].upper()}", size=12, fill="#DFE7F5"))
        parts.append(_text(x_light - 2, task_y + 208, f"{size} {routing[size][0].upper()}", size=12, fill="#43506A"))

    metrics_y = task_y + 246
    parts.append(f'<rect x="48" y="{metrics_y}" width="2144" height="160" rx="26" fill="#FFFFFF" stroke="#C8D0DE" stroke-width="2"/>')
    parts.append(_text(78, metrics_y + 38, "TECHNICAL VISUAL METRICS", size=18, fill="#43506A", weight=700))
    x = 78
    for size in _REQUIRED_ORDER:
        info = infos[size]
        center_delta = ((info.optical_center[0] - (size - 1) / 2) ** 2 + (info.optical_center[1] - (size - 1) / 2) ** 2) ** 0.5
        parts.append(_text(x, metrics_y + 76, f"{size}px ({routing[size]})", size=14, fill="#142039", weight=700))
        parts.append(_text(x, metrics_y + 100, f"weight {info.visual_weight:.3f}", size=13, fill="#59667F"))
        parts.append(_text(x, metrics_y + 123, f"center Δ {center_delta:.2f}px", size=13, fill="#59667F"))
        parts.append(_text(x, metrics_y + 146, f"margin {min(info.safe_margin)}px", size=13, fill="#59667F"))
        x += 232

    parts.append("</svg>")
    return ReviewSheet(("\n".join(parts) + "\n").encode("utf-8"), width, height, _REQUIRED_ORDER)
