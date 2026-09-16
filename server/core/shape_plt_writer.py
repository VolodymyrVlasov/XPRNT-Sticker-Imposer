"""HPGL (.plt) cut file for shaped stickers: the actual extracted cut contour,
including bezier curves adaptively flattened to short line segments (HPGL only
supports straight moves), cut once per grid cell.

Reuses server/core/plt_writer.py's HPGL unit-conversion pattern (hx/hy helpers,
IN;FSIZE... header, U/D command style) as a reference for the output format,
but is written fresh here — that file is not imported/modified. Unlike the
rectangular flow's overshoot-on-straight-cuts technique (grid lines / cell
rectangles), an organic closed contour just closes back on its own start point,
so there's no overshoot handling here.

Rotation: same translate-to-cell-center-then-rotate-90 construction as
server/core/shape_contour_pdf.py and the frontend preview, so the print PDF,
contour PDF, and this PLT file always agree on where the cut line actually is.
"""

import math

from server.core.layout import Grid
from server.core.shape_inspect import ContourSubpath

# Flatten cubic beziers until control points are within this many mm of the
# chord — small curves stay lightly segmented, large ones stay smooth.
FLATTEN_TOL_MM = 0.12
_MAX_DEPTH = 24

Point = tuple[float, float]


def _dist_point_to_segment(p: Point, a: Point, b: Point) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _flatten_cubic(p0: Point, p1: Point, p2: Point, p3: Point, tol: float, depth: int = 0) -> list[Point]:
    """Adaptive De Casteljau subdivision. Returns points along the curve
    EXCLUDING p0 (the caller already has it as the current point), INCLUDING p3.
    """
    flat = (
        _dist_point_to_segment(p1, p0, p3) <= tol
        and _dist_point_to_segment(p2, p0, p3) <= tol
    )
    if flat or depth >= _MAX_DEPTH:
        return [p3]

    p01, p12, p23 = _mid(p0, p1), _mid(p1, p2), _mid(p2, p3)
    p012, p123 = _mid(p01, p12), _mid(p12, p23)
    p0123 = _mid(p012, p123)
    left = _flatten_cubic(p0, p01, p012, p0123, tol, depth + 1)
    right = _flatten_cubic(p0123, p123, p23, p3, tol, depth + 1)
    return left + right


def _flatten_subpath(sp: ContourSubpath, tol: float) -> list[Point]:
    """The subpath as a polyline, one point per output vertex, starting AFTER
    sp.start (the caller already has that as the pen-up move target).
    """
    pts: list[Point] = []
    cur: Point = sp.start
    for seg in sp.segments:
        if seg.kind == "C":
            x1, y1, x2, y2, x3, y3 = seg.points
            pts.extend(_flatten_cubic(cur, (x1, y1), (x2, y2), (x3, y3), tol))
            cur = (x3, y3)
        else:
            cur = (seg.points[0], seg.points[1])
            pts.append(cur)
    return pts


def _rotated_cell_point(
    x: float, y: float, cell_x: float, cell_y: float,
    cell_w: float, cell_h: float, dim_w: float, dim_h: float,
) -> Point:
    ox = cell_w / 2 - dim_w / 2
    oy = cell_h / 2 - dim_h / 2
    tx, ty = x + ox, y + oy
    cx, cy = cell_w / 2, cell_h / 2
    rx = cx - (ty - cy)
    ry = cy + (tx - cx)
    return cell_x + rx, cell_y + ry


def generate_shape_plt(
    output_path: str,
    grid: Grid,
    subpaths: list[ContourSubpath],
    dim_w: float,
    dim_h: float,
) -> None:
    mo = grid.mark_offset
    fx = round((grid.sheet_h - 2 * mo) * 40)   # FSIZE X — along feed direction
    fy = round((grid.sheet_w - 2 * mo) * 40)   # FSIZE Y — across feed direction
    out = f"IN;FSIZE{fx},{fy} BD:103,0;TB26,{fx},{fy};CT1;"

    def hx(pdf_y: float) -> int:    # HPGL X (along feed) <- PDF Y
        return round((pdf_y - mo) * 40)

    def hy(pdf_x: float) -> int:    # HPGL Y (across feed) <- PDF X
        return round((pdf_x - mo) * 40)

    cell_is_landscape = grid.cell_w >= grid.cell_h
    art_is_landscape = dim_w >= dim_h
    rotate = cell_is_landscape != art_is_landscape

    def cell_point(x: float, y: float, cell_x: float, cell_y: float) -> Point:
        if rotate:
            return _rotated_cell_point(x, y, cell_x, cell_y, grid.cell_w, grid.cell_h, dim_w, dim_h)
        return cell_x + x, cell_y + y

    # Flatten each subpath's curves once, in native tile-local coordinates —
    # a pure rotation+translation is applied per cell afterward, so flatness
    # tolerance (an isometry) stays exactly what it was computed for.
    flattened = [(sp, _flatten_subpath(sp, FLATTEN_TOL_MM)) for sp in subpaths]

    stride_x = grid.cell_w + grid.gap
    stride_y = grid.cell_h + grid.gap

    for row in range(grid.rows):
        for col in range(grid.cols):
            cell_x = grid.grid_x + col * stride_x
            cell_y = grid.grid_y + row * stride_y

            for sp, poly in flattened:
                if not poly:
                    continue
                sx, sy = cell_point(sp.start[0], sp.start[1], cell_x, cell_y)
                out += f"U{hx(sy)},{hy(sx)} "
                for px, py in poly:
                    ax, ay = cell_point(px, py, cell_x, cell_y)
                    out += f"D{hx(ay)},{hy(ax)} "
                if sp.closed:
                    out += f"D{hx(sy)},{hy(sx)} "

    out += "U0,0;!PG;!PG;"
    with open(output_path, "w", encoding="ascii") as f:
        f.write(out)
