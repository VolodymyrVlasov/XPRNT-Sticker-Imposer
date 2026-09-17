You are working in the project root. This is stage 2 of the same multi-stage
redesign as the previous stage (backend + a later frontend overhaul — this
stage is backend-only, like stage 1). Pull latest `main` first — it must
already contain stage 1's commit (shaped-sticker sizing from the PDF page,
`bleed_mm` on `ShapeGenerateRequest`/`ShapeBatchGenerateRequest`, `actual_w`/
`actual_h` on `ShapeAnalyzeResponse`). If it doesn't, stop and report — don't
proceed on top of a stale base.

Per the user's explicit instruction, this whole line of work (every stage,
regardless of size) commits and pushes directly to `main` — no feature
branches, no PRs, for anything in this effort.

## GOAL — orientation / grid / quantity must be per-file in batch mode, not shared

Today, `BatchGenerateRequest` and `ShapeBatchGenerateRequest` each carry a
single shared `orientation` and `quantity` for the whole batch (`server/
models.py`), and neither batch item type carries `cols`/`rows` at all — batch
mode is always full auto-fit, one grid size/orientation/quantity applied
uniformly to every uploaded file. That's wrong: a real batch upload normally
mixes different sticker sizes, so forcing one orientation and one grid on
every item makes no sense, and each file naturally needs its own print
quantity too. This was confirmed with the user: orientation and grid
(cols/rows) must be resolved independently per item, quantity must be set
per item (it's moving into a future per-file "properties" popup in the UI —
this stage only does the backend/API side of that), and the only two things
that stay genuinely shared across a whole batch are the sheet/margins/
material/order fields and the `cut_contour` checkbox (already shared, stays
shared, default unchanged).

This makes both batch item models finally mirror the fields their existing
single-file counterparts (`GenerateRequest`/`ShapeGenerateRequest`) already
have per-request — `orientation`/`cols`/`rows`/`quantity` — since for a
single file "per request" already means "per item". No new grid math is
needed: `resolve_grid()` (`server/core/layout.py`) already accepts optional
`orientation`/`cols`/`rows` and auto-fits whatever is left `None`/0 — batch
mode just wasn't passing those through per item before.

⚠️ Expected, temporary side effect: `web/app.js` (not touched by this stage)
still sends the OLD shape — one shared `orientation`/`quantity` at the batch
request's top level, nothing per item. After this stage, both batch
endpoints will reject that payload with a 422 (missing required per-item
`quantity`, and unknown/removed top-level fields are just ignored by
FastAPI, which is harmless, but the missing required per-item field is not).
This is expected and will be fixed by a later frontend stage — single-file
(non-batch) generation is completely unaffected and keeps working today.
Verify this stage with direct API calls (Python `requests`/`httpx` or curl
against the running `uvicorn` server), not by clicking through the current
UI's batch mode.

## STEP 1 — UPDATE: server/models.py

Change `BatchItem` and `BatchGenerateRequest`:

```python
class BatchItem(BaseModel):
    upload_id: str
    dim_w: float = Field(gt=0)
    dim_h: float = Field(gt=0)
    orientation: str | None = None
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    quantity: int = Field(gt=0)


class BatchGenerateRequest(BaseModel):
    items: list[BatchItem]
    sheet_name: str
    sheet_w: float = Field(gt=0)
    sheet_h: float = Field(gt=0)
    mark_offset: float = Field(ge=0)
    field_margin: float = Field(ge=0)
    order: str
    material: str
    cut_contour: bool = False
```

(`orientation` and `quantity` removed from `BatchGenerateRequest` — they now
live only on `BatchItem`, one value per file.)

Change `ShapeBatchItem` and `ShapeBatchGenerateRequest` the same way (keep
`ShapeBatchGenerateRequest.bleed_mm` — added in stage 1 — unchanged; it's
correctly shared across the whole batch, same as `sheet_name`/`material`):

```python
class ShapeBatchItem(BaseModel):
    upload_id: str
    orientation: str | None = None
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    quantity: int = Field(gt=0)


class ShapeBatchGenerateRequest(BaseModel):
    items: list[ShapeBatchItem]
    sheet_name: str
    sheet_w: float = Field(gt=0)
    sheet_h: float = Field(gt=0)
    mark_offset: float = Field(ge=0)
    field_margin: float = Field(ge=0)
    order: str
    material: str
    cut_contour: bool = False
    bleed_mm: float = Field(default=SHAPE_BLEED_MM, ge=0)
```

Leave `GenerateRequest`/`ShapeGenerateRequest` (the single-file models)
completely untouched — they already have per-request orientation/cols/rows/
quantity and are not part of this change.

## STEP 2 — UPDATE: server/routes/generate_batch.py

Inside the per-item loop, resolve the grid from the ITEM's own orientation/
cols/rows instead of the request's:

```python
grid = resolve_grid(
    item.dim_w, item.dim_h, payload.sheet_w, payload.sheet_h,
    payload.mark_offset, payload.field_margin, 0,
    orientation=item.orientation, cols=item.cols, rows=item.rows,
)
```

And use the item's own quantity for the sheets-needed calculation:

```python
stickers_per_sheet = grid.count
sheets_needed = math.ceil(item.quantity / stickers_per_sheet)
actual_qty = sheets_needed * stickers_per_sheet
```

Everything else in this route — the template-folder dedup-by-`folder_name`
logic, the zip assembly — is unchanged and still correct as-is: it already
keys purely off the RESULTING grid's own dimensions/cols/rows/orientation
(via `build_folder_name`), so two items that happen to resolve to the same
final grid still correctly share one template/PLT/contour set, regardless of
whether that grid came from auto-fit or an explicit per-item override.

