"""HPGL (.plt) cut-file generation for a sticker grid.

Two cutting strategies:
  - gap == 0: stickers share cut lines (contiguous grid) -> cut full grid lines,
    fewer passes, with curved lead-ins to avoid whip marks on long straight cuts.
  - gap  > 0: stickers are separated -> cut each cell as its own closed rectangle,
    with a short overlap at the closing corner for a clean loop.
"""

from server.core.layout import Grid
from server.utils.constants import OVERSHOOT


def _lead_in(hx_func, hy_func, pdf_x, pdf_y, direction) -> str:
    """4-point curved lead-in before cutting a line.

    direction: 'right'|'left' for horizontal lines, 'down'|'up' for vertical lines.
    Offsets are applied in PDF mm space before converting to HPGL units.
    """
    arc = [(0.0, -0.2), (0.25, -0.25), (0.4, -0.2), (0.5, 0.0)]
    cmds = ""
    for along, perp in arc:
        if direction == "down":
            px, py = pdf_x + perp, pdf_y + along
        elif direction == "up":
            px, py = pdf_x - perp, pdf_y - along
        elif direction == "right":
            px, py = pdf_x + along, pdf_y + perp
        else:  # left
            px, py = pdf_x - along, pdf_y - perp
        cmds += f"D{hx_func(py)},{hy_func(px)} "
    return cmds


def _grid_lines_cut(out: str, hx, hy, grid: Grid) -> str:
    mo = grid.mark_offset
    ov = OVERSHOOT
    h_lines = [grid.grid_y + i * grid.cell_h for i in range(grid.rows + 1)]
    v_lines = [grid.grid_x + i * grid.cell_w for i in range(grid.cols + 1)]

    for idx, pdf_x in enumerate(v_lines):
        top_to_bottom = (idx % 2 == 0)
        sy = grid.grid_y - ov            if top_to_bottom else grid.grid_y + grid.grid_h + ov
        ey = grid.grid_y + grid.grid_h + ov if top_to_bottom else grid.grid_y - ov
        direction = "down" if top_to_bottom else "up"
        out += f"U{hx(sy)},{hy(pdf_x)} "
        out += _lead_in(hx, hy, pdf_x, sy, direction)
        out += f"D{hx(ey)},{hy(pdf_x)} "

    for idx, pdf_y in enumerate(reversed(h_lines)):
        left_to_right = (idx % 2 == 0)
        sx = grid.grid_x - ov            if left_to_right else grid.grid_x + grid.grid_w + ov
        ex = grid.grid_x + grid.grid_w + ov if left_to_right else grid.grid_x - ov
        direction = "right" if left_to_right else "left"
        out += f"U{hx(pdf_y)},{hy(sx)} "
        out += _lead_in(hx, hy, sx, pdf_y, direction)
        out += f"D{hx(pdf_y)},{hy(ex)} "

    return out


def _cell_rects_cut(out: str, hx, hy, grid: Grid) -> str:
    ov = OVERSHOOT
    stride_x = grid.cell_w + grid.gap
    stride_y = grid.cell_h + grid.gap

    for row in range(grid.rows):
        for col in range(grid.cols):
            x0 = grid.grid_x + col * stride_x
            x1 = x0 + grid.cell_w
            y0 = grid.grid_y + row * stride_y
            y1 = y0 + grid.cell_h

            out += f"U{hx(y0 - ov)},{hy(x0)} "
            for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 - ov)):
                out += f"D{hx(py)},{hy(px)} "

    return out


def generate_plt(output_path: str, grid: Grid) -> None:
    mo = grid.mark_offset
    fx = round((grid.sheet_h - 2 * mo) * 40)   # FSIZE X — along feed direction
    fy = round((grid.sheet_w - 2 * mo) * 40)   # FSIZE Y — across feed direction
    out = f"IN;FSIZE{fx},{fy} BD:103,0;TB26,{fx},{fy};CT1;"

    def hx(pdf_y: float) -> int:    # HPGL X (along feed) <- PDF Y
        return round((pdf_y - mo) * 40)

    def hy(pdf_x: float) -> int:    # HPGL Y (across feed) <- PDF X
        return round((pdf_x - mo) * 40)

    if grid.gap <= 0:
        out = _grid_lines_cut(out, hx, hy, grid)
    else:
        out = _cell_rects_cut(out, hx, hy, grid)

    out += "U0,0;!PG;!PG;"
    with open(output_path, "w", encoding="ascii") as f:
        f.write(out)
