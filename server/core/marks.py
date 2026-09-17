"""Corner registration marks and the feed-direction arrow, shared by the
template PDF, the shaped-sticker print PDF, and the vector cut-contour
reference PDF — everywhere a person or a plotter aligns against the physical
printed sheet. Also the optional per-cell outline frame (see
draw_cell_outlines), drawn by the print-PDF generators only, never by the
template/contour files.
"""

from server.core.layout import Grid
from server.utils.constants import MM

# Feed-direction arrow: a solid triangle pointing toward the top sheet edge,
# centered horizontally, telling the operator which way to load the sheet
# into the plotter. Fixed size and edge offset per spec: 3x3mm, apex 5mm
# from the sheet's top edge — independent of mark_offset (previously 8x7mm,
# positioned at mark_offset + 2mm).
FEED_ARROW_WIDTH_MM = 3.0
FEED_ARROW_HEIGHT_MM = 3.0
FEED_ARROW_OFFSET_MM = 5.0  # sheet top edge -> arrow apex, fixed

# Optional black frame around every sticker cell ("Додати обводку довкола
# макету" in the UI) — a printed border the customer can opt into, distinct
# from the corner registration marks above. See draw_cell_outlines below.
OUTLINE_STROKE_WIDTH_MM = 0.1


def draw_registration_marks(c, grid: Grid) -> None:
    """Four filled L-brackets, each pointing from its sheet corner toward the
    interior, plus a feed-direction arrow centered at the top of the sheet.
    """
    sheet_w, sheet_h, mo = grid.sheet_w, grid.sheet_h, grid.mark_offset

    def pt(v: float) -> float:
        return v * MM

    def fr(x: float, y: float, w: float, h: float) -> None:
        """Filled rect. x,y = top-left origin, Y axis pointing down, all mm."""
        c.rect(pt(x), pt(sheet_h - y - h), pt(w), pt(h), fill=1, stroke=0)

    fr(mo,                  mo - 0.5,            9, 1)
    fr(mo - 0.5,            mo,                  1, 9)
    fr(sheet_w - mo - 9,    mo - 0.5,            9, 1)
    fr(sheet_w - mo - 0.5,  mo,                  1, 9)
    fr(mo,                  sheet_h - mo - 0.5,  9, 1)
    fr(mo - 0.5,            sheet_h - mo - 9,    1, 9)
    fr(sheet_w - mo - 9,    sheet_h - mo - 0.5,  9, 1)
    fr(sheet_w - mo - 0.5,  sheet_h - mo - 9,    1, 9)

    _draw_feed_arrow(c, sheet_w, sheet_h)


def _draw_feed_arrow(c, sheet_w: float, sheet_h: float) -> None:
    """Solid triangle, apex toward the top sheet edge, centered horizontally
    across the sheet width — indicates which edge to feed into the plotter
    first. Fixed 3x3mm, apex FEED_ARROW_OFFSET_MM (5mm) from the sheet's top
    edge.

    NOTE: at the default SRA3 mark_offset=9mm/field_margin=2mm this sits
    close to pdf_template.py's centered filename-caption band (that file
    draws its caption + two small triangles independently, centered the same
    way). A previous stage had to tune the old mark_offset-relative position
    to dodge exactly this collision. This new fixed position was NOT
    re-verified against that caption — do that in the smoke test below
    before considering this done.
    """
    def pt(v: float) -> float:
        return v * MM

    cx = sheet_w / 2.0
    apex_y = FEED_ARROW_OFFSET_MM
    base_y = apex_y + FEED_ARROW_HEIGHT_MM
    half_w = FEED_ARROW_WIDTH_MM / 2.0

    p = c.beginPath()
    p.moveTo(pt(cx),           pt(sheet_h - apex_y))
    p.lineTo(pt(cx - half_w),  pt(sheet_h - base_y))
    p.lineTo(pt(cx + half_w),  pt(sheet_h - base_y))
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def draw_cell_outlines(c, grid: Grid) -> None:
    """Unfilled OUTLINE_STROKE_WIDTH_MM-stroke rectangle around every cell in
    the grid — the optional "обводка довкола макету" frame. Caller must set
    the stroke color first (e.g. c.setStrokeColor(K100)), same convention as
    draw_registration_marks.

    The caller MUST draw this as the TOPMOST layer, over the already-tiled
    artwork — see server/core/print_pdf.py / server/core/shape_print_pdf.py.
    With gap=0 (batch mode) or contain-fit padding, half the stroke's width
    sits exactly on each cell's shared edge; drawing this underneath the
    artwork would silently hide that half wherever the (opaque) artwork tile
    covers it, and the outline would then only ever show at the outer
    perimeter of the whole grid instead of around every individual sticker.
    """
    def pt(v: float) -> float:
        return v * MM

    c.setLineWidth(pt(OUTLINE_STROKE_WIDTH_MM))
    stride_x = grid.cell_w + grid.gap
    stride_y = grid.cell_h + grid.gap
    for row in range(grid.rows):
        for col in range(grid.cols):
            cell_x = grid.grid_x + col * stride_x
            cell_top = grid.grid_y + row * stride_y
            c.rect(
                pt(cell_x), pt(grid.sheet_h - cell_top - grid.cell_h),
                pt(grid.cell_w), pt(grid.cell_h),
                fill=0, stroke=1,
            )
