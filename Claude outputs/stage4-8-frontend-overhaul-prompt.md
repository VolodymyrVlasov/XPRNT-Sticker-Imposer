You are working in the project root. This is stages 4-8 of the same multi-
stage redesign as the previous three stages, combined into one prompt (the
user asked for the frontend overhaul as a single pass rather than 5 separate
hand-offs). Pull latest `main` first — it must already contain stage 1
(shape sizing from PDF page + `bleed_mm`/`actual_w`/`actual_h`), stage 2
(per-batch-item `orientation`/`cols`/`rows`/`quantity` on `BatchItem`/
`ShapeBatchItem`), and stage 3 (printed feed-direction arrow). If it doesn't,
stop and report — don't proceed on top of a stale base.

Per the user's explicit instruction, this whole line of work (every stage,
regardless of size) commits and pushes directly to `main` — no feature
branches, no PRs.

This stage touches `web/index.html`, `web/app.js`, `web/style.css`, plus one
small, explicitly-approved backend addition (STEP 1). Read all three web
files in full before starting — this prompt describes the target shape, but
you need the current file in front of you to edit it correctly; don't work
from memory of what this prompt quotes.

## GOAL — unify the UI around "always a list of files" + a 2-tab params card

Today the UI has two entirely separate code paths and DOM subtrees:
single-file mode (`#single-preview-block`, `#artwork-info`, `#size-row`,
top-level `#orientation-select`/`#cols`/`#rows`/`#quantity` driving one
file) and batch mode (`#batch-list`, `#batch-preview-block`,
`#batch-summary`, the same shared top-level orientation/cols/rows/quantity
controls applied uniformly to every file — which stage 2 already retired on
the backend, since orientation/cols/rows/quantity are now per-item on the
API). This stage retires the dual code path on the frontend to match: **one
file is just a list of one.** Concretely:

- The params card gets 2 tabs. **Tab 1** = upload dropzone + the file list
  (always shown, even for 1 file) — each row shows the file, its size, a
  fit/no-fit indicator, a properties button, and a delete button; clicking a
  row selects which file's layout is shown in the preview card. The shared
  "Векторний PDF контуру різу" checkbox lives here too (shared across the
  whole batch, default ON — unchanged from today except its location).
  **Tab 2** = "Аркуш і розмітка" — sheet/mark-offset/field-margin (existing
  section 2) plus order number/material (existing section 3, minus
  quantity, which is now per-file) plus, in shape mode, the new `bleed_mm`
  input — with one explicit "Застосувати" button instead of today's
  live-on-every-keystroke recompute.
- Orientation, grid (cols×rows), and quantity move into a per-file
  **properties popup**, opened from a burger-menu icon on each list row —
  matching stage 2's API, which already expects these per item. The popup
  has its own Cancel/Apply.
- The preview card **only shows the currently-selected file's full layout**
  — the "list you can click through inside the preview card" behavior
  (today's `#batch-summary`/`showBatchItemPreview`/`showBatchList`) is
  retired; that job now belongs entirely to the Tab 1 list. The preview
  card gains zoom/pan, drops the "вміщується" pill (fit/no-fit now shows per
  row in the Tab 1 list instead), and its bottom stats strip becomes a
  compact single row instead of a 2-column 4-row block.
- Card widths become 2/5 (params/files) : 3/5 (preview), and the "Типи
  розкладки" sidebar gets more visual separation from the main content per
  the user's annotated screenshot.
- This is also where stage 1's `actual_w`/`actual_h`/`bleed_mm` (shape mode)
  finally get wired into the UI — stage 1 deliberately left the frontend
  showing the raw page size, noting this would land in the frontend stage.

### Decisions made on your behalf — flag these for the user's confirmation, don't silently treat them as gospel

1. **Rectangular per-file size + deform moves into the properties popup.**
   Today, ONLY single-file rectangular mode lets you manually edit sticker
   W×H and unlock aspect (deform the artwork to fill a resized cell) — batch
   mode has never supported this, on either the frontend or the backend
   (`generate_batch.py` calls `generate_print_pdf(..., grid)` with no
   `deform` argument, i.e. always `deform=False`). The user was asked
   directly whether unifying to "always a list" should drop this feature for
   the single-file case, keep it out of scope, or extend it into the
   per-file popup with a small backend addition — they chose **extend it,
   with the backend addition**. STEP 1 below adds `deform: bool = False` to
   `BatchItem` and wires it through `generate_batch.py`; `dim_w`/`dim_h` on
   `BatchItem` already accept whatever the client sends, so no other backend
   change is needed for editable size. Shape mode is unaffected — its size
   is always fixed from the file, never editable, exactly as today.
2. **Tab 2 holds sheet/marks AND order/material together**, not just
   sheet/marks — the user's spec named "2 tabs" and didn't ask for a 3rd, so
   the existing sections 2 and 3 (minus quantity) both live under the single
   "Аркуш і розмітка" tab, sharing one "Застосувати" button.
3. **Dropping/selecting more files appends to the existing list** rather
   than replacing it — consistent with "always a list", and lets someone
   build up a batch incrementally.
4. **Sidebar separation and zoom control sizing/placement are a first
   pass**, not pixel-matched against the user's annotated screenshot (this
   session can't see that screenshot's exact measurements) — call this out
   in your summary so the user can ask for adjustment if it doesn't match
   what they marked up.

