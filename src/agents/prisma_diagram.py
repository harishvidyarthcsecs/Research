"""
PRISMA Flow Diagram.

Hand-rolled SVG, no charting dependency (matches the project's existing
zero-extra-dependency convention). Fixed viewBox, boxes positioned by simple
arithmetic — five stacked boxes with connecting arrows:
  Identified -> Duplicates removed -> Screened -> Excluded -> Included
"""
from ..models.data_models import PrismaCounts

_BOX_W = 320
_BOX_H = 60
_GAP = 30
_SIDE_W = 260


def render_svg(counts: PrismaCounts) -> str:
    boxes = [
        ("Identified", counts.identified),
        ("Screened", counts.screened),
        ("Included in evidence table", counts.included),
    ]
    excluded_lines = [
        f"Duplicates removed: {counts.duplicates_removed}",
        f"Excluded (no abstract): {counts.excluded_no_abstract}",
        f"Excluded (extraction failed): {counts.excluded_extraction_failed}",
    ]

    height = len(boxes) * (_BOX_H + _GAP) + _GAP
    width = _BOX_W + _GAP + _SIDE_W + 40
    cx = 20 + _BOX_W / 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="sans-serif">',
        '<style>.box{fill:#eef2ff;stroke:#4338ca;stroke-width:1.5;}'
        '.side{fill:#fef2f2;stroke:#b91c1c;stroke-width:1.5;}'
        '.label{font-size:13px;fill:#1f2937;}'
        '.count{font-size:12px;fill:#4b5563;}</style>',
    ]

    y = _GAP
    centers = []
    for title, count in boxes:
        parts.append(f'<rect class="box" x="20" y="{y}" width="{_BOX_W}" height="{_BOX_H}" rx="6"/>')
        parts.append(f'<text class="label" x="{cx}" y="{y + 24}" text-anchor="middle">{title}</text>')
        parts.append(f'<text class="count" x="{cx}" y="{y + 44}" text-anchor="middle">n = {count}</text>')
        centers.append(y + _BOX_H / 2)
        y += _BOX_H + _GAP

    for i in range(len(boxes) - 1):
        y_start = _GAP + i * (_BOX_H + _GAP) + _BOX_H
        y_end = y_start + _GAP
        parts.append(
            f'<line x1="{cx}" y1="{y_start}" x2="{cx}" y2="{y_end}" '
            f'stroke="#4338ca" stroke-width="1.5" marker-end="url(#arrow)"/>'
        )

    parts.append(
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" '
        'orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#4338ca"/></marker></defs>'
    )

    side_x = 20 + _BOX_W + _GAP
    side_y = centers[1] - _BOX_H / 2 if len(centers) > 1 else _GAP
    side_h = max(_BOX_H, 20 * len(excluded_lines) + 20)
    parts.append(f'<rect class="side" x="{side_x}" y="{side_y}" width="{_SIDE_W}" height="{side_h}" rx="6"/>')
    for i, line in enumerate(excluded_lines):
        parts.append(
            f'<text class="count" x="{side_x + 12}" y="{side_y + 20 + i * 18}">{line}</text>'
        )
    mid_y = _GAP + (_BOX_H + _GAP) + _BOX_H / 2
    parts.append(
        f'<line x1="{20 + _BOX_W}" y1="{mid_y}" x2="{side_x}" y2="{side_y + side_h / 2}" '
        f'stroke="#b91c1c" stroke-width="1.5" marker-end="url(#arrow-red)"/>'
    )
    parts.append(
        '<defs><marker id="arrow-red" markerWidth="8" markerHeight="8" refX="4" refY="4" '
        'orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#b91c1c"/></marker></defs>'
    )

    parts.append('</svg>')
    return "".join(parts)
