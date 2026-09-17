"""Print PDF for shaped stickers: registration marks plus the raster-only
artwork (see server/core/shape_inspect.py's extract_raster_only_pdf — no
vector cut lines, those must never print) tiled across the grid.

Unlike the rectangular flow's generate_print_pdf, there is no separate
template file exposed to the user (shaped mode has no template PDF in the
output zip) — but the print sheet itself still needs registration marks for
physical cut alignment, so a small marks-only PDF is generated internally via
reportlab, merged in as the bottom layer (mirroring generate_print_pdf's own
template-merge technique), and discarded — it never appears in the zip.

No contain-fit scaling: dim_w/dim_h already equal the cell exactly (bleed
included), so placement is 1:1 mm-for-mm — just the same rotate-to-orientation
handling server/core/print_pdf.py uses, reproduced here without importing it.

Optionally also merges a 0.1mm outline frame around every cell as the very
top layer — see server/core/marks.py's draw_cell_outlines docstring for why
it must be the topmost layer rather than baked into the marks-only PDF.
"""

import os
import tempfile

from server.core.layout import Grid
from server.utils.constants import MM


def generate_shape_print_pdf(
    output_path: str, raster_only_pdf_path: str, grid: Grid, outline: bool = False,
) -> None:
    from pypdf import PageObject, PdfReader, PdfWriter, Transformation
    from reportlab.pdfgen import canvas as rl_canvas

    from server.core.marks import draw_registration_marks
    from server.utils.constants import K100

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

    # Layer 1 — registration marks (bottom). Built as a throwaway marks-only
    # PDF and merged in, same technique server/core/print_pdf.py uses with its
    # (user-facing, in that mode) template PDF — here it's purely internal.
    #
    # pypdf's merge_page is lazy: it stores a reference into the source
    # PdfReader and only actually reads the page content later, when
    # writer.write() runs — exactly like generate_print_pdf's own
    # PdfReader(template_pdf_path) never gets closed/deleted early. So the
    # temp marks file (and its reader) must stay alive until after write(),
    # and only get cleaned up in the finally around that whole span. Same
    # rule applies to the optional outline temp file below.
    marks_fd, marks_path = tempfile.mkstemp(suffix=".pdf", dir=os.path.dirname(output_path) or ".")
    os.close(marks_fd)
    marks_reader = None
    outline_path = None
    outline_reader = None
    try:
        marks_canvas = rl_canvas.Canvas(marks_path, pagesize=(sheet_w_pt, sheet_h_pt))
        marks_canvas.setFillColor(K100)
        marks_canvas.setStrokeColor(K100)
        draw_registration_marks(marks_canvas, grid)
        marks_canvas.save()
        marks_reader = PdfReader(marks_path)
        page.merge_page(marks_reader.pages[0], over=True)

        # Layer 2 — artwork tiled into every cell (middle). No contain-fit
        # here — the tile IS the cell (bleed-inclusive), so scale is always
        # 1:1; only the placement translation varies per cell.
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

        # Layer 3 — optional 0.1mm black outline around every cell (top).
        if outline:
            from server.core.marks import draw_cell_outlines

            outline_fd, outline_path = tempfile.mkstemp(
                suffix=".pdf", dir=os.path.dirname(output_path) or ".",
            )
            os.close(outline_fd)
            outline_canvas = rl_canvas.Canvas(outline_path, pagesize=(sheet_w_pt, sheet_h_pt))
            outline_canvas.setStrokeColor(K100)
            draw_cell_outlines(outline_canvas, grid)
            outline_canvas.save()
            outline_reader = PdfReader(outline_path)
            page.merge_page(outline_reader.pages[0], over=True)

        writer = PdfWriter()
        writer.add_page(page)
        with open(output_path, "wb") as f:
            writer.write(f)
    finally:
        # Close both readers' own file handles explicitly before removing
        # their temp files — Windows raises PermissionError deleting a file
        # that still has a live handle, and merge_page's laziness means
        # neither reader can be closed any sooner than here.
        if marks_reader is not None:
            marks_reader.close()
        os.remove(marks_path)
        if outline_reader is not None:
            outline_reader.close()
        if outline_path is not None:
            os.remove(outline_path)