## STEP 1 — BACKEND: per-item deform, for the properties-popup size editor

### server/models.py

Add `deform` to `BatchItem`:

```python
class BatchItem(BaseModel):
    upload_id: str
    dim_w: float = Field(gt=0)
    dim_h: float = Field(gt=0)
    orientation: str | None = None
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    quantity: int = Field(gt=0)
    deform: bool = False
```

### server/routes/generate_batch.py

Pass it through to the existing `generate_print_pdf` call (which already
accepts a `deform` kwarg — see its signature in `server/core/print_pdf.py`,
untouched by this change):

```python
generate_print_pdf(print_path, tpl_pdf, artwork_path, grid, deform=item.deform)
```

That's the entire backend change — `ShapeBatchItem` is untouched (shape mode
has no deform concept), and `dim_w`/`dim_h` were already freely
client-supplied per item.

## STEP 2 — app.js: new unified per-item state

Replace the single-vs-batch state split (`analysis`/`currentLayout` vs
`batchMode`/`batchItems`/`batchLayouts`/`batchDetailIndex`/`batchAllFit`)
with one array, always populated, plus a "which row is shown in the preview"
pointer and one shared "applied batch-level params" object:

```js
let items = [];          // always populated — one entry even for a single file
let selectedIndex = -1;  // index into items currently shown in the preview card, or -1

// One entry per uploaded file:
// {
//   upload_id, filename, dim_w, dim_h, page_count, thumbnail,
//   contour,                          // shape mode only
//   actualW, actualH,                 // shape mode only — derived client-side, see STEP 6
//   orientation, cols, rows,          // null = auto, set via the properties popup
//   quantity,                         // default 1
//   editDimW, editDimH,               // rectangular only — null = use dim_w/dim_h as analyzed
//   deform,                           // rectangular only — default false
//   layout, layoutError,              // last /api/layout result for this item, or an error string
// }
```

Applied (post-"Застосувати") batch-level params, distinct from what's
currently typed into Tab 2's inputs — this is what actually drives
`/api/layout` calls until the user clicks Apply again:

```js
let appliedParams = {
  sheetName: "SRA3", sheetW: 0, sheetH: 0,
  markOffset: 0, fieldMargin: 0,
  bleedMm: 1.0, // shape mode only, default matches SHAPE_BLEED_MM
};
```

Remove `gridManual`/`resolveManualGrid()` as free functions — grid
manual-vs-auto is now a per-item concern, tracked directly on each item's
`cols`/`rows` (null = auto) and edited only through the properties popup, so
there's no ambiguous "is the visible cols/rows input manual or a reflected
auto-fit" state to track globally anymore.

`aspectLocked`/`refW`/`refH`/`lockToggleBtn` move from top-level state into
the properties popup's own local state (STEP 5) — they only matter while
the popup is open, editing one item's size.

## STEP 3 — index.html: 2-tab structure, unified file list, simplified preview

Restructure the `.steps-card` (currently the single `<div class="card
steps-card">` holding sections 1/2/3) into a tab strip plus 2 panels:

```html
<div class="card steps-card">
  <div class="card-tabs">
    <button type="button" class="card-tab is-active" id="card-tab-files">1. Файли</button>
    <button type="button" class="card-tab" id="card-tab-params">2. Аркуш і розмітка</button>
  </div>

  <div class="card-tab-panel" id="card-panel-files">
    <label class="dropzone" id="dropzone" for="file-input"> ... (unchanged) </label>
    <input type="file" id="file-input" accept="application/pdf" multiple hidden>

    <div class="file-list" id="file-list"></div>
    <div class="file-list-empty" id="file-list-empty">Файли ще не завантажено</div>

    <div class="field-row" id="cut-contour-row">
      <label for="cut-contour-checkbox">Векторний PDF контуру різу (для сторонніх програм)</label>
      <input type="checkbox" id="cut-contour-checkbox" checked>
    </div>
  </div>

  <div class="card-tab-panel" id="card-panel-params" hidden>
    <div class="field-row">
      <label for="sheet-select">Аркуш</label>
      <select id="sheet-select"></select>
    </div>
    <div class="field-row" id="custom-sheet-row" hidden>
      <label>Розмір аркуша, мм</label>
      <div class="pair">
        <input type="number" id="sheet-w" min="1" step="0.1">
        <span>×</span>
        <input type="number" id="sheet-h" min="1" step="0.1">
      </div>
    </div>
    <div class="field-row">
      <label for="mark-offset">Відступ мітки від краю аркуша, мм</label>
      <input type="number" id="mark-offset" min="0" step="0.1">
    </div>
    <div class="field-row">
      <label for="field-margin">Відступ поля розкладки від мітки, мм</label>
      <input type="number" id="field-margin" min="0" step="0.1">
    </div>
    <div class="field-row" id="bleed-row" hidden>
      <label for="bleed-mm">Блід, мм</label>
      <input type="number" id="bleed-mm" min="0" step="1" value="1">
    </div>

    <div class="field-row">
      <label for="order-number">Номер замовлення</label>
      <input type="text" id="order-number">
    </div>
    <div class="field-row">
      <label for="material-select">Матеріал</label>
      <select id="material-select"></select>
    </div>
    <div class="field-row" id="material-custom-row" hidden>
      <label for="material-custom">Назва матеріалу</label>
      <input type="text" id="material-custom" placeholder="Свій варіант…">
    </div>

    <div class="params-apply-row">
      <span class="params-pending-hint" id="params-pending-hint" hidden>Є незастосовані зміни</span>
      <button type="button" class="primary-btn" id="params-apply-btn">Застосувати</button>
    </div>
  </div>
</div>
```

