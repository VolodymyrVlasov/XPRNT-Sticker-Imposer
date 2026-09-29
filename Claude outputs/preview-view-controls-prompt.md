You are working in the project root.
Do NOT modify existing working code beyond what is listed below.
Base branch: `main`. Commit and push directly to `main` (single-maintainer repo).

## GOAL

Add view-mode controls (контури / друк / разом) and a contour-color picker
above the sheet preview, add a feed-direction triangle to the preview
(matching the one already drawn in the real generated PDFs), and remove the
grey background/border around the preview canvas.

## CONTEXT / DESIGN DECISIONS (already confirmed with the project owner — do not re-litigate)

- **Scope**: the контури/друк/разом toggle applies in **all three** sidebar
  modes, including "Прямокутні наліпки" — not just the shape modes.
  "Прямокутні наліпки" has no vector cut-contour data at all (no PDF layer
  to trace), so there **"контур" means the cell-border rectangle** — the
  same rectangle that's already drawn around every cell in that mode today
  (`web/app.js`'s `if (!shapeMode) { ...cell border rect... }`), since for a
  rectangular sticker the cell edge literally *is* the cut line. In "Фігурні
  стікери"/"Стікерпаки", "контур" means the existing dashed vector contour
  path traced from the PDF.
- Because both of those now represent "where the plotter cuts", **the new
  contour-color picker recolors both** — the rect-mode cell border AND the
  shape-mode dashed contour path share the same color state. It does
  **not** affect the corner registration marks, the corner-guide ticks
  (Стікерпаки), the field-boundary dashed guide, the new feed-direction
  triangle (see below), or the existing `outline-checkbox` 0.1mm decorative
  border — those all stay their current colors (black/grey), unchanged.
- **Color picker scope**: on-screen preview only. Does **not** change the
  color of the generated vector cut-contour PDF (`shape_contour_pdf.py`) —
  do not touch that file.
- **The grey box around the preview**: remove it — `.preview-canvas`'s
  `background`/`border` only, not the element itself (it's still needed
  structurally: it sizes/centers the SVG and holds the pan/zoom-cursor
  class). Every other property on `.preview-canvas` stays as-is.
- **View mode does NOT reset per file selection** — unlike zoom (which
  already resets via `resetZoom()` in `renderSelectedPreview()`), view mode
  and contour color are user preferences that should persist across
  switching between files/tasks within the session, until the page is
  reloaded. Don't copy the zoom-reset pattern for these.
- Sheet-level framing (sheet outline, field-boundary dashed guide, corner
  registration marks, the pack-mode corner-guide ticks, and the new feed
  triangle) is always drawn regardless of view mode — контури/друк only
  gates **per-cell** content (the raster image / grey placeholder, and the
  contour path or cell-border rect).
- The existing `outline-checkbox` (0.1mm decorative border) stays
  completely independent of all of this — same condition, same color, as
  today.

## STEP 1 — web/index.html — new controls in the preview head row

Find:
```html
          <div class="preview-head">
            <div class="preview-zoom-controls">
              <button type="button" id="zoom-out" title="Зменшити">−</button>
              <button type="button" id="zoom-reset" title="Скинути масштаб">⤢</button>
              <button type="button" id="zoom-in" title="Збільшити">+</button>
            </div>
          </div>
```
Replace with (new `.preview-view-controls` group added on the left, before
the existing zoom controls):
```html
          <div class="preview-head">
            <div class="preview-view-controls">
              <button type="button" class="view-mode-btn" id="view-mode-contour" title="Тільки контур порізки" aria-pressed="false">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="4 3"/>
                </svg>
              </button>
              <button type="button" class="view-mode-btn" id="view-mode-print" title="Тільки друк" aria-pressed="false">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="3" y="4" width="18" height="16" rx="2"/>
                  <circle cx="8.5" cy="9.5" r="1.5"/>
                  <path d="M21 16l-5.5-5.5a2 2 0 0 0-2.8 0L3 20"/>
                </svg>
              </button>
              <button type="button" class="view-mode-btn is-active" id="view-mode-together" title="Контур і друк разом" aria-pressed="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="3" y="7" width="13" height="13" rx="2"/>
                  <path d="M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/>
                </svg>
              </button>
              <span class="view-controls-divider" aria-hidden="true"></span>
              <label class="contour-color-swatch" title="Колір контуру порізки">
                <input type="color" id="contour-color-input" value="#00ff00">
              </label>
            </div>
            <div class="preview-zoom-controls">
              <button type="button" id="zoom-out" title="Зменшити">−</button>
              <button type="button" id="zoom-reset" title="Скинути масштаб">⤢</button>
              <button type="button" id="zoom-in" title="Збільшити">+</button>
            </div>
          </div>
```
(`view-mode-together` starts with `is-active`/`aria-pressed="true"` — matches
the default state set in STEP 3.)

## STEP 2 — web/style.css — new control styles, dark mode, remove the grey preview box

**2a.** Change `.preview-head`'s `justify-content` from `flex-end` to
`space-between` so the new group sits left and zoom stays right:
```css
.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
```

**2b.** Add near `.preview-zoom-controls` (reusing the same 28×28 button
look):
```css
.preview-view-controls { display: flex; align-items: center; gap: 4px; }
.view-mode-btn {
  width: 28px; height: 28px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--card-bg);
  color: var(--muted);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.view-mode-btn:hover { background: var(--surface); color: var(--fg); }
.view-mode-btn.is-active { background: var(--ink); color: #fff; border-color: var(--ink); }
.view-controls-divider { width: 1px; height: 18px; background: var(--border); margin: 0 4px; }
.contour-color-swatch {
  width: 28px; height: 28px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  overflow: hidden;
  display: flex;
  padding: 0;
  cursor: pointer;
}
.contour-color-swatch input[type="color"] {
  width: 100%; height: 100%;
  border: none; padding: 0; margin: -4px;
  cursor: pointer; background: none;
}
```
(the `margin: -4px` on the color `<input>` compensates for the browser's
own default padding around a color swatch input so it fills the 28×28 box
edge-to-edge — check this visually in the smoke test and adjust the value
if your browser renders it with visible white edges.)

**2c.** `.view-mode-btn.is-active` uses `background: var(--ink)`, and
`--ink` flips from dark to light in dark mode (see `.sidebar-tab.is-active`,
which already had to be fixed for exactly this reason — a past session hit
this same bug: white-on-white text after the flip). Add the matching fix in
the existing `@media (prefers-color-scheme: dark)` block, right next to
`.sidebar-tab.is-active { color: #111111; }`:
```css
  .view-mode-btn.is-active { color: #111111; }
```

**2d.** Remove the grey background/border from `.preview-canvas` — find:
```css
.preview-canvas {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  ...
```
Change only the `border` and `background` lines:
```css
.preview-canvas {
  flex: 1;
  min-height: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  ...
```
Leave every other property on `.preview-canvas` (and `.preview-canvas.is-panning`)
exactly as-is.

## STEP 3 — web/app.js — state, element refs, and button wiring

**3a.** Near the other element refs (after `const zoomResetBtn = el("zoom-reset");`), add:
```js
const viewModeContourBtn = el("view-mode-contour");
const viewModePrintBtn = el("view-mode-print");
const viewModeTogetherBtn = el("view-mode-together");
const contourColorInput = el("contour-color-input");
```

**3b.** Near the top-level state variables (wherever `let isStickerPack = false;`
or similar module-level state lives), add:
```js
// Preview-only display state — persists across file/task switches within
// the session (unlike zoom, which resets per selection); not sent to the
// server, doesn't affect anything generated.
let viewMode = "together"; // "together" | "contour" | "print"
let contourColor = "#00ff00";
```

**3c.** Add the click/input handlers (near the other event-listener
registrations):
```js
function setViewMode(mode) {
  viewMode = mode;
  for (const [btn, m] of [[viewModeContourBtn, "contour"], [viewModePrintBtn, "print"], [viewModeTogetherBtn, "together"]]) {
    const active = m === mode;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", String(active));
  }
  if (selectedIndex >= 0) renderSelectedPreview();
}
viewModeContourBtn.addEventListener("click", () => setViewMode("contour"));
viewModePrintBtn.addEventListener("click", () => setViewMode("print"));
viewModeTogetherBtn.addEventListener("click", () => setViewMode("together"));

contourColorInput.addEventListener("input", () => {
  contourColor = contourColorInput.value;
  if (selectedIndex >= 0) renderSelectedPreview();
});
```
(`renderSelectedPreview()` calls `resetZoom()` at its top — that's existing,
unrelated behavior for zoom only; don't change it. If re-triggering a zoom
reset on every view-mode/color click turns out to feel wrong in the smoke
test, call `renderLayout(...)` directly instead of the whole
`renderSelectedPreview()` — your call, note which you picked and why in the
Summary.)

## STEP 4 — web/app.js — gate per-cell content in renderLayout, recolor the contour

Find the per-cell rendering block (inside `renderLayout`'s `for (let row...) for (let col...)` loop):

```js
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
```

Replace with (decouples "print" visibility from "contour" visibility — see
STEP heading comment for why; `showPrint`/`showContour` are computed once
before the row/col loop starts, not per-cell — put that computation right
above the `for (let row ...)` line):

```js
  const showPrint = viewMode !== "contour";
  const showContour = viewMode !== "print";
```

```js
      if (showPrint && !hasThumb) {
        previewSvg.appendChild(svgEl("rect", {
          x: cellX, y: cellY, width: layout.cell_w, height: layout.cell_h,
          fill: "#e3e3e3", stroke: "none",
        }));
      }

      const wantsNestedSvg = hasThumb && (showPrint || (shapeMode && showContour));
      if (wantsNestedSvg) {
        // Nested <svg> clips to the cell automatically, so rotated/oversized
        // artwork never bleeds past the cut line. Built whenever EITHER the
        // image or the shape-mode contour path needs to render, since both
        // share this same clip/transform container — only append the pieces
        // the current view mode actually wants.
        const nested = svgEl("svg", {
          x: cellX, y: cellY, width: layout.cell_w, height: layout.cell_h,
          viewBox: `0 0 ${layout.cell_w} ${layout.cell_h}`,
        });

        if (showPrint) {
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
        }

        if (shapeMode && artwork.contour && showContour) {
          // Cut-contour outline, sharing the exact same translate/rotate the
          // image above uses (when present) so it always lines up with the
          // raster underneath it. Color is the user's chosen contourColor,
          // not a fixed black — see STEP heading's contour-color note.
          const path = svgEl("path", {
            d: contourPathD(artwork.contour.subpaths),
            fill: "none",
            stroke: contourColor,
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

      if (!shapeMode && showContour) {
        // Rectangular mode has no traced vector contour — the cell edge
        // itself is the cut line, so it plays the "контур" role here.
        // Color is the user's chosen contourColor (see STEP heading).
        previewSvg.appendChild(svgEl("rect", {
          x: cellX, y: cellY, width: layout.cell_w, height: layout.cell_h,
          fill: "none", stroke: contourColor, "stroke-width": strokeW * 0.6,
        }));
      }
```

The `if (outlineCheckbox.checked) { ... }` block right after this stays
completely unchanged — don't touch it.

## STEP 5 — web/app.js — feed-direction triangle

Add near the existing corner-registration-marks block (after the
`for (const { cx, cy, dirX, dirY } of corners) { ... }` loop, before the
`if (isStickerPack) { ... corner-guide ticks ... }` block) — always drawn,
independent of view mode, matching `server/core/marks.py`'s
`_draw_feed_arrow` geometry (`FEED_ARROW_WIDTH_MM`/`HEIGHT_MM` = 3,
`FEED_ARROW_OFFSET_MM` = 5 — apex 5mm from the sheet's top edge, centered
horizontally). Note the preview SVG's viewBox is already top-down
(distance-from-top, same sense `mark_offset` is already used above for
`cy`), unlike reportlab's bottom-up page space in the Python version, so
this does NOT need the `sheet_h - ...` flip that file's version has:

```js
  // Feed-direction triangle — visual match for server/core/marks.py's
  // _draw_feed_arrow. Keep these three numbers in sync with
  // FEED_ARROW_WIDTH_MM/FEED_ARROW_HEIGHT_MM/FEED_ARROW_OFFSET_MM there if
  // they ever change. Always drawn regardless of view mode — same as the
  // corner registration marks above, this is a print-alignment mark, not
  // per-cell content.
  const feedApexY = 5, feedBaseY = 5 + 3, feedHalfW = 3 / 2;
  const feedCx = sheetW / 2;
  previewSvg.appendChild(svgEl("polygon", {
    points: `${feedCx},${feedApexY} ${feedCx - feedHalfW},${feedBaseY} ${feedCx + feedHalfW},${feedBaseY}`,
    fill: "#111111",
  }));
```

## STEP 6 — SMOKE TEST

1. Restart the server. Open each of the three sidebar modes, upload a test
   file in each, confirm the preview renders without console errors.
2. In "Прямокутні наліпки": click "контур" — raster disappears, cell-border
   rectangles remain (default green). Click "друк" — border rectangles
   disappear, raster remains. Click "разом" — both show. Same three checks
   in "Фігурні стікери"/"Стікерпаки", but "контур" should show the actual
   traced dashed cut-contour path (not a plain rectangle) instead.
3. Change the color picker to a different color (e.g. red) — confirm both
   the rect-mode cell border AND the shape-mode dashed contour path
   immediately re-render in the new color; confirm it does NOT change the
   color of anything in a real generated zip (registration marks, the
   vector "- контур.pdf" file, the .plt) — generate one batch and check.
4. Confirm the feed-direction triangle appears in the preview near the top
   center of the sheet, roughly where the real generated print PDF's own
   triangle sits (open a generated print PDF alongside the preview to
   compare position) — in all three modes.
5. Confirm the grey box around the preview canvas is gone (white/blends
   with the card background) — in light mode and dark mode
   (`prefers-color-scheme: dark` — use your browser devtools to emulate it,
   or your OS dark mode).
6. Dark mode: confirm the active view-mode button (default "разом" on load)
   has legible icon-on-background contrast, not a light icon disappearing
   into a light flipped `--ink` background — this is the same bug class as
   the sidebar-tab fix from an earlier session, don't let it recur here.
7. Select a different file (or switch sidebar tabs) while a non-default
   view mode and a non-default contour color are active — confirm BOTH
   persist (per the STEP CONTEXT note — this is deliberately different from
   zoom, which does reset).
8. Regression: `outline-checkbox`'s 0.1mm decorative border still appears
   independently of view mode and is still black, in all three modes.

## STEP 7 — CLAUDE.md

Append a short entry to "Останній стан": the new контур/друк/разом preview
toggle (and what "контур" means per-mode), the contour-color picker
(preview-only, default `#00ff00`), the feed-direction triangle, and the
removed grey preview-canvas background/border.

## STEP 8 — COMMIT + PUSH

```
git add web/index.html web/style.css web/app.js CLAUDE.md
git commit -m "feat: preview view-mode toggle (contour/print/together), contour color picker, feed-direction triangle; remove grey preview box"
git push origin main
```

## STEP 9 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🔴 Not implemented
### 🧪 Smoke test results (all 8 points from STEP 6)
### 📋 Known issues for next session
