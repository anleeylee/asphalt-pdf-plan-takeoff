"""Self-contained ASCII DXF parser (no external CAD dependency).

Scope (per S03): extract measurable paving geometry — closed polylines,
circles, lines — plus layers, text labels and model units. It is deliberately
not a general CAD platform.

Entity support:
  - LWPOLYLINE  (bulge arcs approximated when bulge != 0)
  - POLYLINE + VERTEX / SEQEND
  - CIRCLE
  - LINE
  - TEXT / MTEXT (labels, notes)
  - LAYER table (name + color)
  - HEADER $INSUNITS / $MEASUREMENT

Validation helpers: open-polyline detection, self-intersection detection,
duplicate-geometry detection, unit detection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .validation import require_valid_geometry

DXF_UNIT_TO_FT = {
    1: 1 / 12.0,   # inches
    2: 1.0,        # feet
    3: 3.0,        # yards
    4: 1 / 304.8,  # millimeters
    5: 1 / 30.48,  # centimeters
    6: 1 / 0.3048,  # meters
    7: 5280.0,     # miles
}


@dataclass
class DXFEntity:
    kind: str
    layer: str
    points: list[tuple[float, float]] = field(default_factory=list)  # polyline/line vertices
    closed: bool = False
    center: Optional[tuple[float, float]] = None
    radius: Optional[float] = None
    text: Optional[str] = None
    bulge: float = 0.0

    def is_closed_geometry(self) -> bool:
        if self.kind == "CIRCLE":
            return True
        return self.closed


@dataclass
class DXFDocument:
    units: Optional[str] = None          # scale: model units -> feet
    units_label: Optional[str] = None    # human label, e.g. "feet"
    layers: dict[str, int] = field(default_factory=dict)  # name -> color
    entities: list[DXFEntity] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def entities_of_layer(self, layer: str) -> list[DXFEntity]:
        return [e for e in self.entities if e.layer == layer]

    def entity_layers(self) -> list[str]:
        return sorted({e.layer for e in self.entities})


def _parse_groups(text: str) -> Iterable[tuple[int, str]]:
    lines = text.splitlines()
    i = 0
    while i + 1 < len(lines):
        try:
            code = int(lines[i].strip())
        except ValueError:
            code = -1
        value = lines[i + 1]
        yield code, value
        i += 2


def _vertices_from_groups(groups: list[tuple[int, str]], x_code=10, y_code=20) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    cur_x = None
    for code, value in groups:
        if code == x_code:
            cur_x = float(value)
        elif code == y_code and cur_x is not None:
            pts.append((cur_x, float(value)))
            cur_x = None
    return pts


def _split_entity_blocks(groups: list[tuple[int, str]]) -> list[tuple[str, list[tuple[int, str]]]]:
    """Split a group stream into (kind, block) tuples at each (0, KIND) marker."""
    blocks: list[tuple[str, list[tuple[int, str]]]] = []
    i = 0
    while i < len(groups):
        code, value = groups[i]
        if code == 0:
            kind = value.strip().upper()
            block = [(code, value)]
            i += 1
            while i < len(groups):
                c, v = groups[i]
                if c == 0:
                    break
                block.append((c, v))
                i += 1
            blocks.append((kind, block))
        else:
            i += 1
    return blocks


def parse_dxf(text: str, *, source_name: str = "<memory>") -> DXFDocument:
    doc = DXFDocument()
    groups_all = list(_parse_groups(text))
    pos = 0
    n = len(groups_all)

    def section_groups(section_name: str) -> list[tuple[int, str]]:
        nonlocal pos
        while pos < n:
            code, value = groups_all[pos]
            if code == 0 and value.strip().upper() == "SECTION":
                code2, value2 = groups_all[pos + 1] if pos + 1 < n else (0, "")
                if value2.strip().upper() == section_name:
                    start = pos + 2
                    end = start
                    while end < n:
                        c, v = groups_all[end]
                        if c == 0 and v.strip().upper() == "ENDSEC":
                            break
                        end += 1
                    pos = end + 1
                    return groups_all[start:end]
            pos += 1
        return []

    # HEADER: $INSUNITS (group 9 keyword, followed by group 70 value)
    header_pending = None
    for code, value in groups_all:
        if code == 9 and value.strip().upper() in ("$INSUNITS", "$MEASUREMENT"):
            header_pending = value.strip().upper()
        elif header_pending == "$INSUNITS" and code == 70:
            try:
                unit_code = int(value)
            except ValueError:
                unit_code = None
            if unit_code in DXF_UNIT_TO_FT:
                doc.units = DXF_UNIT_TO_FT[unit_code]
                doc.units_label = {
                    1: "inches", 2: "feet", 3: "yards", 4: "millimeters",
                    5: "centimeters", 6: "meters", 7: "miles",
                }.get(unit_code, "unitless")
            else:
                # unit code 0 = unitless, or an unsupported code: units unknown
                doc.warnings.append("model units missing/unitless; treat units as unknown")
            header_pending = None
        elif code != 9:
            header_pending = None

    # LAYER table: entries start with (0, LAYER), name at (2, ...), color at (62, ...)
    for idx in range(len(groups_all) - 1):
        code, value = groups_all[idx]
        if code == 0 and value.strip().upper() == "LAYER":
            name = None
            color = 7
            j = idx + 1
            while j < len(groups_all):
                c, v = groups_all[j]
                if c == 0 and v.strip().upper() != "LAYER":
                    break
                if c == 2 and name is None:
                    name = v
                elif c == 62:
                    try:
                        color = int(v)
                    except ValueError:
                        color = 7
                j += 1
            if name:
                doc.layers[name] = color

    # ENTITIES
    entities_groups = section_groups("ENTITIES")
    blocks = _split_entity_blocks(entities_groups)

    i = 0
    while i < len(blocks):
        kind, block = blocks[i]
        layer = "0"
        for c, v in block:
            if c == 8:
                layer = v

        if kind == "LWPOLYLINE":
            pts = _vertices_from_groups(block)
            closed = any(c == 70 and (int(v) & 1) for c, v in block)
            bulge = next((float(v) for c, v in block if c == 42), 0.0)
            doc.entities.append(DXFEntity("LWPOLYLINE", layer, pts, closed=closed, bulge=bulge))
            i += 1
        elif kind == "POLYLINE":
            closed = any(c == 70 and (int(v) & 1) for c, v in block)
            verts: list[tuple[float, float]] = []
            j = i + 1
            while j < len(blocks):
                vkind, vblock = blocks[j]
                if vkind == "VERTEX":
                    vtx = _vertices_from_groups(vblock)
                    if vtx:
                        verts.append(vtx[0])
                    j += 1
                elif vkind == "SEQEND":
                    j += 1
                    break
                else:
                    break
            doc.entities.append(DXFEntity("POLYLINE", layer, verts, closed=closed))
            i = j
        elif kind == "CIRCLE":
            center = None
            radius = None
            for c, v in block:
                if c == 10:
                    center = (float(v), 0.0)
                elif c == 20 and center:
                    center = (center[0], float(v))
                elif c == 40:
                    radius = float(v)
            if center and radius:
                doc.entities.append(DXFEntity("CIRCLE", layer, center=center, radius=radius))
            i += 1
        elif kind == "LINE":
            pts = _vertices_from_groups(block)
            if len(pts) >= 2:
                doc.entities.append(DXFEntity("LINE", layer, pts[:2]))
            i += 1
        elif kind in ("TEXT", "MTEXT"):
            text_val = None
            for c, v in block:
                if c == 1:
                    text_val = v
                elif c == 3 and text_val is None:
                    text_val = v
            doc.entities.append(DXFEntity(kind, layer, text=text_val or ""))
            i += 1
        else:
            i += 1  # unsupported entity (SPLINE, ARC, ...) skipped

    if not doc.entities and not doc.layers:
        doc.warnings.append(f"no entities parsed from {source_name}; check that the file is ASCII DXF")
    return doc


# ------------------------------------------------------------------ geometry

def polygon_area(points: list[tuple[float, float]]) -> float:
    """Shoelace formula (absolute area)."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def ccw(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    # endpoint sharing is a shared vertex, not an intersection
    for a, b in ((p1, p3), (p1, p4), (p2, p3), (p2, p4)):
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
            return False
    return False


