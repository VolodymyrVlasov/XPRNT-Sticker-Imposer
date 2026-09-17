"use strict";

const el = (id) => document.getElementById(id);

const tabRectBtn = el("tab-rect");
const tabShapeBtn = el("tab-shape");

const dropzone = el("dropzone");
const fileInput = el("file-input");

const cardTabFilesBtn = el("card-tab-files");
const cardTabParamsBtn = el("card-tab-params");
const cardPanelFiles = el("card-panel-files");
const cardPanelParams = el("card-panel-params");

const fileListEl = el("file-list");
const fileListEmptyEl = el("file-list-empty");

const sheetSelect = el("sheet-select");
const customSheetRow = el("custom-sheet-row");
const sheetWInput = el("sheet-w");
const sheetHInput = el("sheet-h");
const markOffsetInput = el("mark-offset");
const fieldMarginInput = el("field-margin");
const bleedRow = el("bleed-row");
const bleedMmInput = el("bleed-mm");

const orderNumberInput = el("order-number");
const materialSelect = el("material-select");
const materialCustomRow = el("material-custom-row");
const materialCustomInput = el("material-custom");

const paramsPendingHint = el("params-pending-hint");
const paramsApplyBtn = el("params-apply-btn");

const cutContourCheckbox = el("cut-contour-checkbox");

const generateBtn = el("generate-btn");
const newTaskBtn = el("new-task-btn");
const statusEl = el("status");

const previewTitle = el("preview-title");
const previewCanvas = el("preview-canvas");
const previewSvg = el("preview-svg");
const previewStats = el("preview-stats");
const previewEmpty = el("preview-empty");
const zoomInBtn = el("zoom-in");
const zoomOutBtn = el("zoom-out");
const zoomResetBtn = el("zoom-reset");

const propsModal = el("props-modal");
const propsModalFilename = el("props-modal-filename");
const propsSizeRow = el("props-size-row");
const propsWInput = el("props-w");
const propsHInput = el("props-h");
const propsLockToggleBtn = el("props-lock-toggle");
const propsLockShacklePath = el("props-lock-shackle");
const propsOrientation = el("props-orientation");
const propsCols = el("props-cols");
const propsRows = el("props-rows");
const propsQuantity = el("props-quantity");
const propsModalError = el("props-modal-error");
const propsCancelBtn = el("props-cancel");
const propsApplyBtn = el("props-apply");

let config = null;
let shapeMode = false; // "Фігурні стікери" sidebar tab — fixed size, cut-contour preview

// items: always populated — one entry even for a single file.
// {
//   upload_id, filename, dim_w, dim_h, page_count, thumbnail,
//   contour,                          // shape mode only
//   actualW, actualH,                 // shape mode only — derived client-side
//   orientation, cols, rows,          // null = auto, set via the properties popup
//   quantity,                         // default 1
//   editDimW, editDimH,               // rectangular only — null = use dim_w/dim_h as analyzed
//   deform,                           // rectangular only — default false
//   layout, layoutError,              // last /api/layout result for this item, or an error string
// }
let items = [];
let selectedIndex = -1; // index into items currently shown in the preview card, or -1
let layoutRequestSeq = 0;

