You are working in the project root. This is a bugfix to the already-merged shaped-
stickers feature, found by the user testing with a REAL production file. Pull latest
main first (should include today's earlier shape_inspect.py fixes — opacity/dedup,
and the fmt_dim rounding fix — if not already there).

This is a small, single-file task: per this project's convention for micro/small
tasks, commit directly to main, no feature branch, no PR needed.

## GOAL — root cause (already diagnosed precisely, don't re-derive it)

User reported: a Rectangle/Ellipse-type vector object isn't recognized as the cut
contour ("контур не знайдено" validation error fires), but converting the same
object to a Path in Illustrator fixes it. This looked like a shape-type issue but
isn't — I inspected the real file with PyMuPDF and pikepdf and found the actual
cause:

The file has two Illustrator layers (Optional Content Groups / OCGs): "Дизайн"
(has the raster artwork) and "Різ" (has the cut-contour rectangle). The "Різ" layer
is set OFF by default — `/OCProperties/D/OFF` explicitly lists it — i.e. it's a
hidden layer in Illustrator (a very plausible, likely-recurring real workflow:
designers hide the cut-line layer for a clean working view while still expecting
prepress/plotter tooling to read its geometry).

PyMuPDF's content-stream walk respects the PDF's default OCG visibility and
silently omits a hidden layer's content ENTIRELY:
- `page.get_drawings()` / `page.get_drawings(extended=True)` — both return
  nothing for the hidden layer's path, no trace of it at all (unlike the earlier
  opacity=0 bug, where the invisible copy was at least detectable as a near-zero-
  opacity draw — a hidden-OCG path isn't reported as a draw operation in any form).
- `page.get_image_info(xrefs=True)` — same issue, would apply symmetrically if the
  raster/design layer were ever the one hidden instead. (`page.get_images(full=True)`
  does NOT have this problem — it lists XObjects regardless of OCG state — but
  `extract_raster_only_pdf()` uses `get_image_info(xrefs=True)`, which DOES.)

