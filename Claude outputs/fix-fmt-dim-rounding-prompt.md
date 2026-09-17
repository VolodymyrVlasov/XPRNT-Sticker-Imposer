You are working in the project root. This is a small, standalone fix — pull latest
main first (it should already include today's earlier shape-inspect opacity/dedup
fix, commit a04b1d4 or later).

This is a small, single-function task: per this project's convention for
micro/small tasks, commit directly to main, no feature branch, no PR needed.

## GOAL

Dimensions shown in generated filenames and the rectangular-mode template PDF's
printed caption are currently too precise — e.g. "49.38x54.03" — which is not a
meaningful precision for a human-readable label on the shop floor. Round these
DISPLAY strings to the nearest whole millimetre. This must be purely cosmetic: the
actual layout/imposition/cut geometry (grid cell sizes, coordinates used for
printing and cutting) must NOT change in precision anywhere — only the formatted
text shown in filenames and the on-sheet caption.

## Context you need

`fmt_dim()` in `server/utils/naming.py` is the single formatting function behind
every one of these display strings — used by `build_folder_name()` (PLT/contour
filename AND the `title` string handed to `generate_template_pdf()`, which draws it
as the on-sheet caption in `server/core/pdf_template.py`) and, directly, by the
`size_str` construction in both `server/routes/generate.py` and
`server/routes/generate_shape.py` (and transitively their batch counterparts,
`generate_batch.py` / `generate_batch_shape.py`, which call the same naming
helpers). Fixing `fmt_dim()` alone therefore fixes every one of these places at
once — no other file needs to change.

Currently:

```python
def fmt_dim(v: float) -> str:
    """Drop trailing '.0' for whole-number dimensions."""
    return str(int(v)) if v == int(v) else str(round(v, 2))
```

## STEP 1 — UPDATE: server/utils/naming.py

Replace `fmt_dim()` so it rounds to the nearest whole millimetre, using
round-half-up (not Python's built-in `round()`, which does banker's/round-half-to-
even rounding — e.g. `round(49.5)` gives 50 as expected but `round(48.5)` gives 48,
not 49 — round-half-up is the less surprising choice for a shop-floor label):

```python
import math


def fmt_dim(v: float) -> str:
    """Round to the nearest whole millimetre for display in filenames and the
    on-sheet template caption — e.g. 49.38 -> "49". This only affects the
    formatted label string; every actual layout/print/cut coordinate elsewhere
    in the app keeps full float precision, untouched by this function.
    Round-half-up (not Python's banker's-rounding `round()`) so e.g. 48.5 -> 49,
    not 48 — the less surprising behavior for a human-readable label.
    """
    return str(math.floor(v + 0.5))
```

(Adjust the exact implementation if you find a cleaner idiom, but keep the
round-half-up behavior and the "returns a whole-number string, no decimals ever"
contract — callers like `build_folder_name()`'s `"PLT {fmt_dim(short_side)}x..."`
and the `size_str` f-strings in generate.py/generate_shape.py just interpolate
whatever `fmt_dim()` returns, so no caller changes are needed.)

Note this also affects the `gap{fmt_dim(gap)}` segment in `build_folder_name()`
(rectangular mode with a nonzero gap) — that's expected, same function, same
reasoning; gap values in practice are already whole millimetres so this is a no-op
for existing use, just flag it in your summary in case that's ever not true.

## STEP 2 — SMOKE TEST

Using the real running server:

1. Rectangular mode: analyze/layout an artwork whose fitted cell size comes out
   fractional (pick sheet/margins that force this, e.g. via manual cols/rows
   override or an odd artwork size) and generate. Confirm the PLT filename, the
   contour-PDF filename (if requested), the print PDF filename, and the zip
   filename all show whole-mm dimensions (e.g. "49x54", not "49.38x54.03"). Open
   the generated template PDF and confirm the printed caption text also shows the
   rounded whole-mm value (via PyMuPDF: `page.get_text()` or search for the string).
2. Confirm the actual grid geometry is unaffected: `grid.cell_w`/`grid.cell_h`
   (or wherever you can inspect this — e.g. via `/api/layout`'s response, or by
   comparing the print PDF's actual tile placement/size against a run from before
   this change) still reflect the full-precision value, not the rounded one —
   i.e. this change is display-only, verify it didn't leak into the actual
   coordinates used for tiling/cutting.
3. Shaped-stickers mode: same check — build a synthetic shaped-sticker PDF whose
   `dim_w`/`dim_h` come out fractional (e.g. 42.38 x 31.91), generate via
   `/api/generate-shape`, confirm the PLT/contour/print/zip filenames show whole-mm
   dimensions, and confirm the actual cut/print geometry (subpath coordinates, tile
   placement) is unaffected — only the filename string changed.
4. Batch mode (both rectangular and shaped): confirm filenames in a batch-generated
   zip show the same whole-mm rounding per item.
5. Round-half-up sanity check: construct a case where the fractional dimension is
   exactly x.5 (e.g. 49.5) and confirm it rounds UP to 50, not down to 49 (i.e.
   Python's plain `round()` was NOT used).

Paste example before/after filenames in your summary.

## STEP 3 — UPDATE: CLAUDE.md "Останній стан"

Append ONE short entry at the end of the changelog section (after the existing
2026-09-17 entries — do not edit those, add a new one below):

```
- **2026-09-17** — Округлено розмір наліпки у назвах файлів і в підписі на
  шаблон-PDF (прямокутний режим) до цілого міліметра (round-half-up), напр.
  "49.38x54.03" → "49x54". Це суто косметична зміна рядка `fmt_dim()`
  (`server/utils/naming.py`) — фактична геометрія розкладки й порізки (координати
  друку/різу) точність не втрачає, округлення стосується лише тексту в
  назві файлу й підписі на аркуші. Стосується і прямокутного, і фігурного
  режимів (обидва використовують ту саму функцію), і одиночного, і batch.
```

Include this file in the same commit as the code fix.

## STEP 4 — COMMIT + PUSH

git add server/utils/naming.py CLAUDE.md
git commit -m "fix(naming): round displayed sticker size to whole mm in filenames/captions"
git push origin main

## STEP 5 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (example before/after filenames, round-half-up check, confirmation that actual geometry precision is untouched)
### 📋 Known issues for next session