## STEP 3 — UPDATE: server/routes/generate_batch_shape.py

Same two changes, applied in its per-item loop:

```python
grid = resolve_grid(
    info.dim_w, info.dim_h, payload.sheet_w, payload.sheet_h,
    payload.mark_offset, payload.field_margin, 0,
    orientation=item.orientation, cols=item.cols, rows=item.rows,
)
```

```python
stickers_per_sheet = grid.count
sheets_needed = math.ceil(item.quantity / stickers_per_sheet)
actual_qty = sheets_needed * stickers_per_sheet
```

(This route currently has no cols/rows plumbing at all — batch shape mode
was always forced full auto-fit; this adds the same manual-override
capability the single-file `/api/generate-shape` route already has.)
Everything else — `inspect_shape_pdf(artwork_path, payload.bleed_mm)` from
stage 1, the no-dedup-per-item zip assembly, `extract_raster_only_pdf` — is
unchanged.

## STEP 4 — UPDATE: update the two route docstring-ish inline comments

Both routes currently have a comment above the `resolve_grid(...)` call
saying something like "Batch mode always auto-fits ... — no per-item manual
grid/size override". That comment is now false — update it to reflect the
new per-item override capability, e.g.:

```python
# Each item resolves its own grid independently — explicit per-item
# orientation/cols/rows win, anything left unset auto-fits for that item
# alone. No gap in batch mode (unchanged).
```

## STEP 5 — SMOKE TEST

Use direct HTTP calls against the running server (Python `requests`/`httpx`
or curl) — not the browser UI, per the note above.

1. `/api/generate-batch` with 2 items of genuinely different `dim_w`/`dim_h`,
   one with an explicit `orientation`/`cols`/`rows` override and one left
   `None` (auto-fit); each with a different `quantity`. Confirm: both items'
   grids resolve independently (the overridden one respects the explicit
   values, the other auto-fits), each item's own `quantity` drives its own
   `sheets_needed`/`actual_qty` in its print filename, and the resulting zip
   contains correct per-item print PDFs plus correctly-deduped template
   folders.
2. Two items that, after resolution, land on the IDENTICAL final grid (same
   cell size/cols/rows/orientation) — confirm they still share one template/
   PLT/contour folder (dedup still works).
3. Omit `quantity` on an item entirely — confirm FastAPI returns a 422 (it's
   now required per item, no default).
4. `/api/generate-batch-shape` — same two-item test as point 1, plus confirm
   `bleed_mm` (still request-level, from stage 1) applies identically to
   every item regardless of each item's own orientation/cols/rows override.
5. `/api/generate-batch-shape` — one item with an explicit `cols`/`rows` that
   does NOT fit the sheet — confirm the existing "не вміщується" 400 error
   still fires correctly (this path already existed for the single-file
   route; confirm it now also works per-item in batch).
6. Regression: single-file `/api/generate` and `/api/generate-shape` (not
   touched by this stage) still work exactly as before.
7. Confirm (and note in your summary, don't fix) that a batch request built
   the OLD way — shared top-level `orientation`/`quantity`, no per-item
   `quantity` — now fails with a 422, matching the expected temporary
   breakage called out above.

## STEP 6 — UPDATE: CLAUDE.md "Останній стан"

Read the current file first — stage 1 added a dated entry ending with a
"Наступні стадії" list that starts "2 — побатчеві параметри...". Add a new
sub-bullet under that same entry (or a new dated entry if today's date has
moved on from stage 1's) documenting stage 2's completion, and trim stage 2
off the front of the "Наступні стадії" list (renumber so it now starts from
3). Something in this spirit:

```
  **Стадія 2 (бекенд, побатчеві параметри) — виконано.** Було: у batch-режимі
  орієнтація, сітка (cols/rows) і кількість були спільними на весь batch —
  один розмір/орієнтація застосовувались до всіх завантажених файлів. Стало:
  `BatchItem`/`ShapeBatchItem` тепер мають власні `orientation`/`cols`/`rows`/
  `quantity` (як і в одиночному режимі), `orientation`/`quantity` прибрано з
  рівня `BatchGenerateRequest`/`ShapeBatchGenerateRequest` (лишились спільними
  тільки аркуш/відступи/матеріал/замовлення й чекбокс контуру різу).
  `generate_batch.py`/`generate_batch_shape.py` рахують сітку й
  sheets_needed окремо для кожного файлу. ⚠️ Тимчасовий ефект: поточний
  фронтенд (`web/app.js`) ще шле старий формат запиту (спільні orientation/
  quantity) — batch-режим через UI поверне 422, доки не підключиться
  фронтенд-стадія з попапом властивостей файлу. Одиночний режим не
  зачеплений.

  Наступні стадії (заплановано, ще не почато): 3 — стрілка напряму подачі
  аркуша в плотер (`marks.py`). 4-8 — фронтенд: вкладки картки параметрів,
  уніфікація списку файлів (завжди список), попап властивостей файлу (сітка/
  орієнтація/кількість), зум/пан прев'ю, прибрати індикатор "вміщується",
  компактна статистика, ширини карток 2/5:3/5, відступ сайдбару "Типи
  розкладки".
```

## STEP 7 — COMMIT + PUSH

```
git add server/models.py server/routes/generate_batch.py server/routes/generate_batch_shape.py CLAUDE.md
git commit -m "feat(batch): resolve orientation/grid/quantity per batch item instead of sharing one for the whole batch"
git push origin main
```

## STEP 8 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (all 7 points from STEP 5)
### 📋 Known issues for next session