I confirmed the fix works: `doc.get_ocgs()` lists every OCG's xref and on/off
state; forcing every OCG's xref into the `on` list via `doc.set_layer(-1,
on=[...], off=[])`, then round-tripping through `doc.tobytes()` + reopening
(critically: `doc.set_layer()` alone updates the OCG config dict but
get_drawings()/get_image_info() on the SAME live Document object do NOT pick up
the change — only a freshly re-parsed document does), makes the hidden layer's
content show up correctly and completely — verified item-for-item against the raw
content stream.

This is a *visibility* decision only, not a *layer name* filter — we are NOT
requiring the layer be named "Різ"/"Cut"/anything in particular, staying
consistent with this feature's original stage-1 design ("every vector path in the
file counts, no color/layer filtering"). We're simply making sure a layer being
toggled off in Illustrator doesn't cause its geometry to be silently dropped.

The fix belongs in `server/core/shape_inspect.py`, touching both
`inspect_shape_pdf()` (vector contour + validation) and `extract_raster_only_pdf()`
(raster extraction) via one new shared helper, since both currently open the PDF
with a plain `fitz.open(path)` that's subject to this OCG-visibility blind spot.

## STEP 1 — UPDATE: server/core/shape_inspect.py

Add a shared helper (near the top of the file, after the existing module-level
constants, before `_points_close`):

```python
def _load_with_all_layers_visible(path: str) -> "fitz.Document":
    """Open the PDF with every Optional Content Group (Illustrator "layer")
    forced to visible, regardless of the file's own default layer-visibility
    state.

    Real client files routinely have a layer toggled OFF/hidden in Illustrator —
    most commonly the cut-contour layer, hidden for a clean design view while
    still expected to be read by prepress/plotter tooling. Verified on a real
    client file: a rounded-rect cut contour on a layer literally named "Різ"
    (OFF by default in /OCProperties/D/OFF) was completely invisible to
    page.get_drawings() — no trace of it at all, even in extended mode — while
    the identical geometry on a visible layer was found normally.
    page.get_image_info(xrefs=True) (used by extract_raster_only_pdf below) has
    the same blind spot, so this is applied to raster extraction too, in case
    the design/raster layer is ever the hidden one instead.

    This only affects layer VISIBILITY, never which paths count as contour
    geometry — every vector path in the file still counts regardless of which
    layer it's on or what that layer is named, per this module's original
    design (see the module docstring).

    Note: doc.set_layer() alone updates the OCG config dict, but
    get_drawings()/get_image_info() on the SAME live Document object do not
    pick up the change — only a freshly (re)parsed document does, hence the
    tobytes() + reopen round-trip below.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    ocgs = doc.get_ocgs()
    if not ocgs:
        return doc
    doc.set_layer(-1, on=list(ocgs.keys()), off=[])
    buf = doc.tobytes()
    doc.close()
    return fitz.open(stream=buf, filetype="pdf")
```

Then:

1. In `extract_raster_only_pdf()`, replace `src = fitz.open(path)` with
   `src = _load_with_all_layers_visible(path)` (keep it in the same place,
   outside the `try:` block, exactly as the original `fitz.open(path)` call was —
   no other structural change to this function).

2. In `inspect_shape_pdf()`, replace:
   ```python
   try:
       doc = fitz.open(path)
   except Exception as exc:
       raise ValueError(f"Не вдалося прочитати PDF: {exc}") from exc
   ```
   with:
   ```python
   try:
       doc = _load_with_all_layers_visible(path)
   except Exception as exc:
       raise ValueError(f"Не вдалося прочитати PDF: {exc}") from exc
   ```

Nothing else in either function needs to change — both already operate on
whatever `doc`/`page` object they're handed, and this just changes how that
object is constructed. This composes cleanly with the existing opacity-based
`_visible_drawings()` filter and the geometric dedup from the earlier fix — layer
visibility (this fix) and paint opacity (the earlier fix) are independent PDF
mechanisms, so forcing layers visible does not undo or interfere with excluding a
genuinely 0%-opacity duplicate path.

## STEP 2 — SMOKE TEST

1. Build a synthetic shaped-sticker test PDF (reuse the established rounded-rect +
   bezier-corners + 1mm-bleed pattern) via pikepdf, where the cut-contour path's
   marked-content section references an OCG that is explicitly listed in
   `/OCProperties/D/OFF` (i.e. genuinely hidden by default — not merely low
   opacity, an actual layer-visibility toggle). Confirm:
   - On the CURRENT (pre-fix) code, `inspect_shape_pdf()` raises the "контур не
     знайдено" ValueError on this file (reproduces the reported bug exactly).
   - After the fix, `inspect_shape_pdf()` succeeds and returns exactly 1 subpath
     with the expected geometry (matching what a visible-layer version of the
     same file would produce).
2. Build a second variant where instead the RASTER/design layer is the hidden one
   (cut-contour layer visible) — confirm `extract_raster_only_pdf()` still finds
   and correctly crops the image after the fix (this would previously have failed
   with "растрового шару не знайдено" even though the image genuinely exists).
3. Run the full `/api/generate-shape` flow end-to-end on the hidden-cut-layer file,
   confirm a correct zip comes out (print PDF, PLT, optional contour PDF) with the
   right geometry.
4. Regression — re-run the opacity/dedup smoke tests from the earlier fix (an
   invisible-via-0%-opacity duplicate path, both on ordinary visible layers) and
   confirm they still behave identically (still deduped/excluded correctly) — i.e.
   this change doesn't interact badly with that one.
5. Full regression pass: existing single-file and batch shaped-sticker generation
   (synthetic PDFs without hidden layers) produce identical output to before this
   fix, and rectangular-mode generation (single + batch, which uses
   `server/core/pdf_inspect.py`, untouched by this change) is unaffected.

Paste the before/after result on the hidden-cut-layer repro file in your summary —
this is the concrete evidence that matters most here.

## STEP 3 — UPDATE: CLAUDE.md "Останній стан"

Append ONE new entry at the end of the changelog section (after today's existing
entries — do not edit those, add a new one below):

```
- **2026-09-17** — Виправлено: контур порізки на прихованому шарі Illustrator не
  розпізнавався. Причина (знайдено на реальному файлі клієнта): цей шар PDF мав
  два Illustrator-шари ("Дизайн" з растром, "Різ" з контуром порізки), і шар
  "Різ" був вимкнений за замовчуванням (`/OCProperties/D/OFF`) — типовий
  робочий процес: дизайнер ховає шар з лінією різу для чистого вигляду макета.
  `page.get_drawings()` PyMuPDF повністю ігнорує вміст прихованого шару (на
  відміну від невидимості через прозорість із попереднього фіксу — тут не
  лишається взагалі жодного сліду, навіть у extended-режимі). Це НЕ пов'язано з
  типом об'єкта (Rectangle/Ellipse проти Path), хоча спочатку виглядало так —
  конвертація в Path, ймовірно, "допомагала" лише тому, що для редагування
  об'єкта на прихованому шарі в Illustrator доводиться тимчасово зробити шар
  видимим. Виправлено в `server/core/shape_inspect.py`: новий спільний хелпер
  `_load_with_all_layers_visible()` примусово вмикає всі Optional Content
  Groups (`doc.set_layer()` + обов'язковий tobytes()+reopen, бо зміна не
  застосовується до вже відкритого документа) перед аналізом — використовується
  і в `inspect_shape_pdf` (контур), і в `extract_raster_only_pdf` (растр, та сама
  вразливість там теж є, про всяк випадок). Це стосується лише видимості шару,
  не назви чи кольору — усі вектори в файлі й далі рахуються контуром незалежно
  від того, на якому шарі вони лежать, як і було задумано з першого етапу.
```

Include this file in the same commit as the code fix.

## STEP 4 — COMMIT + PUSH

git add server/core/shape_inspect.py CLAUDE.md
git commit -m "fix(shape): read cut-contour/raster geometry regardless of hidden Illustrator layers"
git push origin main

## STEP 5 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (before/after on the hidden-layer repro, hidden-raster-layer variant, opacity/dedup regression, full regression pass)
### 📋 Known issues for next session
