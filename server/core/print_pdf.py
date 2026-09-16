from server.core.layout import Grid
from server.utils.constants import MM


def generate_print_pdf(
    output_path: str,
    template_pdf_path: str,
    artwork_path: str,
    grid: Grid,
    deform: bool = False,
) -> None:
    from pypdf import PageObject, PdfReader, PdfWriter, Transformation

    art_reader = PdfReader(artwork_path)
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
    art_w_pt = float(art_page.mediabox.width)
    art_h_pt = float(art_page.mediabox.height)

    cell_w_pt = grid.cell_w * MM
    cell_h_pt = grid.cell_h * MM
    if deform:
        # Sticker box was resized off the artwork's native ratio — stretch X/Y
        # independently so the artwork exactly fills the cell, no padding.
        scale_x = cell_w_pt / art_w_pt
        scale_y = cell_h_pt / art_h_pt
        pad_x = pad_y = 0.0
    else:
        # Uniform contain-fit — keeps the artwork's own aspect ratio, centered.
        scale_x = scale_y = min(cell_w_pt / art_w_pt, cell_h_pt / art_h_pt)
        pad_x = (cell_w_pt - art_w_pt * scale_x) / 2
        pad_y = (cell_h_pt - art_h_pt * scale_y) / 2

    sheet_w_pt = grid.sheet_w * MM
    sheet_h_pt = grid.sheet_h * MM
    page = PageObject.create_blank_page(width=sheet_w_pt, height=sheet_h_pt)

    # Layer 1 — template registration marks (bottom)
    page.merge_page(PdfReader(template_pdf_path).pages[0], over=True)

    # Layer 2 — artwork tiled into every cell (top)
    stride_x = grid.cell_w + grid.gap
    stride_y = grid.cell_h + grid.gap
    for row in range(grid.rows):
        for col in range(grid.cols):
            cell_left_pt = (grid.grid_x + col * stride_x) * MM
            cell_top = grid.grid_y + row * stride_y
            cell_bottom_pt = sheet_h_pt - (cell_top + grid.cell_h) * MM
            tx = cell_left_pt + pad_x - art_x0 * scale_x
            ty = cell_bottom_pt + pad_y - art_y0 * scale_y
            t = Transformation((scale_x, 0, 0, scale_y, tx, ty))
            page.merge_transformed_page(art_page, t, over=True)

    writer = PdfWriter()
    writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)
