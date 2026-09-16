"""Sheet imposition math: fitting a grid of stickers onto a sheet.

Coordinate model (all mm, origin at sheet top-left, Y growing downward):
  sheet edge -> [mark_offset] -> registration marks -> [field_margin] -> usable field
  the sticker grid is centered inside the usable field, with `gap` mm between cells.
"""

import math
from dataclasses import dataclass


@dataclass
class Grid:
    orientation: str
    cell_w: float
    cell_h: float
    cols: int
    rows: int
    gap: float
    grid_w: float
    grid_h: float
    grid_x: float
    grid_y: float
    sheet_w: float
    sheet_h: float
    mark_offset: float
    field_margin: float
    fits: bool

    @property
    def count(self) -> int:
        return self.cols * self.rows

    @property
    def max_capacity(self) -> tuple[int, int]:
        """Max (cols, rows) of this cell size that could ever fit given the current margins/gap."""
        usable_w, usable_h = usable_field(self.sheet_w, self.sheet_h, self.mark_offset, self.field_margin)
        return max_fit(self.cell_w, self.cell_h, usable_w, usable_h, self.gap)

    def as_dict(self) -> dict:
        max_cols, max_rows = self.max_capacity
        return {
            "orientation": self.orientation,
            "cell_w": self.cell_w, "cell_h": self.cell_h,
            "cols": self.cols, "rows": self.rows,
            "max_cols": max_cols, "max_rows": max_rows,
            "gap": self.gap,
            "grid_w": self.grid_w, "grid_h": self.grid_h,
            "grid_x": self.grid_x, "grid_y": self.grid_y,
            "sheet_w": self.sheet_w, "sheet_h": self.sheet_h,
            "mark_offset": self.mark_offset, "field_margin": self.field_margin,
            "fits": self.fits, "count": self.count,
        }


def cell_dims(dim_w: float, dim_h: float, orientation: str) -> tuple[float, float]:
    """Return (cell_w, cell_h) for the sticker's two raw dimensions and an orientation.

    WIDE = long side across the sheet (X), TALL = long side along the feed (Y).
    """
    short_side = min(dim_w, dim_h)
    long_side = max(dim_w, dim_h)
    if orientation == "WIDE":
        return long_side, short_side
    return short_side, long_side


def usable_field(sheet_w: float, sheet_h: float, mark_offset: float, field_margin: float) -> tuple[float, float]:
    inset = 2 * (mark_offset + field_margin)
    return sheet_w - inset, sheet_h - inset


def max_fit(cell_w: float, cell_h: float, usable_w: float, usable_h: float, gap: float) -> tuple[int, int]:
    """Max whole cells (cols, rows) of size cell_w x cell_h, `gap` mm apart, fitting in usable_w x usable_h."""
    def fit(span: float, cell: float) -> int:
        if cell <= 0:
            return 0
        return max(0, math.floor((span + gap + 1e-9) / (cell + gap)))

    return fit(usable_w, cell_w), fit(usable_h, cell_h)


def build_grid(
    dim_w: float, dim_h: float,
    sheet_w: float, sheet_h: float,
    orientation: str,
    cols: int, rows: int,
    mark_offset: float, field_margin: float, gap: float,
) -> Grid:
    """Build a Grid for an explicit orientation/cols/rows (no auto-fit)."""
    cell_w, cell_h = cell_dims(dim_w, dim_h, orientation)
    usable_w, usable_h = usable_field(sheet_w, sheet_h, mark_offset, field_margin)

    grid_w = cols * cell_w + max(cols - 1, 0) * gap if cols > 0 else 0.0
    grid_h = rows * cell_h + max(rows - 1, 0) * gap if rows > 0 else 0.0

    field_x = mark_offset + field_margin
    field_y = mark_offset + field_margin
    grid_x = field_x + (usable_w - grid_w) / 2.0
    grid_y = field_y + (usable_h - grid_h) / 2.0

    fits = cols >= 1 and rows >= 1 and grid_w <= usable_w + 1e-6 and grid_h <= usable_h + 1e-6

    return Grid(
        orientation=orientation, cell_w=cell_w, cell_h=cell_h,
        cols=cols, rows=rows, gap=gap,
        grid_w=grid_w, grid_h=grid_h, grid_x=grid_x, grid_y=grid_y,
        sheet_w=sheet_w, sheet_h=sheet_h,
        mark_offset=mark_offset, field_margin=field_margin,
        fits=fits,
    )


def auto_grid(
    dim_w: float, dim_h: float,
    sheet_w: float, sheet_h: float,
    mark_offset: float, field_margin: float, gap: float,
    orientation: str | None = None,
) -> Grid:
    """Pick the orientation (unless fixed) and cols/rows that maximize sticker count."""
    usable_w, usable_h = usable_field(sheet_w, sheet_h, mark_offset, field_margin)
    orientations = [orientation] if orientation else ["WIDE", "TALL"]

    best: Grid | None = None
    for orient in orientations:
        cell_w, cell_h = cell_dims(dim_w, dim_h, orient)
        cols, rows = max_fit(cell_w, cell_h, usable_w, usable_h, gap)
        candidate = build_grid(
            dim_w, dim_h, sheet_w, sheet_h, orient, cols, rows,
            mark_offset, field_margin, gap,
        )
        if best is None or candidate.count > best.count:
            best = candidate

    assert best is not None
    return best


def resolve_grid(
    dim_w: float, dim_h: float,
    sheet_w: float, sheet_h: float,
    mark_offset: float, field_margin: float, gap: float,
    orientation: str | None = None,
    cols: int | None = None,
    rows: int | None = None,
) -> Grid:
    """Build a Grid from possibly-partial input: explicit cols/rows/orientation win,
    anything left unset (None or 0) is auto-fit to maximize sticker count.

    Orientation and cols/rows are resolved independently: an explicit cols/rows
    override applies on top of whichever orientation is in effect (given, or the
    one auto-fit would have picked), so editing the grid doesn't require also
    pinning the orientation.
    """
    resolved_orientation = orientation or auto_grid(
        dim_w, dim_h, sheet_w, sheet_h, mark_offset, field_margin, gap,
    ).orientation

    if cols and rows:
        return build_grid(
            dim_w, dim_h, sheet_w, sheet_h, resolved_orientation, cols, rows,
            mark_offset, field_margin, gap,
        )
    return auto_grid(
        dim_w, dim_h, sheet_w, sheet_h, mark_offset, field_margin, gap,
        orientation=resolved_orientation,
    )
