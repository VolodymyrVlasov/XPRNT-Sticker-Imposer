"use strict";

const el = (id) => document.getElementById(id);

const tabRectBtn = el("tab-rect");
const tabShapeBtn = el("tab-shape");

const dropzone = el("dropzone");
const fileInput = el("file-input");
const artworkInfo = el("artwork-info");
const artworkFilename = el("artwork-filename");
const artworkSize = el("artwork-size");

const sizeRow = el("size-row");
const stickerWInput = el("sticker-w");
const stickerHInput = el("sticker-h");
const lockToggleBtn = el("lock-toggle");
const lockShacklePath = el("lock-shackle");

const paramsCard = el("params-card");
const orderCard = el("order-card");

const sheetSelect = el("sheet-select");
const customSheetRow = el("custom-sheet-row");
const sheetWInput = el("sheet-w");
const sheetHInput = el("sheet-h");
const markOffsetInput = el("mark-offset");
const fieldMarginInput = el("field-margin");
const orientationSelect = el("orientation-select");
const colsInput = el("cols");
const rowsInput = el("rows");

const orderNumberInput = el("order-number");
const materialSelect = el("material-select");
const materialCustomRow = el("material-custom-row");
const materialCustomInput = el("material-custom");
const quantityInput = el("quantity");

const cutContourCheckbox = el("cut-contour-checkbox");

const generateBtn = el("generate-btn");
const newTaskBtn = el("new-task-btn");
const statusEl = el("status");

const previewTitle = el("preview-title");
const singlePreviewBlock = el("single-preview-block");
const batchBackBtn = el("batch-back-btn");
const previewSvg = el("preview-svg");
const previewFit = el("preview-fit");
const previewStats = el("preview-stats");

const batchListEl = el("batch-list");
const batchPreviewBlock = el("batch-preview-block");
const batchSummaryEl = el("batch-summary");

let config = null;
let analysis = null;      // { upload_id, filename, dim_w, dim_h, page_count, thumbnail }
let currentLayout = null; // last LayoutResult from /api/analyze or /api/layout
let layoutRequestSeq = 0;
let gridManual = false;   // true once the user edits cols/rows directly (vs. showing the auto-fit)
let aspectLocked = true;  // sticker W/H lock, Photoshop-style
let refW = 0, refH = 0;   // sticker W/H as of the last synced edit — the ratio used while locked

let shapeMode = false;    // "Фігурні стікери" tab — fixed size, cut-contour preview

let batchMode = false;
let batchItems = [];      // analyze()/analyzeShapeFile() results for every file in a multi-file upload
let batchLayouts = [];    // [{ item, layout, error }] — last renderBatchSummary() results, for drill-down
let batchDetailIndex = null; // index into batchLayouts currently shown as a full preview, or null = list view
let batchAllFit = false;
let batchRequestSeq = 0;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function round2(v) { return Math.round(v * 100) / 100; }

// ── card enable/disable (plain divs, not <fieldset>, so we drive it by hand) ─

function setSectionEnabled(section, enabled) {
  section.classList.toggle("is-disabled", !enabled);
  section.querySelectorAll("input, select, button").forEach((field) => { field.disabled = !enabled; });
}

// ── sticker size (editable) + aspect-ratio lock ─────────────────────────────

function setLockState(locked) {
  aspectLocked = locked;
  lockToggleBtn.classList.toggle("is-locked", locked);
  lockToggleBtn.setAttribute("aria-pressed", String(locked));
  lockToggleBtn.title = locked ? "Зберігати пропорції" : "Вільна зміна (деформація артворку)";
  lockShacklePath.setAttribute("d", locked ? "M8 11V7a4 4 0 0 1 8 0v4" : "M8 11V7a4 4 0 0 1 7.5-3.8");
  if (locked) {
    // Re-anchor the ratio to whatever is on screen right now.
    refW = parseFloat(stickerWInput.value) || refW;
    refH = parseFloat(stickerHInput.value) || refH;
  }
}
lockToggleBtn.addEventListener("click", () => setLockState(!aspectLocked));

