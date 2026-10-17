"""Small dependency-free HTML/SVG helpers for the steering workbench."""
from __future__ import annotations

import html
import math
from typing import Any, Iterable, List, Mapping, Sequence


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    return ("%." + str(digits) + "f") % number


def signed(value: Any, digits: int = 4) -> str:
    text = fmt(value, digits)
    if text == "—":
        return text
    return ("+" if float(value) >= 0 else "") + text


def _color_for(value: float, limit: float) -> str:
    if limit <= 0:
        return "rgb(248,250,252)"
    t = max(-1.0, min(1.0, value / limit))
    if t < 0:
        return "rgb(%d,%d,%d)" % (248 + int((251 - 248) * -t), 250 + int((113 - 250) * -t), 252 + int((133 - 252) * -t))
    return "rgb(%d,%d,%d)" % (248 + int((96 - 248) * t), 250 + int((165 - 250) * t), 252 + int((250 - 252) * t))


def svg_line(
    series: Sequence[Mapping[str, Any]],
    width: int = 620,
    height: int = 240,
    y_label: str = "",
    x_labels: Sequence[str] = (),
    y_min: float | None = None,
    y_max: float | None = None,
) -> str:
    values: List[float] = []
    for item in series:
        values.extend(float(point[1]) for point in item["points"])
    if not values:
        return "<svg></svg>"
    low = min(values) if y_min is None else y_min
    high = max(values) if y_max is None else y_max
    if high == low:
        high = low + 1.0
    left, top, right, bottom = 58, 22, 18, 42
    def x(index: int, count: int) -> float:
        return left + (index / max(count - 1, 1)) * (width - left - right)
    def y(value: float) -> float:
        return top + (high - value) / (high - low) * (height - top - bottom)
    parts = ['<svg viewBox="0 0 %d %d" role="img">' % (width, height)]
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#0b1220"/>' % (width, height))
    if low < 0 < high:
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#334155" stroke-dasharray="4 3"/>' % (left, y(0), width - right, y(0)))
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#334155"/>' % (left, top, left, height - bottom))
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#334155"/>' % (left, height - bottom, width - right, height - bottom))
    for index, label in enumerate(x_labels):
        if len(x_labels) <= 1 or index % max(1, len(x_labels) // 6) != 0:
            continue
        xx = x(index, len(x_labels))
        parts.append('<text x="%.1f" y="%d" fill="#64748b" font-size="10" text-anchor="middle">%s</text>' % (xx, height - 18, esc(label)))
    for item in series:
        points = item["points"]
        path = " ".join(("M" if index == 0 else "L") + "%.2f,%.2f" % (x(index, len(points)), y(float(point[1]))) for index, point in enumerate(points))
        parts.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.2"/>' % (path, item.get("color", "#60a5fa")))
        for index, point in enumerate(points):
            parts.append('<circle cx="%.2f" cy="%.2f" r="2.2" fill="%s"/>' % (x(index, len(points)), y(float(point[1])), item.get("color", "#60a5fa")))
    parts.append('<text x="8" y="%d" fill="#94a3b8" font-size="10">%s</text>' % (top + 4, esc(y_label)))
    for index, item in enumerate(series):
        parts.append('<text x="%d" y="%d" fill="%s" font-size="10">%s</text>' % (width - 110, top + 14 + index * 14, item.get("color", "#60a5fa"), esc(item.get("name", ""))))
    parts.append("</svg>")
    return "".join(parts)


def svg_bars(
    items: Sequence[Mapping[str, Any]],
    width: int = 620,
    height: int = 240,
    y_label: str = "",
    y_min: float | None = None,
    y_max: float | None = None,
) -> str:
    values = [float(item["value"]) for item in items]
    low = min(values + [0.0]) if y_min is None else y_min
    high = max(values + [0.0]) if y_max is None else y_max
    if high == low:
        high = low + 1.0
    left, top, right, bottom = 58, 22, 18, 52
    def y(value: float) -> float:
        return top + (high - value) / (high - low) * (height - top - bottom)
    parts = ['<svg viewBox="0 0 %d %d" role="img">' % (width, height)]
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#0b1220"/>' % (width, height))
    parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#334155"/>' % (left, y(0), width - right, y(0)))
    slots = (width - left - right) / max(len(items), 1)
    for index, item in enumerate(items):
        xx = left + index * slots + slots * 0.18
        ww = slots * 0.64
        yy = y(float(item["value"]))
        parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (xx, min(yy, y(0)), ww, abs(y(0) - yy), item.get("color", "#60a5fa")))
        parts.append('<text x="%.1f" y="%d" fill="#94a3b8" font-size="9" text-anchor="middle">%s</text>' % (xx + ww / 2, height - 18, esc(item.get("label", ""))))
    parts.append('<text x="8" y="%d" fill="#94a3b8" font-size="10">%s</text>' % (top + 4, esc(y_label)))
    parts.append("</svg>")
    return "".join(parts)


