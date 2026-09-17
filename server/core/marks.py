"""Corner registration marks and the feed-direction arrow, shared by the
template PDF, the shaped-sticker print PDF, and the vector cut-contour
reference PDF — everywhere a person or a plotter aligns against the physical
printed sheet.
"""

from server.core.layout import Grid
from server.utils.constants import MM

# Feed-direction arrow: a solid triangle pointing toward the top sheet edge,
# centered horizontally, telling the operator which way to load the sheet
# into the plotter. Sized to sit in roughly the same vertical band as the
# top corner marks' own 9mm arms (see draw_registration_marks) — not
# fine-tuned pixel-for-pixel against the reference photo yet. Check the
# smoke-test renders and adjust these two constants if the size/position
# looks off before calling this done.
FEED_ARROW_WIDTH_MM = 8.0
FEED_ARROW_HEIGHT_MM = 7.0


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

    _draw_feed_arrow(c, sheet_w, sheet_h, mo)


def _draw_feed_arrow(c, sheet_w: float, sheet_h: float, mark_offset: float) -> None:
    """Solid triangle, apex toward the top sheet edge, centered horizontally
    across the sheet width — indicates which edge to feed into the plotter
    first. Roughly spans the same vertical band as the top corner marks.
    """
    def pt(v: float) -> float:
        return v * MM

    cx = sheet_w / 2.0
    apex_y = mark_offset + 2.0  # distance from the top sheet edge, mm — pushed
    # down from the corner marks' own -0.5 baseline so the arrow's apex clears
    # the template's centered filename-label caption (also horizontally
    # centered, drawn independently by pdf_template.py), which occupies
    # roughly the same band as the corner marks' top edge.
    base_y = apex_y + FEED_ARROW_HEIGHT_MM
    half_w = FEED_ARROW_WIDTH_MM / 2.0

    p = c.beginPath()
    p.moveTo(pt(cx),           pt(sheet_h - apex_y))
    p.lineTo(pt(cx - half_w),  pt(sheet_h - base_y))
    p.lineTo(pt(cx + half_w),  pt(sheet_h - base_y))
    p.close()
    c.drawPath(p, fill=1, stroke=0)