`id="params-card"`/`id="order-card"` (the old `is-disabled`-toggled
sections) go away along with the sections they wrapped —
`setSectionEnabled` now just needs to enable/disable `#card-panel-params`
as a whole (still disabled/greyed out until at least one file is loaded,
same idea as today, just one section instead of two).

Preview card — drop the single/batch dual blocks entirely, always one view:

```html
<section class="col col-preview">
  <div class="card preview-card">
    <div class="card-title" id="preview-title">Прев'ю розкладки</div>
    <div class="preview-head">
      <div class="preview-zoom-controls">
        <button type="button" id="zoom-out" title="Зменшити">−</button>
        <button type="button" id="zoom-reset" title="Скинути масштаб">⤢</button>
        <button type="button" id="zoom-in" title="Збільшити">+</button>
      </div>
    </div>
    <div class="preview-canvas" id="preview-canvas">
      <svg id="preview-svg" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet"></svg>
    </div>
    <div class="preview-stats-compact" id="preview-stats"></div>
    <div class="preview-empty" id="preview-empty">Оберіть файл зі списку</div>
  </div>
</section>
```

Toggle `#preview-empty` vs (`#preview-canvas` + `#preview-stats`) based on
whether `selectedIndex` points at a file with a resolved layout — mirrors
how `#file-list-empty` toggles against `#file-list`.

Add the properties-popup markup (STEP 5) as a sibling of `.app-shell`, e.g.
right before `</body>`, so it overlays everything regardless of where it's
triggered from.

Remove now-unused elements: `#artwork-info`/`#artwork-filename`/
`#artwork-size`/`#size-row`/`#sticker-w`/`#sticker-h`/`#lock-toggle`/
`#lock-icon`/`#lock-shackle` (the top-level ones — equivalents move into the
popup with new ids, see STEP 5), `#batch-list`, `#orientation-select`/
`#cols`/`#rows` (top-level), `#quantity` (top-level), `#single-preview-
block`/`#batch-preview-block`/`#batch-back-btn`/`#batch-summary`/
`#preview-fit`.

## STEP 4 — app.js: file handling, list rendering, selection, delete

```js
function handleFiles(files) {
  const pdfs = files.filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) { setStatus("Очікується файл PDF", "error"); return; }
  addFiles(pdfs); // always appends — see "decisions made on your behalf" #3
}

async function addFiles(files) {
  setStatus(`Аналіз ${files.length === 1 ? "файлу" : files.length + " файлів"}…`);
  const newItems = await Promise.all(files.map(async (file) => {
    try {
      const data = shapeMode ? await analyzeShapeFile(file) : await analyzeFile(file);
      return {
        upload_id: data.upload_id, filename: data.filename,
        dim_w: data.dim_w, dim_h: data.dim_h, page_count: data.page_count,
        thumbnail: data.thumbnail, contour: data.contour || null,
        orientation: null, cols: null, rows: null, quantity: 1,
        editDimW: null, editDimH: null, deform: false,
        layout: null, layoutError: null,
        actualW: null, actualH: null, // filled in by recomputeActualSize() — STEP 6
      };
    } catch (err) {
      setStatus(`«${file.name}»: ${err.message || err}`, "error");
      return null;
    }
  }));
  const ok = newItems.filter(Boolean);
  items.push(...ok);
  if (ok.length && selectedIndex === -1) selectedIndex = items.length - ok.length; // auto-select the first newly-added file if nothing was selected

  if (items.length) {
    setSectionEnabled(paramsPanel, true);
    newTaskBtn.hidden = false;
    if (!appliedParams.sheetW) applyTab2Params(); // first file: adopt current Tab 2 defaults immediately
  }
  renderFileList();
  await recomputeAllLayouts();
  setStatus(ok.length < files.length ? "Частину файлів не вдалося проаналізувати" : "", "");
}

function removeItem(i) {
  const it = items[i];
  fetch(`/api/session/${it.upload_id}`, { method: "DELETE" }).catch(() => {});
  items.splice(i, 1);
  if (selectedIndex === i) selectedIndex = items.length ? Math.min(i, items.length - 1) : -1;
  else if (selectedIndex > i) selectedIndex -= 1;
  renderFileList();
  renderSelectedPreview();
  updateGenerateEnabled();
}

function selectItem(i) {
  selectedIndex = i;
  renderFileList(); // to update the .is-selected highlight
  renderSelectedPreview();
}

function renderFileList() {
  fileListEl.innerHTML = "";
  fileListEmptyEl.hidden = items.length > 0;
  items.forEach((it, i) => {
    const row = document.createElement("div");
    row.className = "file-row" + (i === selectedIndex ? " is-selected" : "");
    const fitOk = it.layout && it.layout.fits;
    const fitLabel = it.layoutError ? "помилка" : (it.layout ? (fitOk ? "✓" : "!") : "…");
    row.innerHTML = `
      <button type="button" class="file-row-main">
        <span class="file-row-name">${escapeHtml(it.filename)}</span>
        <span class="file-row-size">${fmt(it.dim_w)} × ${fmt(it.dim_h)} мм${shapeMode && it.actualW != null ? ` (факт. ${fmt(it.actualW)} × ${fmt(it.actualH)})` : ""}</span>
        <span class="file-row-fit ${it.layoutError || (it.layout && !fitOk) ? "is-nofit" : "is-fit"}">${fitLabel}</span>
      </button>
      <button type="button" class="file-row-icon file-row-props" title="Властивості" aria-label="Властивості">☰</button>
      <button type="button" class="file-row-icon file-row-delete" title="Видалити" aria-label="Видалити">✕</button>
    `;
    row.querySelector(".file-row-main").addEventListener("click", () => selectItem(i));
    row.querySelector(".file-row-props").addEventListener("click", (e) => { e.stopPropagation(); openPropsModal(i); });
    row.querySelector(".file-row-delete").addEventListener("click", (e) => { e.stopPropagation(); removeItem(i); });
    fileListEl.appendChild(row);
  });
}
```