// Applied (post-"Застосувати") batch-level params — distinct from what's
// currently typed into Tab 2's inputs. Drives /api/layout calls until the
// user clicks Apply again.
let appliedParams = {
  sheetName: "SRA3", sheetW: 0, sheetH: 0,
  markOffset: 0, fieldMargin: 0,
  bleedMm: 1.0, // shape mode only, default matches SHAPE_BLEED_MM
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function round2(v) { return Math.round(v * 100) / 100; }

function fmt(v) {
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

// ── card enable/disable (plain divs, not <fieldset>, so we drive it by hand) ─

function setSectionEnabled(section, enabled) {
  section.classList.toggle("is-disabled", !enabled);
  section.querySelectorAll("input, select, button").forEach((field) => { field.disabled = !enabled; });
}

// ── status helper ────────────────────────────────────────────────────────

function setStatus(message, kind) {
  statusEl.textContent = message || "";
  statusEl.className = "status" + (kind ? " " + kind : "");
}

// ── sidebar tabs / mode switch ───────────────────────────────────────────

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

// ── card tabs (Tab 1 files / Tab 2 sheet+marks) ──────────────────────────

function switchCardTab(tab) {
  const filesActive = tab === "files";
  cardTabFilesBtn.classList.toggle("is-active", filesActive);
  cardTabParamsBtn.classList.toggle("is-active", !filesActive);
  cardPanelFiles.hidden = !filesActive;
  cardPanelParams.hidden = filesActive;
}
cardTabFilesBtn.addEventListener("click", () => switchCardTab("files"));
cardTabParamsBtn.addEventListener("click", () => switchCardTab("params"));

// ── config / bootstrap ───────────────────────────────────────────────────

async function loadConfig() {
  const res = await fetch("/api/config");
  config = await res.json();

  sheetSelect.innerHTML = "";
  for (const name of Object.keys(config.sheet_presets)) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sheetSelect.appendChild(opt);
  }
  const customOpt = document.createElement("option");
  customOpt.value = "Custom";
  customOpt.textContent = "Custom";
  sheetSelect.appendChild(customOpt);

  materialSelect.innerHTML = "";
  for (const m of config.materials) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    materialSelect.appendChild(opt);
  }

  markOffsetInput.value = config.defaults.mark_offset;
  fieldMarginInput.value = config.defaults.field_margin;
}

// ── file upload / analyze ────────────────────────────────────────────────

function openFilePicker() {
  fileInput.click();
}

dropzone.addEventListener("click", openFilePicker);
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") openFilePicker();
});
["dragover", "dragenter"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const files = e.dataTransfer.files && Array.from(e.dataTransfer.files);
  if (files && files.length) handleFiles(files);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleFiles(Array.from(fileInput.files));
  fileInput.value = "";
});

function handleFiles(files) {
  const pdfs = files.filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) {
    setStatus("Очікується файл PDF", "error");
    return;
  }
  addFiles(pdfs); // always appends to the existing list, never replaces it
}

async function analyzeFile(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/analyze", { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail || "Помилка аналізу файлу");
  return res.json();
}

async function analyzeShapeFile(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/analyze-shape", { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json()).detail || "Помилка аналізу файлу");
  return res.json();
}

function recomputeActualSize(it) {
  if (!shapeMode) return;
  it.actualW = round2(it.dim_w - 2 * appliedParams.bleedMm);
  it.actualH = round2(it.dim_h - 2 * appliedParams.bleedMm);
}

async function addFiles(files) {
  setStatus(`Аналіз ${files.length === 1 ? "файлу" : files.length + " файлів"}…`);
  const newItems = await Promise.all(files.map(async (file) => {
    try {
      const data = shapeMode ? await analyzeShapeFile(file) : await analyzeFile(file);
      const item = {
        upload_id: data.upload_id, filename: data.filename,
        dim_w: data.dim_w, dim_h: data.dim_h, page_count: data.page_count,
        thumbnail: data.thumbnail, contour: data.contour || null,
        orientation: null, cols: null, rows: null, quantity: 1,
        editDimW: null, editDimH: null, deform: false,
        layout: null, layoutError: null,
        actualW: null, actualH: null,
      };
      recomputeActualSize(item);
      return item;
    } catch (err) {
      setStatus(`«${file.name}»: ${err.message || err}`, "error");
      return null;
    }
  }));
  const ok = newItems.filter(Boolean);
  items.push(...ok);
  if (ok.length && selectedIndex === -1) selectedIndex = items.length - ok.length; // auto-select the first newly-added file if nothing was selected

  if (items.length) {
    setSectionEnabled(cardPanelParams, true);
    newTaskBtn.hidden = false;
  }
  renderFileList();

  if (items.length && !appliedParams.sheetW) {
    // First file ever added this task: adopt whatever is currently sitting
    // in Tab 2's inputs (config defaults) as the applied params — this also
    // resolves layouts for every item and renders the preview.
    await applyTab2Params();
  } else {
    await recomputeAllLayouts();
    renderFileList();
    renderSelectedPreview();
  }
  setStatus(ok.length < files.length ? "Частину файлів не вдалося проаналізувати" : "", "");
  updateGenerateEnabled();
}

