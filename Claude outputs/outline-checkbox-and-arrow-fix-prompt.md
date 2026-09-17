You are working in the project root.
Do NOT modify existing working code beyond what is listed below.
Base branch: `main`. No feature branch — per standing agreement for this
project, commit and push directly to `main` (single-maintainer repo, small
change).

## GOAL

Two small features plus one bundled bug fix, all touching the same "sheet
& marking" area of the app:

1. A new checkbox on the "2. Аркуш і розмітка" tab: "Додати обводку довкола
   макету" — when checked, the generated print PDF gets a 0.1mm solid black
   outline frame around every sticker cell (both rectangular and shaped
   modes), and the live browser preview shows the same frame so what you see
   matches what prints.
2. Fix the feed-direction arrow (the small triangle at the top-center of the
   sheet, added in a previous stage): change it to a fixed 3×3mm triangle
   whose apex sits exactly 5mm from the sheet's top edge — independent of
   `mark_offset` (it was previously sized 8×7mm and positioned at
   `mark_offset + 2mm`).
3. Bundled bug fix: `BatchItem.deform` is missing from `server/models.py` and
   `generate_batch.py` never passes `deform` through to `generate_print_pdf`
   — the frontend's per-item "деформація" toggle (set via the properties
   popup) is silently dropped during real batch generation even though it
   correctly affects the live preview. Add the missing field and wire it
   through so batch generation actually respects it.

## STEP 1 — server/models.py — add fields

