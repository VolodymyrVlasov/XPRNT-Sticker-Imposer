You are working in the project root. This is stage 1 of a larger, multi-stage
redesign (both backend and frontend — this stage is backend-only). Pull latest main
first.

Per the user's explicit instruction, this whole line of work (this stage and every
stage after it, regardless of size) commits and pushes directly to `main` — no
feature branches, no PRs, for anything in this effort.

## GOAL — a real design bug in the shaped-stickers feature

Currently, a shaped sticker's tile size (`dim_w`/`dim_h` — the value that drives
the whole grid/imposition math) is computed from the CUT-CONTOUR's own bounding
box plus a fixed 1mm bleed on each side (`server/core/shape_inspect.py`,
`inspect_shape_pdf()`). This is wrong: if a client's PDF page is, say, A5-ish
212×150mm but the vector cut line inside it only outlines a small 55×5mm shape
somewhere on the page (a common case — the cut contour can be a small decorative
die-cut window or partial shape, not the sticker's own outline), the app currently
shrinks the whole layout down to roughly 57×7mm — completely wrong. The uploaded
file's own page size must never be altered based on where the vector geometry
happens to sit.

The correct model (confirmed with the user):

- The sticker's tile size for imposition (`dim_w`/`dim_h` — feeds `resolve_grid()`,
  drives cell placement/tiling/print/cut just like today) = the PDF's own page
  size: **TrimBox if present, else MediaBox** — same convention the rectangular
  flow's `server/core/pdf_inspect.py` already uses (there via pypdf; here via
  PyMuPDF's `page.trimbox`, which already falls back to MediaBox automatically
  when no TrimBox is defined — verified empirically, no manual "/TrimBox" in page
  check needed the way pdf_inspect.py does it with pypdf).
- The vector cut-contour's own bounding box is IRRELEVANT to sizing now — it can
  be any size, anywhere within the page. Only "does at least one vector path exist
  somewhere in the file" still matters (unchanged validation).
