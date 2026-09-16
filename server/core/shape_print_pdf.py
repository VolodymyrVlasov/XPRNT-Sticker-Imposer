"""Print PDF for shaped stickers: the raster-only artwork (see
server/core/shape_inspect.py's extract_raster_only_pdf — no vector cut lines,
those must never print) tiled across the grid.

Unlike the rectangular flow's generate_print_pdf, there is no template/marks
layer to merge first (shaped mode has no template PDF at all) and no
contain-fit scaling: dim_w/dim_h already equal the cell exactly (bleed
included), so placement is 1:1 mm-for-mm — just the same rotate-to-orientation
handling server/core/print_pdf.py uses, reproduced here without importing it.
"""

from server.core.layout import Grid
from server.utils.constants import MM


def generate_shape_print_pdf(output_path: str, raster_only_pdf_path: str, grid: Grid) -> None:
    from pypdf import PageObject, PdfReader, PdfWriter, Transformation

    art_reader = PdfReader(raster_only_pdf_path)
    art_page = art_reader.pages[0]
    art_w_pt = float(art_page.mediabox.width)
    art_h_pt = float(art_page.mediabox.height)

    cell_is_landscape = grid.cell_w >= grid.cell_h
    art_is_landscape = art_w_pt >= art_h_pt

    if art_is_landscape != cell_is_landscape:
        rotated_page = PageObject.create_blank_page(width=art_h_pt, height=art_w_pt)
        rotated_page.merge_transformed_page(
            art_page,
            Transformation((0, -1, 1, 0, 0, art_w_pt)),
        )
        art_page = rotated_page
        art_w_pt, art_h_pt = art_h_pt, art_w_pt

    art_x0 = float(art_page.mediabox.left)
    art_y0 = float(art_page.mediabox.bottom)

    sheet_w_pt = grid.sheet_w * MM
    sheet_h_pt = grid.sheet_h * MM
    page = PageObject.create_blank_page(width=sheet_w_pt, height=sheet_h_pt)

    # No contain-fit here — the tile IS the cell (bleed-inclusive), so scale is
    # always 1:1; only the placement translation varies per cell.
    stride_x = grid.cell_w + grid.gap
    stride_y = grid.cell_h + grid.gap
    for row in range(grid.rows):
        for col in range(grid.cols):
            cell_left_pt = (grid.grid_x + col * stride_x) * MM
            cell_top = grid.grid_y + row * stride_y
            cell_bottom_pt = sheet_h_pt - (cell_top + grid.cell_h) * MM
            tx = cell_left_pt - art_x0
            ty = cell_bottom_pt - art_y0
            t = Transformation((1, 0, 0, 1, tx, ty))
            page.merge_transformed_page(art_page, t, over=True)

    writer = PdfWriter()
    writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)