In `BatchItem`, add a `deform` field (this was supposed to ship with the
stage-4-8 frontend overhaul's per-item deform support but was missed):

```python
class BatchItem(BaseModel):
    upload_id: str
    dim_w: float = Field(gt=0)
    dim_h: float = Field(gt=0)
    orientation: str | None = None
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    quantity: int = Field(gt=0)
    deform: bool = False  # was missing — see fix note in the prompt this came from
```

Add an `outline` field (shared/global, like `cut_contour` — not per-item) to
all four generate-request models. Do NOT add `outline` to `BatchItem` or
`ShapeBatchItem` — it's a Tab-2/whole-request setting, same as `cut_contour`.

- `GenerateRequest`: add `outline: bool = False` next to the existing
  `deform`/`cut_contour` fields.
- `ShapeGenerateRequest`: add `outline: bool = False` next to `cut_contour`.
- `BatchGenerateRequest`: add `outline: bool = False` next to `cut_contour`.
- `ShapeBatchGenerateRequest`: add `outline: bool = False` next to
  `cut_contour`.

Do NOT change any other fields or classes in this file.

## STEP 2 — server/core/marks.py — replace the whole file

Two changes bundled here: the feed-arrow constants/position fix, and a new
`draw_cell_outlines()` function for the per-cell outline frame (feature 1).
Replace the entire file with:

```python
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
```

## STEP 3 — server/core/print_pdf.py — replace the whole file

Adds an `outline: bool = False` parameter and, when true, merges a
`draw_cell_outlines` overlay as the topmost layer (after the artwork tiling
loop, before writing). Uses the same "keep the temp PdfReader alive until
after `writer.write()`, only close/delete in a `finally`" technique already
established in `shape_print_pdf.py` (pypdf's `merge_page` is lazy — it only
actually reads the source page at write time). Replace the entire file with:

```python
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
```

## STEP 4 — server/core/shape_print_pdf.py — replace the whole file

Same idea as Step 3, applied to the shaped-sticker flow, which already has
one internal temp-canvas (`marks_path`) for registration marks — add a
second one for the outline, following the exact same open/keep-alive/close
pattern. Replace the entire file with:

```python
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
```

## STEP 5 — routes — thread `outline` (and fix `deform`) through

Four small, precise edits — do NOT rewrite these files, just change the
single call site in each:

**`server/routes/generate.py`** — change:
```python
        generate_print_pdf(print_path, tpl_pdf, artwork_path, grid, deform=payload.deform)
```
to:
```python
        generate_print_pdf(print_path, tpl_pdf, artwork_path, grid, deform=payload.deform, outline=payload.outline)
```

**`server/routes/generate_shape.py`** — change:
```python
        generate_shape_print_pdf(print_path, raster_only_pdf, grid)
```
to:
```python
        generate_shape_print_pdf(print_path, raster_only_pdf, grid, outline=payload.outline)
```

**`server/routes/generate_batch.py`** — change:
```python
            generate_print_pdf(print_path, tpl_pdf, artwork_path, grid)
```
to:
```python
            generate_print_pdf(print_path, tpl_pdf, artwork_path, grid, deform=item.deform, outline=payload.outline)
```
(This is the bundled bug fix — `deform` was never passed here at all, so a
per-item deform choice from the properties popup silently had zero effect on
the actual generated PDF even though it correctly showed in the live
preview. `deform` comes from the per-item `BatchItem.deform` added in Step 1;
`outline` comes from the shared/global `payload.outline`.)

**`server/routes/generate_batch_shape.py`** — change:
```python
            generate_shape_print_pdf(print_path, raster_only_pdf, grid)
```
to:
```python
            generate_shape_print_pdf(print_path, raster_only_pdf, grid, outline=payload.outline)
```

## STEP 6 — web/index.html — new checkbox on Tab 2

In `card-panel-params` (the "2. Аркуш і розмітка" tab), add a new
`field-row` right after the `field-margin` row and before the `bleed-row`
(so it sits with the other sheet/marking settings, ahead of the
shape-mode-only bleed field):

```html
            <div class="field-row" id="outline-row">
              <label for="outline-checkbox">Додати обводку довкола макету (0.1 мм, чорна)</label>
              <input type="checkbox" id="outline-checkbox">
            </div>
```

No `checked` attribute — defaults to unchecked (opt-in), unlike
`cut-contour-checkbox` which defaults checked. No CSS changes needed —
`.field-row input[type="checkbox"]` styling already covers it.

## STEP 7 — web/app.js — wire the checkbox up

1. Near the existing `const cutContourCheckbox = el("cut-contour-checkbox");`
   declaration, add:
   ```js
   const outlineCheckbox = el("outline-checkbox");
   ```

2. In `startNewTask()`, next to the existing
   `cutContourCheckbox.checked = true;` line, add:
   ```js
   outlineCheckbox.checked = false;
   ```

3. Add a change listener that redraws just the current preview (not a full
   `renderSelectedPreview()`, which would also reset zoom/pan — this is a
   pure visual toggle, no layout math changes, so don't disturb the user's
   current zoom):
   ```js
   outlineCheckbox.addEventListener("change", () => {
     if (selectedIndex >= 0 && items[selectedIndex].layout) {
       const it = items[selectedIndex];
       renderLayout(it.layout, it, shapeMode ? false : it.deform);
     }
   });
   ```
   Place this near the other Tab-2 input listeners (`markParamsPending`
   etc.) or right after the `paramsApplyBtn` wiring — wherever reads best in
   context.

4. In `renderLayout(layout, artwork, deform)`, inside the existing
   `for (let row ...) for (let col ...)` loop, after the existing
   `if (!shapeMode) { ... }` block that draws the per-cell border rect
   (around line 759-766), add:
   ```js
       if (outlineCheckbox.checked) {
         // Visual stand-in for the real printed 0.1mm outline (see
         // server/core/marks.py's draw_cell_outlines) — scaled up here for
         // visibility in the SVG preview, same convention the shape-mode
         // contour dashes already use (strokeW * 0.5), not literal mm.
         previewSvg.appendChild(svgEl("rect", {
           x: cellX, y: cellY, width: layout.cell_w, height: layout.cell_h,
           fill: "none", stroke: "#000000", "stroke-width": strokeW * 0.4,
         }));
       }
   ```
   This applies in BOTH rectangular and shape mode (shape mode currently has
   no per-cell rectangle at all — this adds one, on top of the traced cut
   contour, only when the checkbox is checked). Note: in rectangular mode
   there is already an unconditional, always-on thin cell-border rect drawn
   just above this (a pre-existing decorative grid reference, unrelated to
   this feature and unchanged) — the new rect simply layers on top of it
   when the checkbox is checked; that's expected, not a bug.

5. In `generateBatch()`'s payload object, add `outline: outlineCheckbox.checked`
   next to the existing `cut_contour: cutContourCheckbox.checked` line.

6. In `generateShapeBatch()`'s payload object, add the same:
   `outline: outlineCheckbox.checked` next to `cut_contour: cutContourCheckbox.checked`.

Do NOT change anything else in this file.

## STEP 8 — SMOKE TEST

1. Restart the local server (`python run_server.py`) and confirm it starts
   cleanly.

2. **Geometry check for the feed arrow** — before eyeballing anything, write
   a short throwaway script (or a Python one-liner) that computes, for the
   default SRA3 sheet with `mark_offset=9`, `field_margin=2`:
   - the feed arrow's vertical span from the sheet's top edge:
     `FEED_ARROW_OFFSET_MM` to `FEED_ARROW_OFFSET_MM + FEED_ARROW_HEIGHT_MM`
     (5mm–8mm from the top edge);
   - `pdf_template.py`'s caption band: baseline at `mark_offset + 0.5` (8.5mm
     from the top edge) with a 12pt font (~4.2mm cap height) and the two
     small corner triangles at the same baseline, height `font_pt` (12pt ≈
     4.2mm) — i.e. roughly spanning ~4.3mm–8.5mm from the top edge.
   Report whether these two vertical bands overlap (they look like they do,
   on paper). Do NOT silently move the arrow or the caption to "fix" this —
   the 3×3mm/5mm numbers are an explicit spec. Just report the numeric
   finding plainly in the Summary below so it can be decided on with the
   full picture (it may turn out fine visually since the arrow triangle
   itself is very narrow, only 3mm wide, vs. the caption text's much wider
   horizontal footprint, so the two might not visually intersect where the
   caption actually has ink — but say what the numbers show either way).