- Bleed becomes a per-request parameter (`bleed_mm`, default 1.0mm, shared for the
  whole batch when batch-generating — not per-item) instead of the hardcoded
  `SHAPE_BLEED_MM` constant used directly in the math. It is no longer ADDED to
  anything — instead it's used ONLY to compute a separate "actual/net" size for
  display purposes: `actual_w = dim_w - 2*bleed_mm`, `actual_h = dim_h - 2*bleed_mm`
  (e.g. page 212×150 with the default 1mm bleed → actual size 210×148 — this
  assumes the designer's own page already has bleed baked into its dimensions,
  which is now the designer's responsibility, not something this app adds).
- Cut-contour subpath coordinates are now simply relative to the PAGE's own
  top-left corner (mm) — there is no more "inset by bleed from the contour's own
  bbox" repositioning, since the tile origin IS the page origin now. This is
  actually a simplification of the existing coordinate math, not an addition.
- The raster crop for the print PDF (`extract_raster_only_pdf`) now crops to the
  page's own TrimBox/MediaBox directly — no more computing a bbox+bleed region
  from the contour.

This only touches `server/core/shape_inspect.py`'s internals, plus the request/
response models and the three shape routes that need to plumb `bleed_mm` through.
`shape_print_pdf.py`, `shape_contour_pdf.py`, and `shape_plt_writer.py` need ZERO
changes — verified by reading them: they all treat `dim_w`/`dim_h` generically as
"the tile's own dimensions" for rotation/placement math and never assume anything
about how dim_w/dim_h were computed or where within the tile the contour sits, and
`shape_print_pdf.py` reads its raster page's own actual size directly from that
PDF rather than from a passed-in dim_w/dim_h. Do not touch those three files.

## STEP 1 — UPDATE: server/utils/constants.py

Update the `SHAPE_BLEED_MM` comment — it's now a DEFAULT for the request-level
`bleed_mm` parameter (used to compute the displayed "actual" size), not a value
added directly into the tile-size math:

```python
# Default bleed for shaped stickers, used only to compute the displayed
# "actual" (net/trim) sticker size as page_size - 2*bleed_mm — see
# ShapeGenerateRequest.bleed_mm. Callers may override this per request.
SHAPE_BLEED_MM = 1.0
```

## STEP 2 — UPDATE: server/core/shape_inspect.py

### 2a. `ShapeArtworkInfo` — replace `bleed_box_pt` with `page_box_pt`, add `actual_w`/`actual_h`

```python
@dataclass
class ShapeArtworkInfo:
    dim_w: float  # PDF page width (TrimBox if present else MediaBox), mm — feeds
    # the grid/imposition math, exactly like before; just no longer bleed-derived.
    dim_h: float
    actual_w: float  # dim_w - 2*bleed_mm — the displayed "actual"/net sticker
    # size (see module docstring / the prompt that introduced this). Display only —
    # never feeds grid math.
    actual_h: float
    bleed_mm: float  # the bleed value actually used to compute actual_w/actual_h
    page_count: int
    subpaths: list[ContourSubpath]  # coordinates relative to the PAGE's own
    # top-left corner (mm) — i.e. relative to page_box_pt's own (x0, y0), not
    # inset by any bleed amount.
    page_box_pt: tuple[float, float, float, float]  # (x0, y0, x1, y1) — the
    # page's own TrimBox (or MediaBox) in the SOURCE PDF's own point space. This
    # is exactly the region extract_raster_only_pdf should crop the artwork to.
```

### 2b. `inspect_shape_pdf()` — new signature, simplified sizing

```python
def inspect_shape_pdf(path: str, bleed_mm: float) -> ShapeArtworkInfo:
```

Replace the whole "raw cut-contour bounding box" section (the part that currently
unions all `drawings[i]["rect"]` and derives `dim_w`/`dim_h`/`offset_x`/`offset_y`
from that union plus bleed) with:

```python
page_box = page.trimbox  # falls back to MediaBox automatically when no
# TrimBox is defined on the page (verified empirically) — same convention as
# server/core/pdf_inspect.py's pypdf-based TrimBox-else-MediaBox logic.

dim_w = round(page_box.width / MM, 2)
dim_h = round(page_box.height / MM, 2)
if dim_w <= 0 or dim_h <= 0:
    raise ValueError("Некоректний розмір сторінки PDF")

actual_w = round(dim_w - 2 * bleed_mm, 2)
actual_h = round(dim_h - 2 * bleed_mm, 2)
if actual_w <= 0 or actual_h <= 0:
    raise ValueError(
        "Бліда завелика для розміру сторінки — фактичний розмір наліпки виходить "
        "від'ємним або нульовим"
    )

def to_mm(p) -> tuple[float, float]:
    return ((p.x - page_box.x0) / MM, (p.y - page_box.y0) / MM)
```

(`to_mm` keeps the same shape/role as before — subpath coordinate conversion — it
just uses `page_box.x0`/`page_box.y0` as the origin instead of a contour-bbox-minus-
bleed offset. The subpath-building loop right after stays exactly the same,
calling this `to_mm`.)

Drop the old `raw_bbox` union loop and the old `bleed_pt`/`offset_x`/`offset_y`
computation entirely — no longer needed since sizing no longer depends on contour
geometry at all.

Update the `return ShapeArtworkInfo(...)` call to match the new fields:

```python
return ShapeArtworkInfo(
    dim_w=dim_w,
    dim_h=dim_h,
    actual_w=actual_w,
    actual_h=actual_h,
    bleed_mm=bleed_mm,
    page_count=doc.page_count,
    subpaths=subpaths,
    page_box_pt=(page_box.x0, page_box.y0, page_box.x1, page_box.y1),
)
```

Everything else in `inspect_shape_pdf()` (image/vector validation via
`_load_with_all_layers_visible`/`_visible_drawings`, the subpath-building loop
itself, the geometric dedup pass) stays exactly as-is — only reads `drawings` for
vector geometry now, never for sizing.

### 2c. `extract_raster_only_pdf()` — rename parameter, update docstring

Rename the `bleed_box_pt` parameter to `page_box_pt` (same 4-tuple shape, same
internal cropping logic — literally zero behavior change to the function body,
just naming/docstring to match its new meaning: it's the page's own TrimBox/
MediaBox now, not a contour-derived region):

```python
def extract_raster_only_pdf(
    path: str, output_path: str, page_box_pt: tuple[float, float, float, float],
) -> None:
    """Write a copy of page 0's raster image(s), CROPPED to `page_box_pt` (the
    page's own TrimBox, or MediaBox if no TrimBox is defined — see
    ShapeArtworkInfo.page_box_pt), with all vector paths stripped.
    ...
```

(keep the rest of the docstring's reasoning about why cropping/repositioning to
(0,0) is needed, just replace "bleed" wording with "page box" wording; internally
just rename the `bleed_box_pt` parameter references to `page_box_pt` — the box_x0/
box_y0/box_x1/box_y1 unpacking and cropping loop are unchanged.)

## STEP 3 — UPDATE: server/models.py

In `ContourGeometry`, remove the `bleed_mm` field — subpaths are no longer
bleed-relative in any way, so it no longer means anything there (confirmed
`web/app.js` never reads `contour.bleed_mm`, so this is safe):

```python
class ContourGeometry(BaseModel):
    subpaths: list[ContourSubpath]  # relative to the page's own top-left corner (mm)
```

In `ShapeAnalyzeResponse`, add `actual_w`/`actual_h`/`bleed_mm` (update the
`dim_w`/`dim_h` comment too, since their role/computation changed):

```python
class ShapeAnalyzeResponse(BaseModel):
    upload_id: str
    filename: str
    dim_w: float  # PDF page size (TrimBox/MediaBox) — feeds the grid math
    dim_h: float
    actual_w: float  # dim_w - 2*bleed_mm — the "actual"/net size, for display
    actual_h: float
    bleed_mm: float
    page_count: int
    sheet_name: str
    layout: LayoutResult
    thumbnail: str
    contour: ContourGeometry
```

In `ShapeGenerateRequest` and `ShapeBatchGenerateRequest`, add (need
`from server.utils.constants import SHAPE_BLEED_MM` in models.py):

```python
    bleed_mm: float = Field(default=SHAPE_BLEED_MM, ge=0)
```

(`ShapeBatchGenerateRequest`'s `bleed_mm` is shared across every item in the
batch, same as `sheet_name`/`material`/etc. already are — not per-item.)

## STEP 4 — UPDATE: server/routes/analyze_shape.py

Accept an optional `bleed_mm` form field alongside the uploaded file (it's a
multipart endpoint already, via `File(...)`):

```python
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
...
from server.utils.constants import DEFAULT_FIELD_MARGIN, DEFAULT_MARK_OFFSET, SHAPE_BLEED_MM, SHEET_PRESETS

@router.post("/api/analyze-shape", response_model=ShapeAnalyzeResponse)
async def analyze_shape(
    file: UploadFile = File(...),
    bleed_mm: float = Form(SHAPE_BLEED_MM),
) -> ShapeAnalyzeResponse:
```

Pass `bleed_mm` into `inspect_shape_pdf(path, bleed_mm)`, and populate the new
response fields:

```python
return ShapeAnalyzeResponse(
    upload_id=upload_id,
    filename=os.path.basename(path),
    dim_w=info.dim_w,
    dim_h=info.dim_h,
    actual_w=info.actual_w,
    actual_h=info.actual_h,
    bleed_mm=info.bleed_mm,
    page_count=info.page_count,
    sheet_name=default_sheet,
    layout=LayoutResult(**grid.as_dict()),
    thumbnail=thumbnail,
    contour=contour,
)
```

(`info.dim_w`/`info.dim_h` are already rounded inside `inspect_shape_pdf` now, so
drop the redundant `round(info.dim_w, 2)` calls here.) Also update the
`ContourGeometry(...)` construction a few lines up to drop the now-removed
`bleed_mm=info.bleed_mm` argument.

## STEP 5 — UPDATE: server/routes/generate_shape.py

Pass `payload.bleed_mm` into `inspect_shape_pdf(artwork_path, payload.bleed_mm)`,
and pass `info.page_box_pt` (renamed) into `extract_raster_only_pdf(artwork_path,
raster_only_pdf, info.page_box_pt)`.

## STEP 6 — UPDATE: server/routes/generate_batch_shape.py

Same two changes as STEP 5, applied inside the per-item loop — `payload.bleed_mm`
(the one shared value from the batch request) passed to every item's
`inspect_shape_pdf()` call, and each item's own `info.page_box_pt` passed to its
own `extract_raster_only_pdf()` call.

## STEP 7 — SMOKE TEST

Build a synthetic shaped-sticker test PDF with a PAGE size of 212×150mm (via
reportlab, matching the established pattern from earlier stages) containing: a
raster image covering the full page, and a SMALL vector cut-contour (e.g. a
55×5mm rounded rect) positioned off-center, nowhere near the page edges.

1. Call `inspect_shape_pdf(path, bleed_mm=1.0)` directly and confirm: `dim_w ==
   212`, `dim_h == 150` (not ~57×7 from the old contour-bbox behavior),
   `actual_w == 210`, `actual_h == 148`, and the subpath's coordinates land in
   roughly the same page-relative position the contour was actually drawn at
   (not renormalized to its own bounding box).
2. Run the full `/api/generate-shape` flow (`cut_contour: true`) and confirm: the
   grid/tile size used for imposition is 212×150 (not the tiny contour size), the
   print PDF's raster content is the FULL page image (cropped to the page's own
   TrimBox/MediaBox, not a tiny region around the vector), and the contour/PLT
   output correctly traces the small shape at its correct page-relative position
   within each tile.