function onStickerWInput() {
  const w = parseFloat(stickerWInput.value);
  if (Number.isFinite(w) && w > 0) {
    if (aspectLocked && refW > 0) stickerHInput.value = round2(refH * (w / refW));
    refW = w;
    refH = parseFloat(stickerHInput.value) || refH;
  }
  recompute();
}
function onStickerHInput() {
  const h = parseFloat(stickerHInput.value);
  if (Number.isFinite(h) && h > 0) {
    if (aspectLocked && refH > 0) stickerWInput.value = round2(refW * (h / refH));
    refH = h;
    refW = parseFloat(stickerWInput.value) || refW;
  }
  recompute();
}
stickerWInput.addEventListener("input", onStickerWInput);
stickerHInput.addEventListener("input", onStickerHInput);

// ── status helper ────────────────────────────────────────────────────────

function setStatus(message, kind) {
  statusEl.textContent = message || "";
  statusEl.className = "status" + (kind ? " " + kind : "");
}

// ── sidebar tabs / mode switch ───────────────────────────────────────────

async function switchMode(toShapeMode) {
  if (toShapeMode === shapeMode) return;
  await startNewTask(); // don't leave stale analysis/preview from the other mode on screen
  shapeMode = toShapeMode;
  tabRectBtn.classList.toggle("is-active", !shapeMode);
  tabShapeBtn.classList.toggle("is-active", shapeMode);
}
tabRectBtn.addEventListener("click", () => switchMode(false));
tabShapeBtn.addEventListener("click", () => switchMode(true));

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
});

function handleFiles(files) {
  const pdfs = files.filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) {
    setStatus("Очікується файл PDF", "error");
    return;
  }
  // Same single-vs-batch dispatch for both modes — shapeMode only decides
  // which endpoints handleSingleFile()/handleBatchFiles() call internally.
  if (pdfs.length === 1) handleSingleFile(pdfs[0]);
  else handleBatchFiles(pdfs);
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

async function handleSingleFile(file) {
  batchMode = false;
  batchItems = [];
  batchLayouts = [];
  batchDetailIndex = null;
  batchListEl.hidden = true;
  batchListEl.innerHTML = "";
  previewTitle.textContent = "Прев'ю розкладки";
  singlePreviewBlock.hidden = false;
  batchBackBtn.hidden = true;
  batchPreviewBlock.hidden = true;
  colsInput.disabled = false;
  rowsInput.disabled = false;

  setStatus("Аналіз файлу…");
  try {
    const data = shapeMode ? await analyzeShapeFile(file) : await analyzeFile(file);

    analysis = data; // in shape mode this also carries `contour`
    currentLayout = data.layout;
    gridManual = false;

    artworkFilename.textContent = data.filename;
    artworkSize.textContent = `${fmt(data.dim_w)} × ${fmt(data.dim_h)} мм` +
      (data.page_count > 1 ? ` (сторінок: ${data.page_count})` : "");
    artworkInfo.hidden = false;

    if (shapeMode) {
      // Fixed size, read straight from the file — no W/H inputs, no lock/deform.
      sizeRow.hidden = true;
    } else {
      stickerWInput.value = data.dim_w;
      stickerHInput.value = data.dim_h;
      refW = data.dim_w;
      refH = data.dim_h;
      setLockState(true);
      sizeRow.hidden = false;
    }

    sheetSelect.value = data.sheet_name;
    onSheetChanged();
    orientationSelect.value = "";

    setSectionEnabled(paramsCard, true);
    setSectionEnabled(orderCard, true);
    newTaskBtn.hidden = false;

    renderLayout(currentLayout, analysis, !aspectLocked);
    setStatus("", "");
  } catch (err) {
    setStatus(String(err.message || err), "error");
  }
}