def svg_scatter(
    points: Sequence[Mapping[str, Any]],
    width: int = 620,
    height: int = 260,
    x_label: str = "",
    y_label: str = "",
    log_x: bool = True,
) -> str:
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    if not xs:
        return "<svg></svg>"
    if log_x:
        xs = [math.log10(max(value, 1e-9)) for value in xs]
    low_x, high_x = min(xs), max(xs)
    low_y, high_y = min(ys), max(ys)
    if high_x == low_x:
        high_x = low_x + 1.0
    if high_y == low_y:
        high_y = low_y + 1.0
    left, top, right, bottom = 58, 22, 18, 42
    def x(value: float) -> float:
        return left + (value - low_x) / (high_x - low_x) * (width - left - right)
    def y(value: float) -> float:
        return top + (high_y - value) / (high_y - low_y) * (height - top - bottom)
    parts = ['<svg viewBox="0 0 %d %d" role="img">' % (width, height)]
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#0b1220"/>' % (width, height))
    parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#334155"/>' % (left, y(0), width - right, y(0)))
    for point, xx, yy in zip(points, xs, ys):
        parts.append('<circle cx="%.1f" cy="%.1f" r="2.4" fill="%s" opacity="0.6"/>' % (x(xx), y(yy), point.get("color", "#fb7185")))
    parts.append('<text x="%d" y="%d" fill="#94a3b8" font-size="10" text-anchor="middle">%s</text>' % (width // 2, height - 8, esc(x_label)))
    parts.append('<text x="8" y="%d" fill="#94a3b8" font-size="10">%s</text>' % (top + 4, esc(y_label)))
    parts.append("</svg>")
    return "".join(parts)


def svg_heatmap(
    matrix: Sequence[Sequence[float]],
    marker_columns: Sequence[int] = (),
    width: int = 900,
    height: int = 360,
    limit: float = 0.3,
) -> str:
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    if rows == 0 or cols == 0:
        return "<svg></svg>"
    left, top, right, bottom = 34, 10, 10, 28
    cell_w = (width - left - right) / cols
    cell_h = (height - top - bottom) / rows
    parts = ['<svg viewBox="0 0 %d %d" role="img">' % (width, height)]
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#0b1220"/>' % (width, height))
    for row in range(rows):
        if row % 4 != 0:
            continue
        parts.append('<text x="%d" y="%.1f" fill="#64748b" font-size="9" text-anchor="end">%d</text>' % (left - 4, top + row * cell_h + cell_h * 0.8, row))
    for row in range(rows):
        values = matrix[row]
        for col in range(cols):
            parts.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (
                left + col * cell_w, top + row * cell_h, cell_w + 0.4, cell_h + 0.4, _color_for(float(values[col]), limit)))
    for col in marker_columns:
        if 0 <= col < cols:
            parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#f8fafc" stroke-width="0.7" opacity="0.7"/>' % (
                left + col * cell_w, top, left + col * cell_w, top + rows * cell_h))
    parts.append('<text x="%d" y="%d" fill="#64748b" font-size="9">layers 0-%d; white ticks = marker next-token</text>' % (left, height - 8, rows - 1))
    parts.append("</svg>")
    return "".join(parts)
