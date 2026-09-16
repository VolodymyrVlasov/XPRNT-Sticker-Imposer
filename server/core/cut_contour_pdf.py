"""Vector PDF with just the cut geometry, for re-creating a cut file in
third-party cutting/plotting software from an already-produced layout.

Includes the same corner registration marks as the template PDF (so the
operator can align this file's vector paths against the printed sheet) plus
the cut lines themselves as real stroked vector paths — drawn in a spot-like
magenta, the common "cut line" convention — rather than the PLT's plotter
commands.
"""

from reportlab.lib.colors import CMYKColor
from reportlab.pdfgen import canvas

from server.core.layout import Grid
from server.core.marks import draw_registration_marks
from server.utils.constants import K100, MM

CUT_COLOR = CMYKColor(0, 1, 0, 0)  # 100% magenta — conventional cut-line color
LINE_WIDTH_MM = 0.1


def generate_cut_contour_pdf(output_path: str, grid: Grid) -> None:
    sheet_w, sheet_h = grid.sheet_w, grid.sheet_h
    pw = sheet_w * MM
    ph = sheet_h * MM
    c = canvas.Canvas(output_path, pagesize=(pw, ph))

    def pt(v: float) -> float:
        return v * MM

    c.setFillColor(K100)
    c.setStrokeColor(K100)
    draw_registration_marks(c, grid)

    c.setStrokeColor(CUT_COLOR)
    c.setLineWidth(LINE_WIDTH_MM * MM)

    if grid.gap <= 0:
        # Contiguous grid — stickers share cut lines, so just draw the grid lines.
        h_lines = [grid.grid_y + i * grid.cell_h for i in range(grid.rows + 1)]
        v_lines = [grid.grid_x + i * grid.cell_w for i in range(grid.cols + 1)]
        x0, x1 = grid.grid_x, grid.grid_x + grid.grid_w
        for y in h_lines:
            c.line(pt(x0), pt(sheet_h - y), pt(x1), pt(sheet_h - y))
        y0, y1 = grid.grid_y, grid.grid_y + grid.grid_h
        for x in v_lines:
            c.line(pt(x), pt(sheet_h - y0), pt(x), pt(sheet_h - y1))
    else:
        # Gapped stickers — each cell is cut as its own closed rectangle.
        stride_x = grid.cell_w + grid.gap
        stride_y = grid.cell_h + grid.gap
        for row in range(grid.rows):
            for col in range(grid.cols):
                x = grid.grid_x + col * stride_x
                y = grid.grid_y + row * stride_y
                c.rect(
                    pt(x), pt(sheet_h - y - grid.cell_h),
                    pt(grid.cell_w), pt(grid.cell_h),
                    fill=0, stroke=1,
                )

    c.save()