function removeItem(i) {
  const it = items[i];
  fetch(`/api/session/${it.upload_id}`, { method: "DELETE" }).catch(() => { /* best effort */ });
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
  fileListEl.hidden = items.length === 0;
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

// ── new task (reset without reloading the page) ──────────────────────────

async function startNewTask() {
  const idsToDrop = items.map((it) => it.upload_id);
  await Promise.all(idsToDrop.map((id) =>
    fetch(`/api/session/${id}`, { method: "DELETE" }).catch(() => { /* best effort */ })
  ));

  items = [];
  selectedIndex = -1;
  appliedParams = {
    sheetName: "SRA3", sheetW: 0, sheetH: 0,
    markOffset: 0, fieldMargin: 0,
    bleedMm: 1.0,
  };

  closePropsModal();
  renderFileList();

  setSectionEnabled(cardPanelParams, false);
  newTaskBtn.hidden = true;
  switchCardTab("files");

  sheetSelect.value = "SRA3";
  onSheetChanged();
  markOffsetInput.value = config.defaults.mark_offset;
  fieldMarginInput.value = config.defaults.field_margin;
  bleedMmInput.value = "1";
  paramsPendingHint.hidden = true;

  cutContourCheckbox.checked = true;

  orderNumberInput.value = "";
  materialSelect.selectedIndex = 0;
  materialCustomRow.hidden = true;
  materialCustomInput.value = "";

  renderSelectedPreview();

  setStatus("", "");
  updateGenerateEnabled();
}

newTaskBtn.addEventListener("click", startNewTask);

// ── sheet / material toggle ──────────────────────────────────────────────

function onSheetChanged() {
  const isCustom = sheetSelect.value === "Custom";
  customSheetRow.hidden = !isCustom;
  if (!isCustom) {
    const preset = config.sheet_presets[sheetSelect.value];
    sheetWInput.value = preset.w;
    sheetHInput.value = preset.h;
  }
}

materialSelect.addEventListener("change", () => {
  materialCustomRow.hidden = materialSelect.value !== config.custom_material;
  updateGenerateEnabled();
});

// ── Tab 2: buffered edits + one explicit Apply ───────────────────────────

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

[orderNumberInput, materialCustomInput].forEach((input) =>
  input.addEventListener("input", updateGenerateEnabled)
);

// ── per-item layout resolution ───────────────────────────────────────────

async function fetchLayoutFor(it) {
  const dimW = shapeMode ? it.dim_w : (it.editDimW ?? it.dim_w);
  const dimH = shapeMode ? it.dim_h : (it.editDimH ?? it.dim_h);
  if (!(appliedParams.sheetW > 0) || !(appliedParams.sheetH > 0)) {
    return { layout: null, error: null };
  }
  const body = {
    dim_w: dimW,
    dim_h: dimH,
    sheet_w: appliedParams.sheetW,
    sheet_h: appliedParams.sheetH,
    mark_offset: appliedParams.markOffset,
    field_margin: appliedParams.fieldMargin,
    gap: 0,
    orientation: it.orientation || null,
    cols: it.cols || null,
    rows: it.rows || null,
  };
  try {
    const res = await fetch("/api/layout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Помилка розрахунку розкладки");
    return { layout: await res.json(), error: null };
  } catch (err) {
    return { layout: null, error: String(err.message || err) };
  }
}

async function recomputeAllLayouts() {
  const seq = ++layoutRequestSeq;
  const results = await Promise.all(items.map((it) => fetchLayoutFor(it)));
  if (seq !== layoutRequestSeq) return; // superseded by a newer edit
  results.forEach(({ layout, error }, i) => {
    items[i].layout = layout;
    items[i].layoutError = error;
  });
}

// ── properties popup (per-file orientation/grid/quantity, +size/deform) ──

let propsIndex = null;
let propsAspectLocked = true;
let draftRefW = 0, draftRefH = 0; // sticker W/H ratio anchor, local to the open popup

function setPropsLockState(locked) {
  propsAspectLocked = locked;
  propsLockToggleBtn.classList.toggle("is-locked", locked);
  propsLockToggleBtn.setAttribute("aria-pressed", String(locked));
  propsLockToggleBtn.title = locked ? "Зберігати пропорції" : "Вільна зміна (деформація артворку)";
  propsLockShacklePath.setAttribute("d", locked ? "M8 11V7a4 4 0 0 1 8 0v4" : "M8 11V7a4 4 0 0 1 7.5-3.8");
  if (locked) {
    draftRefW = parseFloat(propsWInput.value) || draftRefW;
    draftRefH = parseFloat(propsHInput.value) || draftRefH;
  }
}
propsLockToggleBtn.addEventListener("click", () => setPropsLockState(!propsAspectLocked));

function onPropsWInput() {
  const w = parseFloat(propsWInput.value);
  if (Number.isFinite(w) && w > 0) {
    if (propsAspectLocked && draftRefW > 0) propsHInput.value = round2(draftRefH * (w / draftRefW));
    draftRefW = w;
    draftRefH = parseFloat(propsHInput.value) || draftRefH;
  }
}
function onPropsHInput() {
  const h = parseFloat(propsHInput.value);
  if (Number.isFinite(h) && h > 0) {
    if (propsAspectLocked && draftRefH > 0) propsWInput.value = round2(draftRefW * (h / draftRefH));
    draftRefH = h;
    draftRefW = parseFloat(propsWInput.value) || draftRefW;
  }
}
propsWInput.addEventListener("input", onPropsWInput);
propsHInput.addEventListener("input", onPropsHInput);

function openPropsModal(i) {
  propsIndex = i;
  const it = items[i];
  propsModalFilename.textContent = it.filename;
  propsSizeRow.hidden = shapeMode;
  if (!shapeMode) {
    const w = it.editDimW ?? it.dim_w;
    const h = it.editDimH ?? it.dim_h;
    propsWInput.value = w;
    propsHInput.value = h;
    draftRefW = w;
    draftRefH = h;
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
  const idx = propsIndex;
  if (idx === null) return;
  const it = items[idx];
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
  // silently accepting a grid that can't work. Note /api/layout returns
  // HTTP 200 with fits:false for a grid that's merely too big for the
  // sheet (not a request error), so that case needs its own check here —
  // fetchLayoutFor's `error` only covers actual request failures.
  const result = await fetchLayoutFor({ ...it, ...draft });
  Object.assign(it, draft);
  it.layout = result.layout;
  it.layoutError = result.error;
  if (result.error) {
    propsModalError.textContent = result.error;
    propsModalError.hidden = false;
    return; // keep the modal open so the user can adjust
  }
  if (!result.layout || !result.layout.fits) {
    it.layoutError = "Сітка не вміщується на аркуші з поточними параметрами";
    propsModalError.textContent = it.layoutError;
    propsModalError.hidden = false;
    return; // keep the modal open so the user can adjust
  }
  closePropsModal();
  renderFileList();
  if (idx === selectedIndex) renderSelectedPreview();
  updateGenerateEnabled();
});

// ── preview rendering ────────────────────────────────────────────────────

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

// Build an SVG path "d" string from a ShapeAnalyzeResponse's contour.subpaths
// (M start, one L/C command per segment, Z if closed). Coordinates are already
// in mm relative to the artwork's own top-left corner — same convention as
// this SVG's viewBox — so no extra transform is needed here.
function contourPathD(subpaths) {
  return subpaths.map((sp) => {
    let d = `M ${sp.start[0]} ${sp.start[1]}`;
    for (const seg of sp.segments) {
      if (seg.kind === "C") {
        const [x1, y1, x2, y2, x, y] = seg.points;
        d += ` C ${x1} ${y1} ${x2} ${y2} ${x} ${y}`;
      } else {
        d += ` L ${seg.points[0]} ${seg.points[1]}`;
      }
    }
    if (sp.closed) d += " Z";
    return d;
  }).join(" ");
}

function renderLayout(layout, artwork, deform) {
  const sheetW = layout.sheet_w;
  const sheetH = layout.sheet_h;
  previewSvg.setAttribute("viewBox", `0 0 ${sheetW} ${sheetH}`);
  previewSvg.innerHTML = "";

  const strokeW = Math.max(sheetW, sheetH) * 0.0035;

  // sheet outline
  previewSvg.appendChild(svgEl("rect", {
    x: 0, y: 0, width: sheetW, height: sheetH,
    fill: "#ffffff", stroke: "#111111", "stroke-width": strokeW,
  }));

  // usable field boundary (marks + field margin inset)
  const fieldInset = layout.mark_offset + layout.field_margin;
  previewSvg.appendChild(svgEl("rect", {
    x: fieldInset, y: fieldInset,
    width: Math.max(sheetW - 2 * fieldInset, 0),
    height: Math.max(sheetH - 2 * fieldInset, 0),
    fill: "none", stroke: "#b0b0b0", "stroke-width": strokeW,
    "stroke-dasharray": `${strokeW * 3},${strokeW * 2}`,
  }));

  // corner registration marks — L-brackets pointing toward the sheet interior,
  // matching the actual marks drawn onto the template PDF.
  const markLen = 9, markThick = 1;
  const corners = [
    { cx: layout.mark_offset, cy: layout.mark_offset, dirX: 1, dirY: 1 },
    { cx: sheetW - layout.mark_offset, cy: layout.mark_offset, dirX: -1, dirY: 1 },
    { cx: layout.mark_offset, cy: sheetH - layout.mark_offset, dirX: 1, dirY: -1 },
    { cx: sheetW - layout.mark_offset, cy: sheetH - layout.mark_offset, dirX: -1, dirY: -1 },
  ];
  for (const { cx, cy, dirX, dirY } of corners) {
    const hx = dirX > 0 ? cx : cx - markLen;
    previewSvg.appendChild(svgEl("rect", {
      x: hx, y: cy - markThick / 2, width: markLen, height: markThick, fill: "#111111",
    }));
    const vy = dirY > 0 ? cy : cy - markLen;
    previewSvg.appendChild(svgEl("rect", {
      x: cx - markThick / 2, y: vy, width: markThick, height: markLen, fill: "#111111",
    }));
  }

  // sticker grid — each cell shows the uploaded artwork fitted exactly the way
  // the server does: same rotate-to-orientation check, same contain-vs-deform
  // scaling, so the preview never lies about what the print PDF will look like.
  const strideX = layout.cell_w + layout.gap;
  const strideY = layout.cell_h + layout.gap;
  const hasThumb = !!(artwork && artwork.thumbnail);

  let artW = 0, artH = 0, rotate = false, fitW = 0, fitH = 0, padX = 0, padY = 0, rotCx = 0, rotCy = 0;
  if (hasThumb) {
    artW = artwork.dim_w;
    artH = artwork.dim_h;
    const cellIsLandscape = layout.cell_w >= layout.cell_h;
    const artIsLandscape = artW >= artH;
    rotate = cellIsLandscape !== artIsLandscape;
    if (rotate) { const t = artW; artW = artH; artH = t; }

    if (shapeMode || deform) {
      // Shape mode: dim_w/dim_h already equal the bleed-inclusive tile, so the
      // tile IS the cell — no contain-fit scaling/padding needed, the tile
      // simply fills the cell (only the rotate handling below still applies).
      // Deform: the artwork is stretched independently on X/Y to fill the cell.
      fitW = layout.cell_w;
      fitH = layout.cell_h;
    } else {
      // Locked — uniform contain-fit, centered, keeps the artwork's own ratio.
      const scale = Math.min(layout.cell_w / artW, layout.cell_h / artH);
      fitW = artW * scale;
      fitH = artH * scale;
      padX = (layout.cell_w - fitW) / 2;
      padY = (layout.cell_h - fitH) / 2;
    }
    if (rotate) {
      rotCx = padX + fitW / 2;
      rotCy = padY + fitH / 2;
    }
  }

  for (let row = 0; row < layout.rows; row++) {
    for (let col = 0; col < layout.cols; col++) {
      const cellX = layout.grid_x + col * strideX;
      const cellY = layout.grid_y + row * strideY;

      if (!hasThumb) {
        previewSvg.appendChild(svgEl("rect", {
          x: cellX, y: cellY, width: layout.cell_w, height: layout.cell_h,
          fill: "#e3e3e3", stroke: "none",
        }));
      } else {
        // Nested <svg> clips to the cell automatically, so rotated/oversized
        // artwork never bleeds past the cut line.
        const nested = svgEl("svg", {
          x: cellX, y: cellY, width: layout.cell_w, height: layout.cell_h,
          viewBox: `0 0 ${layout.cell_w} ${layout.cell_h}`,
        });
        const image = svgEl("image", { preserveAspectRatio: "none" });
        image.setAttribute("href", artwork.thumbnail);
        image.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", artwork.thumbnail);
        if (rotate) {
          // Pre-rotation box is W/H swapped, centered on the same point the
          // final (post-rotation) box would occupy, then rotated 90° about that center.
          image.setAttribute("x", rotCx - fitH / 2);
          image.setAttribute("y", rotCy - fitW / 2);
          image.setAttribute("width", fitH);
          image.setAttribute("height", fitW);
          image.setAttribute("transform", `rotate(90 ${rotCx} ${rotCy})`);
        } else {
          image.setAttribute("x", padX);
          image.setAttribute("y", padY);
          image.setAttribute("width", fitW);
          image.setAttribute("height", fitH);
        }
        nested.appendChild(image);

        if (shapeMode && artwork.contour) {
          // Cut-contour outline, sharing the exact same translate/rotate as the
          // image above so it always lines up with the raster underneath it.
          const path = svgEl("path", {
            d: contourPathD(artwork.contour.subpaths),
            fill: "none",
            stroke: "#000000",
            "stroke-width": strokeW * 0.5,
            "stroke-dasharray": `${strokeW * 1.2},${strokeW * 0.8}`,
          });
          path.setAttribute("transform", rotate
            ? `rotate(90 ${rotCx} ${rotCy}) translate(${rotCx - fitH / 2} ${rotCy - fitW / 2})`
            : `translate(${padX} ${padY})`);
          nested.appendChild(path);
        }

        previewSvg.appendChild(nested);
      }

      if (!shapeMode) {
        // Shape-mode cells get the traced cut contour (added above) as their
        // border instead of a plain rectangle.
        previewSvg.appendChild(svgEl("rect", {
          x: cellX, y: cellY, width: layout.cell_w, height: layout.cell_h,
          fill: "none", stroke: "#111111", "stroke-width": strokeW * 0.6,
        }));
      }
    }
  }

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

  updateGenerateEnabled();
}

function renderSelectedPreview() {
  resetZoom();
  const it = selectedIndex >= 0 ? items[selectedIndex] : null;
  const hasLayout = !!(it && it.layout);
  previewEmpty.hidden = hasLayout;
  previewCanvas.hidden = !hasLayout;
  previewStats.hidden = !hasLayout;
  if (!hasLayout) {
    previewTitle.textContent = "Прев'ю розкладки";
    previewSvg.innerHTML = "";
    previewStats.innerHTML = "";
    return;
  }
  previewTitle.textContent = `Прев'ю — ${it.filename}`;
  renderLayout(it.layout, it, shapeMode ? false : it.deform);
}

// ── preview zoom / pan ────────────────────────────────────────────────────

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

// ── generate enable/disable ──────────────────────────────────────────────

function effectiveMaterial() {
  if (materialSelect.value === config.custom_material) return materialCustomInput.value.trim();
  return materialSelect.value;
}

function updateGenerateEnabled() {
  const materialOk = effectiveMaterial().length > 0;
  const allFit = items.length > 0 && items.every((it) => it.layout && it.layout.fits && it.quantity > 0);
  generateBtn.disabled = !(allFit && materialOk);
}

function parseFilename(disposition) {
  const star = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try { return decodeURIComponent(star[1]); } catch (_) { /* fall through */ }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1] : null;
}

// ── generate & download — always through the batch endpoints ────────────

function downloadBlob(blob, fallbackFilename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fallbackFilename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function postForZip(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Помилка генерації";
    try { detail = (await res.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const filename = parseFilename(disposition) || "rect-sticker-imposer.zip";
  return { blob, filename };
}

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

// ── init ──────────────────────────────────────────────────────────────────

setSectionEnabled(cardPanelParams, false);
bleedRow.hidden = true;
renderFileList();
renderSelectedPreview();
loadConfig();
