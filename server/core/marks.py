"""Corner registration marks shared by the template PDF and the cut-contour PDF."""

from server.core.layout import Grid
from server.utils.constants import MM


def draw_registration_marks(c, grid: Grid) -> None:
    """Four filled L-brackets, each pointing from its sheet corner toward the interior."""
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