`dropzone`/`fileInput` drag-and-drop wiring stays as today, just calling
`handleFiles` (unchanged signature). Sidebar mode switch (`switchMode`) and
`startNewTask` both need to reset `items = []; selectedIndex = -1;` instead
of the old dual state — keep their overall shape (clear everything, disable
panels, reset Tab 2 inputs to defaults) but adapt the variable names.

## STEP 5 — app.js + index.html: the properties popup

Modal markup (near the end of `<body>`):

```html
<div class="modal-overlay" id="props-modal" hidden>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="props-modal-title">
    <div class="modal-title" id="props-modal-title">Властивості файлу</div>
    <div class="modal-filename" id="props-modal-filename"></div>

    <div class="field-row" id="props-size-row">
      <label>Розмір наклейки, мм</label>
      <div class="pair size-pair">
        <input type="number" id="props-w" min="0.1" step="0.1">
        <button type="button" id="props-lock-toggle" class="lock-btn is-locked" title="Зберігати пропорції" aria-pressed="true">
          <svg id="props-lock-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="5" y="11" width="14" height="9" rx="2"/>
            <path id="props-lock-shackle" d="M8 11V7a4 4 0 0 1 8 0v4"/>
          </svg>
        </button>
        <input type="number" id="props-h" min="0.1" step="0.1">
      </div>
    </div>

    <div class="field-row">
      <label for="props-orientation">Орієнтація</label>
      <select id="props-orientation">
        <option value="">Авто</option>
        <option value="WIDE">WIDE</option>
        <option value="TALL">TALL</option>
      </select>
    </div>
    <div class="field-row">
      <label>Сітка (стовпці × рядки)</label>
      <div class="pair">
        <input type="number" id="props-cols" min="0" step="1" placeholder="авто">
        <span>×</span>
        <input type="number" id="props-rows" min="0" step="1" placeholder="авто">
      </div>
    </div>
    <div class="field-row">
      <label for="props-quantity">Кількість наклейок</label>
      <input type="number" id="props-quantity" min="1" step="1">
    </div>

    <div class="modal-error" id="props-modal-error" hidden></div>

    <div class="modal-actions">
      <button type="button" class="ghost-btn" id="props-cancel">Скасувати</button>
      <button type="button" class="primary-btn" id="props-apply">Застосувати</button>
    </div>
  </div>
</div>
```

`#props-size-row` is `hidden` whenever `shapeMode` is true (reuse the
existing lock-icon toggle logic from today's top-level
`setLockState`/`onStickerWInput`/`onStickerHInput`, just re-targeted at the
`props-*` ids and operating on local draft variables instead of global
`refW`/`refH`, e.g. `draftRefW`/`draftRefH` reset each time the modal opens).

```js
let propsIndex = null;

function openPropsModal(i) {
  propsIndex = i;
  const it = items[i];
  propsModalFilename.textContent = it.filename;
  propsSizeRow.hidden = shapeMode;
  if (!shapeMode) {
    propsWInput.value = it.editDimW ?? it.dim_w;
    propsHInput.value = it.editDimH ?? it.dim_h;
    setPropsLockState(!it.deform);
  }
  propsOrientation.value = it.orientation || "";
  propsCols.value = it.cols ?? "";
  propsRows.value = it.rows ?? "";
  propsQuantity.value = it.quantity;
  propsModalError.hidden = true;
  propsModal.hidden = false;
}

function closePropsModal() {
  propsModal.hidden = true;
  propsIndex = null;
}
propsCancelBtn.addEventListener("click", closePropsModal);

propsApplyBtn.addEventListener("click", async () => {
  const it = items[propsIndex];
  const cols = parseInt(propsCols.value, 10);
  const rows = parseInt(propsRows.value, 10);
  const draft = {
    orientation: propsOrientation.value || null,
    cols: Number.isFinite(cols) && cols > 0 ? cols : null,
    rows: Number.isFinite(rows) && rows > 0 ? rows : null,
    quantity: parseInt(propsQuantity.value, 10) || 1,
    editDimW: shapeMode ? null : (parseFloat(propsWInput.value) || it.dim_w),
    editDimH: shapeMode ? null : (parseFloat(propsHInput.value) || it.dim_h),
    deform: shapeMode ? false : !propsAspectLocked,
  };
  // Validate against the shared sheet params before committing — same
  // fits/doesn't-fit check the server will do, surfaced inline instead of
  // silently accepting a grid that can't work.
  const layout = await fetchLayoutFor({ ...it, ...draft });
  Object.assign(it, draft);
  it.layout = layout.layout;
  it.layoutError = layout.error;
  if (layout.error) {
    propsModalError.textContent = layout.error;
    propsModalError.hidden = false;
    return; // keep the modal open so the user can adjust
  }
  closePropsModal();
  renderFileList();
  if (propsIndex === selectedIndex || items[selectedIndex] === it) renderSelectedPreview();
  updateGenerateEnabled();
});
```