async function handleBatchFiles(files) {
  batchMode = true;
  analysis = null;
  currentLayout = null;

  artworkInfo.hidden = true;
  sizeRow.hidden = true;
  previewTitle.textContent = "Прев'ю розкладки — пакетна обробка";
  singlePreviewBlock.hidden = true;
  batchBackBtn.hidden = true;
  batchPreviewBlock.hidden = false;

  batchListEl.hidden = false;
  batchListEl.innerHTML = "";
  batchItems = [];
  batchLayouts = [];
  batchDetailIndex = null;

  setStatus(`Аналіз ${files.length} файлів…`);

  const rows = files.map((file) => {
    const row = document.createElement("div");
    row.className = "batch-item";
    row.textContent = `${file.name} — аналіз…`;
    batchListEl.appendChild(row);
    return row;
  });

  await Promise.all(files.map(async (file, i) => {
    try {
      const data = shapeMode ? await analyzeShapeFile(file) : await analyzeFile(file);
      batchItems.push(data);
      rows[i].textContent = `${data.filename} — ${fmt(data.dim_w)} × ${fmt(data.dim_h)} мм`;
    } catch (err) {
      rows[i].textContent = `${file.name} — помилка: ${err.message || err}`;
      rows[i].classList.add("error");
    }
  }));

  sheetSelect.value = "SRA3";
  onSheetChanged();
  orientationSelect.value = "";

  setSectionEnabled(paramsCard, true);
  setSectionEnabled(orderCard, true);
  // Manual grid override is ambiguous across differently-sized artworks in one batch.
  colsInput.value = "";
  rowsInput.value = "";
  colsInput.disabled = true;
  rowsInput.disabled = true;
  gridManual = false;

  newTaskBtn.hidden = false;

  if (!batchItems.length) {
    setStatus("Жоден файл не вдалося проаналізувати", "error");
  } else {
    setStatus(batchItems.length < files.length ? "Частину файлів не вдалося проаналізувати — див. список" : "", "");
  }
  await renderBatchSummary();
}