3. Re-run with a custom `bleed_mm=2.0` in the request and confirm `actual_w`/
   `actual_h` come back as `dim_w - 4` / `dim_h - 4`.
4. Validation: a `bleed_mm` large enough to make `actual_w`/`actual_h` non-positive
   raises a clear 400 error.
5. `/api/analyze-shape` response includes `actual_w`/`actual_h`/`bleed_mm`, and
   `dim_w`/`dim_h` equal the page size — confirm with the real HTTP route, not just
   direct function calls.
6. Batch (`/api/generate-batch-shape`) — build 2 items with genuinely different
   PAGE sizes, confirm `bleed_mm` from the shared request applies to both, and
   each item's own `dim_w`/`dim_h`/`actual_w`/`actual_h` are computed independently
   from its own page size.
7. Regression: re-run the opacity/geometric-dedup repro and the hidden-OCG-layer
   repro from the last two fixes (combine one of them with a small-vector-on-a-
   big-page file, to confirm the fixes still compose correctly with this change) —
   both should behave identically to before.
8. Regression: rectangular-mode generation (single + batch, uses
   `server/core/pdf_inspect.py`, untouched by this change) is unaffected.

Note in your summary: the CURRENT frontend (`web/app.js`, not touched by this
stage) will keep displaying `dim_w`/`dim_h` (now = page size) as the "sticker
size" in its UI until a later stage switches it to show `actual_w`/`actual_h`
instead — this is an expected, temporary interim state per the user's explicit
choice to land backend and frontend stages independently, not a bug to fix here.