`fetchLayoutFor(item)` is a small shared helper factored out of the existing
`/api/layout` POST logic (today inlined in `recompute()`/
`renderBatchSummary()`) — one item in, `{ layout, error }` out, using
`appliedParams` for the shared sheet/margin fields and the item's own
effective size (`shapeMode ? item.dim_w/dim_h : (item.editDimW ??
item.dim_w)`/etc.) and orientation/cols/rows. `recomputeAllLayouts()` (STEP
4/6) is just `Promise.all(items.map(...))` over this same helper, applied to
every item's CURRENTLY COMMITTED (not draft) params — used after Tab 2's
Apply, after add/remove, and on initial load.

## STEP 6 — app.js: preview rendering — single selection, zoom/pan, compact stats, actual size

`renderLayout(layout, artwork, deform)` (the big SVG-building function)
keeps its core logic (sheet outline, field boundary, corner marks, tiled
artwork/contour per cell) — none of that changes. What changes around it:

- It's now called only as `renderSelectedPreview()`, which looks up
  `items[selectedIndex]`, uses `it.layout` (already resolved by
  `recomputeAllLayouts()`/the properties popup/Tab 2 Apply — no ad-hoc fetch
  here), and toggles `#preview-empty` when `selectedIndex === -1` or the
  item has no successful layout yet.
- Delete the `previewFit.textContent = ...`/`previewFit.className = ...`
  block entirely (STEP 3 already removed the `#preview-fit` element) — fit/
  no-fit is now only shown per row in the file list (STEP 4).
- Delete the "reflect the resolved grid into `#cols`/`#rows`" block — those
  inputs don't exist at the top level anymore; the properties popup's own
  cols/rows inputs are only ever populated when the popup opens (STEP 5),
  never live-synced from a background recompute.
- Replace the `previewStats.innerHTML = ...` 4-row `<dl>` block with a
  compact single-row strip:

```js
previewStats.innerHTML = "";
const statsData = [
  ["Орієнтація", layout.orientation],
  ["Комірка", `${fmt(layout.cell_w)} × ${fmt(layout.cell_h)}`],
  ["Сітка", `${layout.cols} × ${layout.rows}`],
  ["На аркуші", String(layout.count)],
];
for (const [label, value] of statsData) {
  const stat = document.createElement("div");
  stat.className = "stat";
  stat.innerHTML = `${label}<b>${escapeHtml(value)}</b>`;
  previewStats.appendChild(stat);
}
```

- Add zoom/pan on `#preview-canvas` (wraps `#preview-svg`), reset every time
  a new item is selected or its layout is recomputed (so zoom never carries
  over onto a different sheet):

```js
let zoom = { scale: 1, tx: 0, ty: 0 };

function applyZoomTransform() {
  previewSvg.style.transform = `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale})`;
}
function resetZoom() {
  zoom = { scale: 1, tx: 0, ty: 0 };
  applyZoomTransform();
}

previewCanvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = previewCanvas.getBoundingClientRect();
  const mx = e.clientX - rect.left - rect.width / 2;
  const my = e.clientY - rect.top - rect.height / 2;
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  const newScale = Math.min(8, Math.max(1, zoom.scale * factor));
  zoom.tx = mx - (mx - zoom.tx) * (newScale / zoom.scale);
  zoom.ty = my - (my - zoom.ty) * (newScale / zoom.scale);
  zoom.scale = newScale;
  if (zoom.scale <= 1.001) { zoom.scale = 1; zoom.tx = 0; zoom.ty = 0; }
  applyZoomTransform();
}, { passive: false });

let panning = false, panStartX = 0, panStartY = 0, panOrigTx = 0, panOrigTy = 0;
previewCanvas.addEventListener("pointerdown", (e) => {
  if (zoom.scale <= 1) return;
  panning = true;
  previewCanvas.setPointerCapture(e.pointerId);
  panStartX = e.clientX; panStartY = e.clientY;
  panOrigTx = zoom.tx; panOrigTy = zoom.ty;
  previewCanvas.classList.add("is-panning");
});
previewCanvas.addEventListener("pointermove", (e) => {
  if (!panning) return;
  zoom.tx = panOrigTx + (e.clientX - panStartX);
  zoom.ty = panOrigTy + (e.clientY - panStartY);
  applyZoomTransform();
});
["pointerup", "pointercancel", "pointerleave"].forEach((evt) =>
  previewCanvas.addEventListener(evt, () => { panning = false; previewCanvas.classList.remove("is-panning"); })
);
zoomInBtn.addEventListener("click", () => { zoom.scale = Math.min(8, zoom.scale * 1.3); applyZoomTransform(); });
zoomOutBtn.addEventListener("click", () => {
  zoom.scale = Math.max(1, zoom.scale / 1.3);
  if (zoom.scale <= 1.001) resetZoom(); else applyZoomTransform();
});
zoomResetBtn.addEventListener("click", resetZoom);
```