function fmt(v) {
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

// ── new task (reset without reloading the page) ──────────────────────────

async function startNewTask() {
  const idsToDrop = analysis ? [analysis.upload_id] : batchItems.map((it) => it.upload_id);
  await Promise.all(idsToDrop.map((id) =>
    fetch(`/api/session/${id}`, { method: "DELETE" }).catch(() => { /* best effort */ })
  ));

  analysis = null;
  currentLayout = null;
  gridManual = false;

  batchMode = false;
  batchItems = [];
  batchLayouts = [];
  batchDetailIndex = null;
  batchAllFit = false;
  batchListEl.hidden = true;
  batchListEl.innerHTML = "";
  batchSummaryEl.innerHTML = "";
  previewTitle.textContent = "Прев'ю розкладки";
  singlePreviewBlock.hidden = false;
  batchBackBtn.hidden = true;
  batchPreviewBlock.hidden = true;

  fileInput.value = "";
  artworkInfo.hidden = true;
  artworkFilename.textContent = "—";
  artworkSize.textContent = "—";

  sizeRow.hidden = true;
  stickerWInput.value = "";
  stickerHInput.value = "";
  refW = 0;
  refH = 0;
  setLockState(true);

  setSectionEnabled(paramsCard, false);
  setSectionEnabled(orderCard, false);
  newTaskBtn.hidden = true;

  sheetSelect.value = "SRA3";
  onSheetChanged();
  markOffsetInput.value = config.defaults.mark_offset;
  fieldMarginInput.value = config.defaults.field_margin;
  orientationSelect.value = "";
  colsInput.value = "";
  rowsInput.value = "";
  colsInput.disabled = false;
  rowsInput.disabled = false;
  colsInput.removeAttribute("max");
  rowsInput.removeAttribute("max");
  cutContourCheckbox.checked = false;

  orderNumberInput.value = "";
  materialSelect.selectedIndex = 0;
  materialCustomRow.hidden = true;
  materialCustomInput.value = "";
  quantityInput.value = "1";

  previewSvg.innerHTML = "";
  previewSvg.setAttribute("viewBox", "0 0 100 100");
  previewFit.textContent = "";
  previewFit.className = "pill";
  previewStats.innerHTML = "";

  setStatus("", "");
  updateGenerateEnabled();
}

newTaskBtn.addEventListener("click", startNewTask);

// ── batch: drill into one file's full preview, and back ─────────────────

function showBatchItemPreview(i) {
  const entry = batchLayouts[i];
  if (!entry || !entry.layout) return;
  batchDetailIndex = i;
  batchPreviewBlock.hidden = true;
  singlePreviewBlock.hidden = false;
  batchBackBtn.hidden = false;
  previewTitle.textContent = `Прев'ю — ${entry.item.filename}`;
  renderLayout(entry.layout, entry.item, false); // batch items never deform — no per-file resize UI
}

function showBatchList() {
  batchDetailIndex = null;
  singlePreviewBlock.hidden = true;
  batchBackBtn.hidden = true;
  batchPreviewBlock.hidden = false;
  previewTitle.textContent = "Прев'ю розкладки — пакетна обробка";
}

batchBackBtn.addEventListener("click", showBatchList);

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
sheetSelect.addEventListener("change", () => { onSheetChanged(); recompute(); });

materialSelect.addEventListener("change", () => {
  materialCustomRow.hidden = materialSelect.value !== config.custom_material;
  updateGenerateEnabled();
});

// ── live layout recompute ────────────────────────────────────────────────

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// Cols/rows fields always display the current grid so they're editable in
// place, but they only override the server's auto-fit once the user has
// actually touched them — otherwise every other field edit would "freeze"
// the grid at its last displayed size instead of re-optimizing. Shared by
// collectLayoutInput() and generateShapeSingle() so a generate request can
// never drift from the grid /api/layout already confirmed fits.
function resolveManualGrid() {
  const cols = parseInt(colsInput.value, 10);
  const rows = parseInt(rowsInput.value, 10);
  const useManualGrid = gridManual && Number.isFinite(cols) && cols > 0 && Number.isFinite(rows) && rows > 0;
  return { cols: useManualGrid ? cols : null, rows: useManualGrid ? rows : null };
}

function collectLayoutInput() {
  const sheetW = parseFloat(sheetWInput.value);
  const sheetH = parseFloat(sheetHInput.value);
  const { cols, rows } = resolveManualGrid();
  // Shape mode has no size inputs — dim_w/dim_h always come straight from the
  // analyzed file (they already include the bleed).
  const dimW = shapeMode ? analysis.dim_w : (parseFloat(stickerWInput.value) || analysis.dim_w);
  const dimH = shapeMode ? analysis.dim_h : (parseFloat(stickerHInput.value) || analysis.dim_h);
  return {
    dim_w: dimW,
    dim_h: dimH,
    sheet_w: sheetW,
    sheet_h: sheetH,
    mark_offset: parseFloat(markOffsetInput.value) || 0,
    field_margin: parseFloat(fieldMarginInput.value) || 0,
    gap: 0,
    orientation: orientationSelect.value || null,
    cols,
    rows,
  };
}

function onGridInput() {
  const colsEmpty = colsInput.value.trim() === "";
  const rowsEmpty = rowsInput.value.trim() === "";
  gridManual = !(colsEmpty && rowsEmpty);
  recompute();
}

const recompute = debounce(async () => {
  if (batchMode) { renderBatchSummary(); return; }
  if (!analysis) return;
  const body = collectLayoutInput();
  if (!(body.sheet_w > 0) || !(body.sheet_h > 0)) return;

  const seq = ++layoutRequestSeq;
  try {
    const res = await fetch("/api/layout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (seq !== layoutRequestSeq) return; // superseded by a newer edit
    if (!res.ok) throw new Error((await res.json()).detail || "Помилка розрахунку розкладки");
    currentLayout = await res.json();
    renderLayout(currentLayout, analysis, !aspectLocked);
  } catch (err) {
    setStatus(String(err.message || err), "error");
  }
}, 200);

[sheetWInput, sheetHInput, markOffsetInput, fieldMarginInput, orientationSelect]
  .forEach((input) => input.addEventListener("input", recompute));
[colsInput, rowsInput].forEach((input) => input.addEventListener("input", onGridInput));

// ── batch summary (one /api/layout call per file, shared sheet/margin/orientation) ─

async function renderBatchSummary() {
  if (!batchMode || !batchItems.length) {
    batchSummaryEl.innerHTML = "";
    batchAllFit = false;
    updateGenerateEnabled();
    return;
  }
  const sheetW = parseFloat(sheetWInput.value);
  const sheetH = parseFloat(sheetHInput.value);
  if (!(sheetW > 0) || !(sheetH > 0)) return;

  const shared = {
    sheet_w: sheetW, sheet_h: sheetH,
    mark_offset: parseFloat(markOffsetInput.value) || 0,
    field_margin: parseFloat(fieldMarginInput.value) || 0,
    gap: 0,
    orientation: orientationSelect.value || null,
    cols: null, rows: null,
  };

  const seq = ++batchRequestSeq;
  const results = await Promise.all(batchItems.map(async (item) => {
    try {
      const res = await fetch("/api/layout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...shared, dim_w: item.dim_w, dim_h: item.dim_h }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "помилка");
      return { item, layout: await res.json(), error: null };
    } catch (err) {
      return { item, layout: null, error: String(err.message || err) };
    }
  }));
  if (seq !== batchRequestSeq) return; // superseded by a newer edit

  batchLayouts = results;
  if (batchDetailIndex !== null) showBatchList(); // params changed — the open detail preview would be stale

  batchSummaryEl.innerHTML = "";
  let allFit = true;
  results.forEach(({ item, layout, error }, i) => {
    const ok = !error && layout && layout.fits;
    if (!ok) allFit = false;
    const row = document.createElement("div");
    row.className = "batch-summary-row" + (layout ? " is-clickable" : "");
    row.title = layout ? "Натисніть, щоб побачити повне прев'ю" : "";
    row.innerHTML = `
      <div class="bsr-name">${escapeHtml(item.filename)}</div>
      <div class="bsr-size">${fmt(item.dim_w)} × ${fmt(item.dim_h)} мм</div>
      <div class="bsr-grid">${layout ? `${layout.cols} × ${layout.rows} (${layout.count}/арк)` : "—"}</div>
      <div class="bsr-status ${ok ? "ok" : "error"}">${error || (layout && layout.fits ? "вміщується" : "не вміщується")}</div>
    `;
    if (layout) row.addEventListener("click", () => showBatchItemPreview(i));
    batchSummaryEl.appendChild(row);
  });
  batchAllFit = allFit;
  updateGenerateEnabled();
}

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

  previewFit.textContent = layout.fits ? "вміщується" : "не вміщується";
  previewFit.className = "pill " + (layout.fits ? "fits" : "no-fit");

  // reflect the resolved grid into the editable cols/rows fields, without
  // clobbering what the user is actively typing, and cap what they can enter
  colsInput.max = layout.max_cols;
  rowsInput.max = layout.max_rows;
  if (document.activeElement !== colsInput) colsInput.value = layout.cols;
  if (document.activeElement !== rowsInput) rowsInput.value = layout.rows;

  previewStats.innerHTML = "";
  const rowsData = [
    ["Орієнтація", layout.orientation],
    ["Розмір комірки", `${fmt(layout.cell_w)} × ${fmt(layout.cell_h)} мм`],
    ["Сітка", `${layout.cols} × ${layout.rows}`],
    ["Наклейок на аркуші", String(layout.count)],
  ];
  for (const [k, v] of rowsData) {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    previewStats.appendChild(dt);
    previewStats.appendChild(dd);
  }

  updateGenerateEnabled();
}

// ── generate enable/disable ──────────────────────────────────────────────

function effectiveMaterial() {
  if (materialSelect.value === config.custom_material) return materialCustomInput.value.trim();
  return materialSelect.value;
}

function updateGenerateEnabled() {
  // Order number is optional — the print filename is simply built without it.
  // shapeMode doesn't need its own branch here: batchMode/analysis/
  // currentLayout/batchItems/batchAllFit are already populated the same way
  // regardless of mode, so the existing single-vs-batch check covers both.
  const materialOk = effectiveMaterial().length > 0 && parseInt(quantityInput.value, 10) > 0;
  const ready = batchMode
    ? batchItems.length > 0 && batchAllFit && materialOk
    : !!analysis && !!currentLayout && currentLayout.fits && materialOk;
  generateBtn.disabled = !ready;
}

[orderNumberInput, materialCustomInput, quantityInput].forEach((input) =>
  input.addEventListener("input", updateGenerateEnabled)
);

function parseFilename(disposition) {
  const star = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try { return decodeURIComponent(star[1]); } catch (_) { /* fall through */ }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1] : null;
}

// ── generate & download ──────────────────────────────────────────────────

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

async function generateSingle() {
  if (!analysis || !currentLayout) return;
  const payload = {
    upload_id: analysis.upload_id,
    layout: collectLayoutInput(),
    sheet_name: sheetSelect.value,
    order: orderNumberInput.value.trim(),
    material: effectiveMaterial(),
    quantity: parseInt(quantityInput.value, 10),
    deform: !aspectLocked,
    cut_contour: cutContourCheckbox.checked,
  };
  const { blob, filename } = await postForZip("/api/generate", payload);
  downloadBlob(blob, filename);
  setStatus("Готово. Файли завантажено: " + filename, "ok");
}

async function generateShapeSingle() {
  if (!analysis || !currentLayout) return;
  const { cols, rows } = resolveManualGrid();
  const payload = {
    upload_id: analysis.upload_id,
    sheet_name: sheetSelect.value,
    sheet_w: parseFloat(sheetWInput.value),
    sheet_h: parseFloat(sheetHInput.value),
    mark_offset: parseFloat(markOffsetInput.value) || 0,
    field_margin: parseFloat(fieldMarginInput.value) || 0,
    orientation: orientationSelect.value || null,
    cols,
    rows,
    order: orderNumberInput.value.trim(),
    material: effectiveMaterial(),
    quantity: parseInt(quantityInput.value, 10),
    cut_contour: cutContourCheckbox.checked,
  };
  const { blob, filename } = await postForZip("/api/generate-shape", payload);
  downloadBlob(blob, filename);
  setStatus("Готово. Файли завантажено: " + filename, "ok");
}

async function generateBatch() {
  if (!batchItems.length) return;
  const payload = {
    items: batchItems.map((it) => ({ upload_id: it.upload_id, dim_w: it.dim_w, dim_h: it.dim_h })),
    sheet_name: sheetSelect.value,
    sheet_w: parseFloat(sheetWInput.value),
    sheet_h: parseFloat(sheetHInput.value),
    mark_offset: parseFloat(markOffsetInput.value) || 0,
    field_margin: parseFloat(fieldMarginInput.value) || 0,
    orientation: orientationSelect.value || null,
    order: orderNumberInput.value.trim(),
    material: effectiveMaterial(),
    quantity: parseInt(quantityInput.value, 10),
    cut_contour: cutContourCheckbox.checked,
  };
  const { blob, filename } = await postForZip("/api/generate-batch", payload);
  downloadBlob(blob, filename);
  setStatus(`Готово. ${batchItems.length} файлів оброблено, завантажено: ${filename}`, "ok");
}

async function generateShapeBatch() {
  if (!batchItems.length) return;
  const payload = {
    items: batchItems.map((it) => ({ upload_id: it.upload_id })),
    sheet_name: sheetSelect.value,
    sheet_w: parseFloat(sheetWInput.value),
    sheet_h: parseFloat(sheetHInput.value),
    mark_offset: parseFloat(markOffsetInput.value) || 0,
    field_margin: parseFloat(fieldMarginInput.value) || 0,
    orientation: orientationSelect.value || null,
    order: orderNumberInput.value.trim(),
    material: effectiveMaterial(),
    quantity: parseInt(quantityInput.value, 10),
    cut_contour: cutContourCheckbox.checked,
  };
  const { blob, filename } = await postForZip("/api/generate-batch-shape", payload);
  downloadBlob(blob, filename);
  setStatus(`Готово. ${batchItems.length} файлів оброблено, завантажено: ${filename}`, "ok");
}

generateBtn.addEventListener("click", async () => {
  generateBtn.disabled = true;
  setStatus("Генерація файлів…");
  try {
    if (shapeMode && batchMode) await generateShapeBatch();
    else if (shapeMode) await generateShapeSingle();
    else if (batchMode) await generateBatch();
    else await generateSingle();
  } catch (err) {
    setStatus(String(err.message || err), "error");
  } finally {
    updateGenerateEnabled();
  }
});

setSectionEnabled(paramsCard, false);
setSectionEnabled(orderCard, false);
loadConfig();
