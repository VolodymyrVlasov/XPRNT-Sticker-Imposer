from reportlab.pdfgen import canvas

from server.core.layout import Grid
from server.core.marks import draw_registration_marks
from server.utils.constants import K100, MM


def generate_template_pdf(output_path: str, grid: Grid, title: str) -> None:
    """Imposition template PDF: registration marks, title, and an invisible sticker grid."""
    sheet_w, sheet_h = grid.sheet_w, grid.sheet_h
    pw = sheet_w * MM
    ph = sheet_h * MM
    c = canvas.Canvas(output_path, pagesize=(pw, ph))
    c.setFillColor(K100)
    c.setStrokeColor(K100)

    def pt(v: float) -> float:
        return v * MM

    draw_registration_marks(c, grid)

    font_pt = 12.0
    c.setFont("Helvetica", font_pt)
    tw = c.stringWidth(title, "Helvetica", font_pt)
    base_rl = pt(sheet_h - (grid.mark_offset + 0.5))
    tx = (pw - tw) / 2.0
    c.drawString(tx, base_rl, title)

    gap = pt(3.0)
    tri = font_pt

    def draw_tri(xl: float) -> None:
        p = c.beginPath()
        p.moveTo(xl,           base_rl)
        p.lineTo(xl + tri,     base_rl)
        p.lineTo(xl + tri / 2, base_rl + tri)
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    draw_tri(tx - gap - tri)
    draw_tri(tx + tw + gap)

    stride_x = grid.cell_w + grid.gap
    stride_y = grid.cell_h + grid.gap
    for col in range(grid.cols):
        for row in range(grid.rows):
            cell_x = grid.grid_x + col * stride_x
            cell_top = grid.grid_y + row * stride_y
            c.rect(
                pt(cell_x),
                pt(sheet_h - cell_top - grid.cell_h),
                pt(grid.cell_w), pt(grid.cell_h),
                fill=0, stroke=0,
            )

    c.save()