Call `resetZoom()` at the start of `renderSelectedPreview()`, before
building the new SVG content.

**Actual size (shape mode)** — stage 1 added `actual_w`/`actual_h` to
`/api/analyze-shape`'s response and `bleed_mm` to the generate payloads, but
left the frontend showing the raw page size. Now: read `bleed_mm` off the
`/api/analyze-shape` response once when a file is added (informational
only), but drive the DISPLAYED actual size from `appliedParams.bleedMm`
(the shared, user-editable value) recomputed purely client-side — no need
to re-call the analyze endpoint when the user changes the bleed:

```js
function recomputeActualSize(it) {
  if (!shapeMode) return;
  it.actualW = round2(it.dim_w - 2 * appliedParams.bleedMm);
  it.actualH = round2(it.dim_h - 2 * appliedParams.bleedMm);
}
```

Call this for every item whenever `appliedParams.bleedMm` changes (i.e.
inside `applyTab2Params()`, STEP 7) and once when each item is first added.
Show it in the file list row (STEP 4 already does — `факт. W × H`) — no
separate display needed elsewhere unless you find one clearly missing; don't
invent extra UI for it beyond what's specified here.

## STEP 7 — app.js: Tab 2 — buffered edits + one Apply button

Tab 2's inputs (`sheet-select`/`sheet-w`/`sheet-h`/`mark-offset`/
`field-margin`/`bleed-mm`/`order-number`/`material-select`/
`material-custom`) stop live-recomputing on every keystroke. Instead:

```js
function markParamsPending() {
  paramsPendingHint.hidden = false;
}
[sheetSelect, sheetWInput, sheetHInput, markOffsetInput, fieldMarginInput, bleedMmInput]
  .forEach((input) => input.addEventListener("input", markParamsPending));
sheetSelect.addEventListener("change", () => { onSheetChanged(); markParamsPending(); });

async function applyTab2Params() {
  appliedParams = {
    sheetName: sheetSelect.value,
    sheetW: parseFloat(sheetWInput.value) || 0,
    sheetH: parseFloat(sheetHInput.value) || 0,
    markOffset: parseFloat(markOffsetInput.value) || 0,
    fieldMargin: parseFloat(fieldMarginInput.value) || 0,
    bleedMm: parseFloat(bleedMmInput.value) || 0,
  };
  paramsPendingHint.hidden = true;
  items.forEach(recomputeActualSize);
  await recomputeAllLayouts();
  renderFileList();
  renderSelectedPreview();
  updateGenerateEnabled();
}
paramsApplyBtn.addEventListener("click", applyTab2Params);
```

`order-number`/`material-select`/`material-custom` don't affect layout math
at all (they're only read at generate time via `effectiveMaterial()`/
`orderNumberInput.value`), so they don't strictly need to gate on Apply —
it's fine (and simpler) to let the SAME Apply button be the one explicit
confirmation point for the whole tab, per the user's "явне підтвердження
застосування" request, even though only the sheet/margin/bleed fields
actually trigger a recompute. `bleed-row`/`bleed-mm` are `hidden` when
`!shapeMode` (toggle alongside the existing `sizeRow`-style mode switches).

`#card-tab-files`/`#card-tab-params` just toggle which `.card-tab-panel` is
visible (`hidden` attribute) and which tab button has `.is-active` — no
data implications, purely a view switch.

## STEP 8 — app.js: generate — always through the batch endpoints

Retire `generateSingle()`/`generateShapeSingle()` — `generateBatch()`/
`generateShapeBatch()` become the only two generate functions, used
regardless of `items.length` (per "always a list, 1 file = list of one"):

```js
async function generateBatch() {
  const payload = {
    items: items.map((it) => ({
      upload_id: it.upload_id,
      dim_w: it.editDimW ?? it.dim_w,
      dim_h: it.editDimH ?? it.dim_h,
      orientation: it.orientation,
      cols: it.cols,
      rows: it.rows,
      quantity: it.quantity,
      deform: it.deform,
    })),
    sheet_name: appliedParams.sheetName,
    sheet_w: appliedParams.sheetW,
    sheet_h: appliedParams.sheetH,
    mark_offset: appliedParams.markOffset,
    field_margin: appliedParams.fieldMargin,
    order: orderNumberInput.value.trim(),
    material: effectiveMaterial(),
    cut_contour: cutContourCheckbox.checked,
  };
  const { blob, filename } = await postForZip("/api/generate-batch", payload);
  downloadBlob(blob, filename);
  setStatus(`Готово. ${items.length} файл(ів) оброблено, завантажено: ${filename}`, "ok");
}

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
  const { blob, filename } = await postForZip("/api/generate-batch-shape", payload);
  downloadBlob(blob, filename);
  setStatus(`Готово. ${items.length} файл(ів) оброблено, завантажено: ${filename}`, "ok");
}

generateBtn.addEventListener("click", async () => {
  generateBtn.disabled = true;
  setStatus("Генерація файлів…");
  try {
    if (shapeMode) await generateShapeBatch(); else await generateBatch();
  } catch (err) {
    setStatus(String(err.message || err), "error");
  } finally {
    updateGenerateEnabled();
  }
});
```

`updateGenerateEnabled()` becomes:

```js
function updateGenerateEnabled() {
  const materialOk = effectiveMaterial().length > 0;
  const allFit = items.length > 0 && items.every((it) => it.layout && it.layout.fits && it.quantity > 0);
  generateBtn.disabled = !(allFit && materialOk);
}
```

`postForZip`/`downloadBlob`/`parseFilename`/`effectiveMaterial`/`fmt`/
`escapeHtml`/`round2`/`debounce` (if still needed anywhere) stay as-is.

## STEP 9 — style.css

Card width ratio (2/5 params+files : 3/5 preview) — update `.layout`:

```css
.layout {
  display: grid;
  grid-template-columns: minmax(320px, 2fr) minmax(400px, 3fr);
  gap: 24px;
  height: 80vh;
  min-height: 520px;
}
```

Sidebar separation — the user marked up a screenshot asking for the "Типи
розкладки" card to sit visibly further left/apart from the params card; as
a first pass (flagged above — adjust after the user sees it), widen the gap
between it and the main content and give it a bit more breathing room from
the viewport edge:

```css
.app-shell {
  display: flex;
  align-items: flex-start;
  gap: 48px; /* was 24px */
  padding-top: 24px;
}
```

Card tabs:

```css
.card-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--border);
}
.card-tab {
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  font-family: inherit;
  margin-bottom: -1px;
}
.card-tab:hover { color: var(--fg); }
.card-tab.is-active { color: var(--ink); border-bottom-color: var(--ink); }
```

File list (Tab 1) — replace `.batch-list`/`.batch-item` styling:

```css
.file-list {
  margin-top: 14px;
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}
.file-list-empty {
  margin-top: 14px;
  padding: 14px;
  text-align: center;
  font-size: 12px;
  color: var(--muted);
}
.file-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--border);
}
.file-row:last-child { border-bottom: none; }
.file-row.is-selected { background: var(--card-bg); box-shadow: inset 2px 0 0 var(--ink); }
.file-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
}
.file-row-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.file-row-size { flex: none; font-size: 11px; color: var(--muted); white-space: nowrap; }
.file-row-fit { flex: none; width: 18px; text-align: center; font-weight: 700; font-size: 12px; }
.file-row-fit.is-fit { color: var(--ok); }
.file-row-fit.is-nofit { color: var(--danger); }
.file-row-icon {
  flex: none;
  width: 28px; height: 28px;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
}
.file-row-icon:hover { background: var(--card-bg); color: var(--fg); }
```

