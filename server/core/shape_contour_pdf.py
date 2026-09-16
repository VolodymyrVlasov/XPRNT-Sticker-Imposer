"""Vector contour-only PDF for shaped stickers, for re-creating a cut file in
third-party cutting/plotting software from an already-produced layout.

Includes the same corner registration marks as the rectangular flow's template
PDF (shared via server/core/marks.py) plus the actual extracted cut contour —
real stroked bezier curves, not flattened — tiled across every grid cell, in
the same magenta cut-line convention server/core/cut_contour_pdf.py uses.

Rotation: when a cell's orientation doesn't match the artwork's natural
orientation, the contour is translated to center on the cell (offset
cell_w/2 - dim_w/2, cell_h/2 - dim_h/2 — dim_w/dim_h are the UNSWAPPED, raw
tile dimensions) and then rotated 90 degrees about the cell's own center —
this is the same construction the frontend preview (stage 2) and the raster
print PDF (server/core/shape_print_pdf.py) both use, so all three outputs
always agree.
"""

from reportlab.lib.colors import CMYKColor
from reportlab.pdfgen import canvas

from server.core.layout import Grid
from server.core.marks import draw_registration_marks
from server.core.shape_inspect import ContourSubpath
from server.utils.constants import K100, MM

CUT_COLOR = CMYKColor(0, 1, 0, 0)  # 100% magenta — same convention as cut_contour_pdf.py
LINE_WIDTH_MM = 0.1


def _rotated_cell_point(
    x: float, y: float, cell_x: float, cell_y: float,
    cell_w: float, cell_h: float, dim_w: float, dim_h: float,
) -> tuple[float, float]:
    """Map a native tile-local point (0..dim_w, 0..dim_h) to an absolute sheet-mm
    point, rotating 90 degrees about the cell's own center (mm, top-left origin,
    Y growing downward — same convention as the SVG preview's rotate(90 cx cy)).
    """
    ox = cell_w / 2 - dim_w / 2
    oy = cell_h / 2 - dim_h / 2
    tx, ty = x + ox, y + oy
    cx, cy = cell_w / 2, cell_h / 2
    rx = cx - (ty - cy)
    ry = cy + (tx - cx)
    return cell_x + rx, cell_y + ry


def generate_shape_contour_pdf(
    output_path: str,
    grid: Grid,
    subpaths: list[ContourSubpath],
    dim_w: float,
    dim_h: float,
) -> None:
    sheet_w, sheet_h = grid.sheet_w, grid.sheet_h
    pw, ph = sheet_w * MM, sheet_h * MM
    c = canvas.Canvas(output_path, pagesize=(pw, ph))

    def pt(v: float) -> float:
        return v * MM

    c.setFillColor(K100)
    c.setStrokeColor(K100)
    draw_registration_marks(c, grid)

    c.setStrokeColor(CUT_COLOR)
    c.setLineWidth(LINE_WIDTH_MM * MM)

    cell_is_landscape = grid.cell_w >= grid.cell_h
    art_is_landscape = dim_w >= dim_h
    rotate = cell_is_landscape != art_is_landscape

    def cell_point(x: float, y: float, cell_x: float, cell_y: float) -> tuple[float, float]:
        if rotate:
            return _rotated_cell_point(x, y, cell_x, cell_y, grid.cell_w, grid.cell_h, dim_w, dim_h)
        return cell_x + x, cell_y + y

    stride_x = grid.cell_w + grid.gap
    stride_y = grid.cell_h + grid.gap

    for row in range(grid.rows):
        for col in range(grid.cols):
            cell_x = grid.grid_x + col * stride_x
            cell_y = grid.grid_y + row * stride_y

            for sp in subpaths:
                path = c.beginPath()
                sx, sy = cell_point(sp.start[0], sp.start[1], cell_x, cell_y)
                path.moveTo(pt(sx), pt(sheet_h - sy))
                for seg in sp.segments:
                    if seg.kind == "C":
                        x1, y1, x2, y2, x3, y3 = seg.points
                        p1x, p1y = cell_point(x1, y1, cell_x, cell_y)
                        p2x, p2y = cell_point(x2, y2, cell_x, cell_y)
                        p3x, p3y = cell_point(x3, y3, cell_x, cell_y)
                        path.curveTo(
                            pt(p1x), pt(sheet_h - p1y),
                            pt(p2x), pt(sheet_h - p2y),
                            pt(p3x), pt(sheet_h - p3y),
                        )
                    else:
                        ex, ey = cell_point(seg.points[0], seg.points[1], cell_x, cell_y)
                        path.lineTo(pt(ex), pt(sheet_h - ey))
                if sp.closed:
                    path.close()
                c.drawPath(path, stroke=1, fill=0)

    c.save()