3. Generate one single-file rectangular batch with the outline checkbox
   OFF, then ON. Open both output print PDFs (e.g. render page 1 to a PNG
   with PyMuPDF, or just report page count / no exceptions if no image
   viewer is available) and confirm: OFF has no border around the cells
   beyond the usual template/marks; ON has a visible thin black frame around
   every sticker cell, not just the outer edge of the grid.

4. Repeat step 3 for shaped-sticker mode (any test shape PDF) — confirm the
   outline frame appears there too, on top of the shape's own artwork.

5. Generate a batch with 2+ items where at least one item has `deform`
   set (via the properties popup, aspect-ratio lock turned off with a
   resized sticker box) — confirm the resulting print PDF actually shows
   the artwork stretched to fill the cell for that item (not just
   contain-fit), verifying the bundled `BatchItem.deform` fix from Step 1/5
   actually works end-to-end now, not just in the live preview.

6. Regression: single-file generate (`/api/generate`), shape single-file
   generate (`/api/generate-shape`), and the existing cut-contour checkbox
   still work as before.

## STEP 9 — CLAUDE.md

Append a short entry to "Останній стан" noting: the new outline checkbox +
its print-PDF/preview implementation, the feed-arrow resize (3×3mm / 5mm
fixed offset) and the geometry-overlap finding from Step 8.2, and the
`BatchItem.deform` fix (previously silently ignored in batch generation).

## STEP 10 — COMMIT + PUSH

```
git add server/models.py server/core/marks.py server/core/print_pdf.py server/core/shape_print_pdf.py server/routes/generate.py server/routes/generate_shape.py server/routes/generate_batch.py server/routes/generate_batch_shape.py web/index.html web/app.js CLAUDE.md
git commit -m "feat: optional cell outline frame, fix feed-arrow size/position, fix dropped batch deform"
git push origin main
```

## STEP 11 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🔴 Not implemented
### 🧪 Smoke test results (all 6 points, including the Step 8.2 geometry numbers)
### 📋 Known issues for next session