def find_self_intersections(points: list[tuple[float, float]], closed: bool) -> list[tuple[int, int]]:
    """Return indices of intersecting non-adjacent segments (O(n^2), small sets)."""
    hits: list[tuple[int, int]] = []
    n = len(points)
    if n < 4:
        return hits
    segments = list(zip(points, points[1:] + ([points[0]] if closed else [])))
    for i in range(len(segments)):
        for j in range(i + 2, len(segments)):
            if closed and i == 0 and j == len(segments) - 1:
                continue  # closing segment shares vertices with the first
            if _segments_intersect(segments[i][0], segments[i][1], segments[j][0], segments[j][1]):
                hits.append((i, j))
    return hits


def normalize_polygon(points: list[tuple[float, float]], closed: bool) -> tuple:
    """Hashable, orientation-free representation for duplicate detection."""
    pts = list(points)
    if closed and pts and pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    return tuple(sorted((round(x, 6), round(y, 6)) for x, y in pts))


def _flatten_bulges(points, bulge) -> list[tuple[float, float]]:
    """Approximate a constant bulge by inserting a sagitta midpoint per segment."""
    out: list[tuple[float, float]] = []
    for i, p in enumerate(points):
        out.append(p)
        if i + 1 < len(points):
            p2 = points[i + 1]
            if abs(bulge) > 1e-9:
                dx, dy = p2[0] - p[0], p2[1] - p[1]
                length = math.hypot(dx, dy)
                if length > 0:
                    mid = ((p[0] + p2[0]) / 2, (p[1] + p2[1]) / 2)
                    sagitta = abs(bulge) * length / 2.0
                    nx, ny = -dy / length, dx / length
                    out.append((mid[0] + nx * sagitta, mid[1] + ny * sagitta))
    return out


def entity_area(entity: DXFEntity, scale_ft: float) -> float:
    """Area in square feet = model-unit area x scale_ft**2."""
    if entity.kind == "CIRCLE" and entity.radius is not None:
        return math.pi * entity.radius ** 2 * scale_ft * scale_ft
    pts = entity.points
    if len(pts) < 3:
        return 0.0
    if entity.bulge:
        pts = _flatten_bulges(pts, entity.bulge)
    base = polygon_area(pts)
    require_valid_geometry(base > 0, f"zero-area geometry on layer {entity.layer!r}")
    return base * scale_ft * scale_ft
