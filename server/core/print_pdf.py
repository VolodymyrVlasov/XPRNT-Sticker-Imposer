import os
import tempfile

from server.core.layout import Grid
from server.utils.constants import MM


def generate_print_pdf(
    output_path: str,
    template_pdf_path: str,
    artwork_path: str,
    grid: Grid,
    deform: bool = False,
    outline: bool = False,
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

    # Layer 2 — artwork tiled into every cell (middle)
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

    # Layer 3 — optional 0.1mm black outline around every cell (top layer —
    # see draw_cell_outlines' own docstring for why it must go here, not
    # baked into the template above).
    outline_path = None
    outline_reader = None
    try:
        if outline:
            from reportlab.pdfgen import canvas as rl_canvas

            from server.core.marks import draw_cell_outlines
            from server.utils.constants import K100

            outline_fd, outline_path = tempfile.mkstemp(
                suffix=".pdf", dir=os.path.dirname(output_path) or ".",
            )
            os.close(outline_fd)
            oc = rl_canvas.Canvas(outline_path, pagesize=(sheet_w_pt, sheet_h_pt))
            oc.setStrokeColor(K100)
            draw_cell_outlines(oc, grid)
            oc.save()
            outline_reader = PdfReader(outline_path)
            page.merge_page(outline_reader.pages[0], over=True)

        writer = PdfWriter()
        writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)
    finally:
        # Same Windows lazy-merge gotcha shape_print_pdf.py already documents
        # for its own marks temp file: pypdf only actually reads
        # outline_reader's page content at writer.write() above, so the
        # reader (and its file handle) must stay open until after that call.
        if outline_reader is not None:
            outline_reader.close()
        if outline_path is not None:
            os.remove(outline_path)