Modal (properties popup):

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: min(360px, 92vw);
  background: var(--card-bg);
  border-radius: var(--radius);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  padding: 20px 22px;
}
.modal-title { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
.modal-filename { font-size: 12px; color: var(--muted); margin-bottom: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.modal-error { font-size: 12px; color: var(--danger); margin-top: 8px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
```

Preview zoom/pan + compact stats — replace `.preview-head`/`.pill`/
`.preview-stats` rules:

```css
.preview-head {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-bottom: 12px;
}
.preview-zoom-controls { display: flex; gap: 4px; }
.preview-zoom-controls button {
  width: 28px; height: 28px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--card-bg);
  color: var(--fg);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.preview-zoom-controls button:hover { background: var(--surface); }

.preview-canvas {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  overflow: hidden;
  cursor: default;
  touch-action: none;
}
.preview-canvas.is-panning { cursor: grabbing; }
#preview-svg { width: 100%; height: 100%; transform-origin: center center; }

.preview-stats-compact {
  margin: 12px 0 0;
  flex: none;
  display: flex;
  border-top: 1px solid var(--border);
  padding-top: 8px;
  font-size: 11px;
  color: var(--muted);
}
.preview-stats-compact .stat { flex: 1; text-align: center; padding: 0 6px; border-right: 1px solid var(--border); }
.preview-stats-compact .stat:last-child { border-right: none; }
.preview-stats-compact .stat b { display: block; margin-top: 2px; font-size: 12px; font-weight: 600; color: var(--fg); }

.preview-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 13px; }
```

Remove the now-unused `.pill`/`.pill.fits`/`.pill.no-fit` rules, the old
`.batch-list`/`.batch-item`/`.batch-summary`/`.batch-summary-row`/`.bsr-*`/
`.back-btn` rules, and the old 2-column `.preview-stats` rule. Add dark-mode
tweaks for any new classes that need them, following the existing
`@media (prefers-color-scheme: dark)` block's pattern (e.g. `.modal`
background already inherits `--card-bg`, should need no extra rule; double-
check `.file-row.is-selected`/`.file-row-fit` contrast in dark mode).

## STEP 10 — SMOKE TEST

This is a UI-heavy stage — run the server locally (`python run_server.py`)
and drive it through a real browser session (or, if a browser-automation
tool is available in your environment, use it; otherwise walk through this
manually and describe what you saw, same spirit as stage 3's rendered-PNG
review). Cover, for BOTH rectangular and shaped-sticker sidebar tabs:

1. Upload 1 file → it appears in the Tab 1 list (not a separate "single
   file" view), gets auto-selected, and its layout renders in the preview.
2. Drop 2 more files while the first is still loaded → all 3 now sit in the
   list (append, not replace); switching selection between rows swaps the
   preview.
3. Delete the currently-selected row → the preview falls back to another
   remaining item (or shows the empty state if the list becomes empty); the
   deleted upload's session is dropped (`DELETE /api/session/{id}` fires).
4. Open the properties popup on one file, set an explicit orientation +
   cols×rows that doesn't fit the current sheet → Apply shows the inline
   error and stays open; fix it to something that fits → Apply closes the
   popup, the list row's size/fit column and (if selected) the preview both
   update to match.
5. Rectangular mode only: in the properties popup, edit the sticker W with
   the aspect lock on → H follows proportionally; toggle the lock off, edit
   W and H independently, Apply → generate this one file and confirm the
   downloaded print PDF actually shows the artwork stretched (deformed) to
   the edited box, not contain-fit — this exercises the new
   `BatchItem.deform`/`generate_batch.py` wiring end to end.
6. Shape mode only: change the `bleed_mm` field on Tab 2 and click
   Apply → every list row's "факт. …" figure updates immediately
   (client-side, no re-analyze network call — check the network tab);
   generate and confirm the print PDF is unaffected by size (still the full
   page) and the zip's naming/quantities are unaffected — `bleed_mm` only
   ever changed the displayed actual size and (server-side) the same value
   already validated in stage 1.
7. Tab 2: edit sheet/mark-offset/field-margin — confirm nothing recomputes
   until "Застосувати" is clicked (the pending hint appears while unapplied,
   disappears after Apply), then every file's fit status updates together.
8. Preview zoom: scroll-wheel zooms in centered under the cursor, drag pans
   once zoomed in, the reset button returns to 1:1, and switching to a
   different file in the list resets zoom back to 1:1 for the new sheet.
9. Generate with the full 3-file batch (mixed orientations/quantities set
   via the popups) — confirm the downloaded zip's contents match: correct
   per-item quantities/sheets-needed, correct dedup of identical
   template/PLT/contour sets (rectangular mode), correct per-item contour
   files (shape mode).
10. "Нове завдання" clears everything back to the empty state (list, both
    tab panels' inputs, preview) exactly like before.
11. Regression: sidebar mode switch (rectangular ↔ shaped) still calls
    `startNewTask()` first and doesn't leave stale items from the other
    mode on screen.

## STEP 11 — UPDATE: CLAUDE.md "Останній стан"

Read the current file first — stage 3 added a sub-bullet ending with a
"Наступні стадії" list that starts "4-8 — фронтенд...". Add a new sub-
bullet documenting stages 4-8's completion (mention the STEP 1 backend
addition explicitly, since it's a real, if small, backend change riding
along with the frontend work) and remove the now-fully-done "Наступні
стадії" list, since this was the last planned stage — replace it with a
closing note that the planned 8-stage effort is complete and flag the two
"first pass, needs a visual look" items (sidebar separation gap, feed-arrow
sizing from stage 3) for a follow-up round if the user wants one. Something
in this spirit:

```
  **Стадії 4-8 (фронтенд, велике перероблення UI) — виконано, весь
  запланований цикл робіт завершено.** Картка параметрів тепер має 2
  вкладки: "1. Файли" (аплоад + уніфікований список файлів — завжди список,
  навіть для одного файлу; трикутник властивостей на кожному рядку відкриває
  попап орієнтація/сітка/кількість(+розмір і деформація для прямокутного
  режиму); іконка видалення) і "2. Аркуш і розмітка" (аркуш/відступи/блід
  (фігурний режим)/замовлення/матеріал, одна кнопка "Застосувати" замість
  живого перерахунку на кожне натискання клавіші). Прев'ю-картка тепер
  завжди показує лише вибраний зі списку файл (перемикання файлів
  переїхало у список на вкладці 1), отримала зум/пан колесом миші та
  перетягуванням, індикатор "вміщується" прибрано (статус тепер у списку
  файлів), статистика внизу стала одним компактним рядком замість 4.
  Ширини карток 2/5 (параметри/файли) : 3/5 (прев'ю). Сайдбар "Типи
  розкладки" отримав більший відступ від основного контенту (перший
  прохід, потребує звірки з розміткою користувача). Ген
  ерація тепер завжди йде через batch-ендпоінти (`/api/generate-batch(-shape)`),
  навіть для одного файлу — одиночні ендпоінти `/api/generate`/
  `/api/generate-shape` лишаються на бекенді, але фронтенд ними більше не
  користується. Підключено `actual_w`/`actual_h`/`bleed_mm` зі стадії 1 —
  "фактичний" розмір рахується на льоту на клієнті з `bleed_mm` без
  повторного аналізу файлу. Невелика бекенд-правка в рамках цього ж циклу:
  `BatchItem.deform` (+ проброс у `generate_batch.py`) — раніше деформація
  артворку під розмір комірки була лише в одиночному прямокутному режимі,
  тепер доступна через попап властивостей файлу й у batch-режимі теж.

  Заплановані на початок цього циклу 8 стадій завершено. Відкрите: точна
  візуальна звірка відступу сайдбару і розміру/позиції стрілки напряму
  подачі (стадія 3) з референсами користувача — можливе тонке
  підлаштування за фідбеком.
```

## STEP 12 — COMMIT + PUSH

```
git add server/models.py server/routes/generate_batch.py web/index.html web/app.js web/style.css CLAUDE.md
git commit -m "feat(web): unify single/batch UI into one always-a-list workflow, 2-tab params card, preview zoom/pan"
git push origin main
```

## STEP 13 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (all 11 points from STEP 10 — describe what you observed, not just pass/fail)
### 📋 Known issues for next session (call out the two flagged "first pass, needs visual confirmation" items explicitly)