## STEP 8 — UPDATE: CLAUDE.md "Останній стан"

Append ONE new entry at the end of the changelog section:

```
- **2026-09-18** — Старт нового етапу доопрацювань (бекенд + великий UI-
  рефакторинг, кілька окремих стадій, усі мержаться напряму в `main` за
  домовленістю з користувачем — без feature-гілок і PR для цього циклу робіт).

  **Стадія 1 (бекенд, розмір фігурних стікерів від сторінки PDF) — виконано.**
  Було: розмір наліпки (`dim_w`/`dim_h`) рахувався від bbox контуру порізки +
  бліда — тому файл із маленьким контуром на великій сторінці (напр. A5 212×150мм
  з контуром лише 55×5мм) розкладався за розміром контуру, а не сторінки. Стало:
  `dim_w`/`dim_h` = розмір сторінки PDF (TrimBox, якщо є, інакше MediaBox — як і в
  прямокутному режимі). Бліда — тепер параметр запиту (`bleed_mm`, дефолт 1мм,
  спільний на весь batch), використовується лише для розрахунку "фактичного"
  (нетто) розміру для відображення: `actual_w/h = dim_w/h - 2×bleed_mm`. Контур
  прив'язаний до системи координат сторінки, а не bbox+бліда — може бути будь-де
  на сторінці, будь-якого розміру. `server/core/shape_inspect.py`:
  `ShapeArtworkInfo` тепер має `actual_w`/`actual_h`/`page_box_pt` (замість
  `bleed_box_pt`); `inspect_shape_pdf(path, bleed_mm)` — новий параметр.
  `extract_raster_only_pdf` обрізає растр під `page_box_pt` (розмір сторінки)
  замість contour+bleed. `shape_print_pdf.py`/`shape_contour_pdf.py`/
  `shape_plt_writer.py` не змінювались — не мали жодних припущень про походження
  dim_w/dim_h. Фронтенд (`web/app.js`) ще НЕ підключений до нових полів
  (`actual_w`/`actual_h`/`bleed_mm`) — тимчасово показує розмір сторінки замість
  фактичного розміру, до наступних стадій UI-рефакторингу.

  Наступні стадії (заплановано, ще не почато): 2 — побатчеві параметри
  (орієнтація/сітка/кількість) по кожному файлу окремо. 3 — стрілка напряму
  подачі аркуша в плотер (`marks.py`). 4-8 — фронтенд: вкладки картки
  параметрів, уніфікація списку файлів (завжди список), попап властивостей
  файлу, зум/пан прев'ю, прибрати індикатор "вміщується", компактна
  статистика, ширини карток 2/5:3/5, відступ сайдбару "Типи розкладки".
```

## STEP 9 — COMMIT + PUSH

git add server/utils/constants.py server/core/shape_inspect.py server/models.py server/routes/analyze_shape.py server/routes/generate_shape.py server/routes/generate_batch_shape.py CLAUDE.md
git commit -m "feat(shape): size shaped stickers from the PDF page, not the cut-contour bbox"
git push origin main

## STEP 10 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (all 8 points from STEP 7)
### 📋 Known issues for next session
