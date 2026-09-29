You are working in the project root.
Do NOT modify existing working code beyond what is listed below.
Base branch: `main`. No feature branch — per standing agreement for this
project, commit and push directly to `main` (single-maintainer repo).

## CONTEXT / DESIGN DECISIONS (already made — do not re-litigate these)

A new sidebar mode "Стікерпаки" (sticker packs) is being added, alongside the
existing "Прямокутні наліпки" and "Фігурні стікери". These decisions were
confirmed with the project owner before writing this prompt:

- **File structure**: one uploaded PDF = one whole pack (same model as the
  existing "Фігурні стікери" mode already uses — that mode's file inspector
  already iterates over ALL raster images and ALL visible vector subpaths on
  the page, not just one of each, so a page containing several different
  sticker shapes with several images is already structurally accepted by
  today's code with zero changes). **Conclusion: sticker packs reuse the
  exact same `/api/analyze-shape`, `/api/generate-shape`,
  `/api/generate-batch-shape` endpoints and `server/core/shape_inspect.py`
  as "Фігурні стікери" — no new endpoints, no new inspection logic.** If
  you find a real file that this inspector rejects but that should be a
  valid sticker pack, stop and report it in the Summary rather than
  loosening the validation blindly — this prompt does not ask for that.
- **UI**: a third sidebar tab, "Стікерпаки", alongside the two existing
  ones.
- **Base-corner guide marks** (for a manual guillotine pre-cut before the
  piece goes to the plotter): exactly ONE corner (top-left), drawn ONLY in
  the final print PDF (not the template, not the .plt, not the vector
  contour PDF).
- **Bleed default 2mm / outline default ON**: these are just different
  DEFAULT values of the already-existing `bleed_mm` and `outline` fields
  when the "Стікерпаки" tab is active — still freely editable by the user,
  not locked.

Net effect: "Стікерпаки" behaves identically to "Фігурні стікери" in every
respect except three deltas — bleed default 2mm (vs 1mm), outline checkbox
defaults checked (vs unchecked), and one new optional corner-guide mark in
the print PDF. Implement it as a lightweight variant of shape mode, not a
parallel pipeline.

## STEP 1 — server/models.py — new field

Add a `corner_mark` field to both shape-mode request models (NOT the
rectangular ones — out of scope):

```python
class ShapeGenerateRequest(BaseModel):
    ...
    cut_contour: bool = False
    outline: bool = False
    # Sticker-pack mode only: one base-corner guide mark near the sheet's
    # top-left edge, for squaring up a manual guillotine pre-cut before the
    # plotter does the precise die-cut. See server/core/marks.py's
    # draw_base_corner_guide.
    corner_mark: bool = False
    bleed_mm: float = Field(default=SHAPE_BLEED_MM, ge=0)
```

```python
class ShapeBatchGenerateRequest(BaseModel):
    ...
    cut_contour: bool = False
    outline: bool = False
    corner_mark: bool = False  # same as ShapeGenerateRequest's field above
    bleed_mm: float = Field(default=SHAPE_BLEED_MM, ge=0)
```

Do NOT add this field to `BatchItem`/`GenerateRequest`/`BatchGenerateRequest`
(rectangular mode) or `ShapeBatchItem` (it's a shared/global setting for the
whole request, same as `cut_contour`/`outline`, not per-item).

## STEP 2 — server/core/marks.py — new corner-guide function

Add near the other constants/functions (after `draw_cell_outlines`):

```python
# Base-corner guide for sticker-pack mode: two short open ticks near the
# sheet's top-left corner, for squaring up a manual guillotine pre-cut
# before the piece goes to the plotter for the precise die-cut. Spec called
# for "7-8mm from the sheet edge" — picked the midpoint. Deliberately
# open/thin ticks (crop-mark style), not filled L-brackets, so they read as
# visually distinct from draw_registration_marks' filled corner brackets
# even though they sit close to them at the default mark_offset=9mm (6mm
# tick length keeps them clear of the registration mark's own 9mm-offset
# start — re-verify this in the smoke test if mark_offset is ever set very
# small).
CORNER_GUIDE_OFFSET_MM = 7.5
CORNER_GUIDE_LEN_MM = 6.0


def draw_base_corner_guide(c, grid: Grid) -> None:
    """Two short perpendicular ticks near the sheet's top-left corner —
    sticker-pack mode only, print PDF only (see
    server/core/shape_print_pdf.py). Caller must set stroke color first
    (e.g. c.setStrokeColor(K100)), same convention as draw_registration_marks.
    """
    def pt(v: float) -> float:
        return v * MM

    o = CORNER_GUIDE_OFFSET_MM
    length = CORNER_GUIDE_LEN_MM
    sheet_h = grid.sheet_h
    c.setLineWidth(pt(0.15))
    c.line(pt(0), pt(sheet_h - o), pt(length), pt(sheet_h - o))  # tick along the top edge
    c.line(pt(o), pt(sheet_h), pt(o), pt(sheet_h - length))       # tick along the left edge
```

## STEP 3 — server/core/shape_print_pdf.py — draw it when requested

Add a `corner_mark: bool = False` parameter, and call the new function on
the SAME internal marks-only canvas that already draws
`draw_registration_marks` (bottom layer — this mark sits near the sheet
edge, well outside the tiled artwork grid, so layer order doesn't matter
here the way it does for the outline frame).

Change the function signature:
```python
def generate_shape_print_pdf(
    output_path: str, raster_only_pdf_path: str, grid: Grid,
    outline: bool = False, corner_mark: bool = False,
) -> None:
```

Right after the existing:
```python
        draw_registration_marks(marks_canvas, grid)
```
add:
```python
        if corner_mark:
            from server.core.marks import draw_base_corner_guide
            draw_base_corner_guide(marks_canvas, grid)
```
(both calls share the same `marks_canvas.setStrokeColor(K100)` already set
just above — no extra color setup needed).

Do not change anything else in this file (the existing `outline` top-layer
logic from a previous change stays exactly as-is).

## STEP 4 — routes — thread `corner_mark` through

**`server/routes/generate_shape.py`** — change:
```python
        generate_shape_print_pdf(print_path, raster_only_pdf, grid, outline=payload.outline)
```
to:
```python
        generate_shape_print_pdf(print_path, raster_only_pdf, grid, outline=payload.outline, corner_mark=payload.corner_mark)
```

**`server/routes/generate_batch_shape.py`** — change:
```python
            generate_shape_print_pdf(print_path, raster_only_pdf, grid, outline=payload.outline)
```
to:
```python
            generate_shape_print_pdf(print_path, raster_only_pdf, grid, outline=payload.outline, corner_mark=payload.corner_mark)
```

## STEP 5 — web/index.html — third sidebar tab

In the sidebar (currently `#tab-rect` and `#tab-shape`), add a third button
right after `#tab-shape`:

```html
    <button type="button" class="sidebar-tab" id="tab-rect">Прямокутні наліпки</button>
    <button type="button" class="sidebar-tab" id="tab-shape">Фігурні стікери</button>
    <button type="button" class="sidebar-tab" id="tab-pack">Стікерпаки</button>
```
(keep whichever of the first two currently has `is-active` — don't move
that class).

## STEP 6 — web/app.js — the mode itself

### 6a. New state + element reference

Near `let shapeMode = false;`, add:
```js
let isStickerPack = false; // only meaningful when shapeMode is true — "Стікерпаки" tab
```
Near `const tabShapeBtn = el("tab-shape");`, add:
```js
const tabPackBtn = el("tab-pack");
```

### 6b. `switchMode` — accept a mode string instead of a boolean

Current:
```js
async function switchMode(toShapeMode) {
  if (toShapeMode === shapeMode) return;
  await startNewTask(); // don't leave stale items/preview from the other mode on screen
  shapeMode = toShapeMode;
  tabRectBtn.classList.toggle("is-active", !shapeMode);
  tabShapeBtn.classList.toggle("is-active", shapeMode);
  bleedRow.hidden = !shapeMode;
}
tabRectBtn.addEventListener("click", () => switchMode(false));
tabShapeBtn.addEventListener("click", () => switchMode(true));
```

Replace with:
```js
async function switchMode(mode) {
  // mode: "rect" | "shape" | "pack"
  const toShapeMode = mode !== "rect";
  const toPack = mode === "pack";
  if (toShapeMode === shapeMode && toPack === isStickerPack) return;
  // Set the mode flags BEFORE calling startNewTask() — it reads isStickerPack
  // to pick the right bleed/outline defaults for the mode being switched TO.
  shapeMode = toShapeMode;
  isStickerPack = toPack;
  await startNewTask(); // don't leave stale items/preview from the other mode on screen
  tabRectBtn.classList.toggle("is-active", mode === "rect");
  tabShapeBtn.classList.toggle("is-active", mode === "shape");
  tabPackBtn.classList.toggle("is-active", mode === "pack");
  bleedRow.hidden = !shapeMode;
}
tabRectBtn.addEventListener("click", () => switchMode("rect"));
tabShapeBtn.addEventListener("click", () => switchMode("shape"));
tabPackBtn.addEventListener("click", () => switchMode("pack"));
```

### 6c. `startNewTask()` — mode-dependent bleed/outline defaults

Find these two lines:
```js
  appliedParams = {
    sheetName: "SRA3", sheetW: 0, sheetH: 0,
    markOffset: 0, fieldMargin: 0,
    bleedMm: 1.0,
  };
```
and, further down:
```js
  bleedMmInput.value = "1";
  paramsPendingHint.hidden = true;

  cutContourCheckbox.checked = true;
  outlineCheckbox.checked = false;
```

Replace both spots so the bleed/outline defaults depend on `isStickerPack`
(computed once, used in both places):

```js
  const bleedDefault = isStickerPack ? 2.0 : 1.0;
  appliedParams = {
    sheetName: "SRA3", sheetW: 0, sheetH: 0,
    markOffset: 0, fieldMargin: 0,
    bleedMm: bleedDefault,
  };
```//...
```js
  bleedMmInput.value = String(bleedDefault);
  paramsPendingHint.hidden = true;

  cutContourCheckbox.checked = true;
  outlineCheckbox.checked = isStickerPack;
```
(`bleedDefault` is declared once near the top of the function, before the
`appliedParams = {...}` assignment, and reused at the `bleedMmInput.value`
line below it — don't declare it twice.)

### 6d. `generateShapeBatch()` — send `corner_mark`

Current payload:
```js
async function generateShapeBatch() {
  const payload = {
    items: items.map((it) => ({
      upload_id: it.upload_id, orientation: it.orientation, cols: it.cols, rows: it.rows, quantity: it.quantity,
    })),
    sheet_name: appliedParams.sheetName,
    sheet_w: appliedParams.sheetW,
    sheet_h: appliedParams.sheetH,
    mark_offset: appliedParams.markOffset,
    field_margin: appliedParams.fieldMargin,
    order: orderNumberInput.value.trim(),
    material: effectiveMaterial(),
    cut_contour: cutContourCheckbox.checked,
    bleed_mm: appliedParams.bleedMm,
  };
  ...
}
```
Add `corner_mark: isStickerPack,` to the payload object (e.g. right after
`bleed_mm: appliedParams.bleedMm,`).

### 6e. Preview — show the corner guide too

In `renderLayout(layout, artwork, deform)`, right after the existing corner
registration-marks loop (`for (const { cx, cy, dirX, dirY } of corners) { ... }`
block), add:

```js
  if (isStickerPack) {
    // Visual match for server/core/marks.py's draw_base_corner_guide — keep
    // these two numbers in sync with CORNER_GUIDE_OFFSET_MM/CORNER_GUIDE_LEN_MM
    // there if they ever change.
    const guideOffset = 7.5, guideLen = 6;
    previewSvg.appendChild(svgEl("line", {
      x1: 0, y1: guideOffset, x2: guideLen, y2: guideOffset,
      stroke: "#111111", "stroke-width": strokeW * 0.4,
    }));
    previewSvg.appendChild(svgEl("line", {
      x1: guideOffset, y1: 0, x2: guideOffset, y2: guideLen,
      stroke: "#111111", "stroke-width": strokeW * 0.4,
    }));
  }
```

Do NOT change anything else in this file.

## STEP 7 — SMOKE TEST

1. Restart the server. Confirm the sidebar now shows three tabs: "Прямокутні
   наліпки", "Фігурні стікери", "Стікерпаки" — clicking each switches mode
   and resets the file list/preview like it already does today between the
   first two.

2. Open "Стікерпаки" — confirm before uploading anything: bleed field shows
   `2`, and the outline checkbox (Tab 2) is checked. Switch to "Фігурні
   стікери" — confirm bleed resets to `1` and outline unchecks. Switch back
   and forth a couple times to confirm there's no state leakage between
   modes (this exercises the STEP 6b/6c reordering).

3. Upload a shape-mode test PDF (any that already works in "Фігурні
   стікери") into "Стікерпаки" mode, generate a batch. Open the resulting
   print PDF (e.g. render with PyMuPDF) and confirm: the outline frame is
   present (checkbox was on by default), and near the top-left corner there
   are two short open ticks distinct from the four filled corner
   registration-mark brackets — not overlapping them. Also confirm neither
   the template folder nor the .plt nor any cut-contour PDF in the same zip
   contain this new mark (print-PDF-only, per spec).

4. Generate the same test file from "Фігурні стікери" mode (not packs) —
   confirm the print PDF does NOT have the corner-guide ticks (since
   `corner_mark` is never sent true from that tab), confirming the feature
   is correctly pack-only, not shape-mode-wide.

5. Live preview: with a file selected in "Стікерпаки" mode, confirm the two
   corner-guide ticks appear in the on-screen SVG preview near the top-left
   corner too, and do NOT appear when the same file is viewed under "Фігурні
   стікери".

6. Regression: single-file `/api/generate-shape` still works (with and
   without `corner_mark` in the request body — it's optional/defaults
   false), and every "Фігурні стікери" smoke-test point from earlier
   sessions still passes unchanged.

## STEP 8 — CLAUDE.md

Append a short entry to "Останній стан" describing the new "Стікерпаки"
sidebar mode: what it is (same pipeline as "Фігурні стікери", different
bleed/outline defaults, new print-PDF-only base-corner guide mark), and the
new `corner_mark` field.

## STEP 9 — COMMIT + PUSH

```
git add server/models.py server/core/marks.py server/core/shape_print_pdf.py server/routes/generate_shape.py server/routes/generate_batch_shape.py web/index.html web/app.js CLAUDE.md
git commit -m "feat: add Стікерпаки sidebar mode (2mm bleed/outline-on defaults, base-corner guide mark)"
git push origin main
```

## STEP 10 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🔴 Not implemented
### 🧪 Smoke test results (all 6 points)
### 📋 Known issues for next session
