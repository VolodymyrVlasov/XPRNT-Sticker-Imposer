You are working in the project root.
Do NOT modify existing working code beyond what is listed below.
Base branch: `main`. No feature branch — per standing agreement for this
project, commit and push directly to `main` (single-maintainer repo, small
change). Frontend-only change — no backend/Python files touched.

## GOAL

Two small, unrelated frontend fixes in `web/style.css` and `web/app.js`:

1. Fix a CSS specificity bug: hovering the currently-active sidebar tab
   ("Прямокутні наліпки" / "Фігурні стікери") loses its dark background but
   keeps its white text, making the label unreadable. Also add a subtle
   `scale(1.05)` hover effect to all sidebar tabs.
2. New feature: the small fit-status badge ("✓" / "!" / "помилка") next to
   each file in the file list currently gives no reason when something is
   wrong. Add a hover popover on that badge showing exactly why — either the
   real request-error message (already available), or, for the very common
   "sticker doesn't fit the sheet" case, a computed explanation with actual
   numbers (sticker size, sheet size, margins, max grid that would fit vs.
   what's requested) — the case that prompted this: a user mis-typed a
   360×520mm sticker (not 36×52mm) and, without this popover, the bare "!"
   icon gave no clue why.

## STEP 1 — web/style.css — sidebar tab hover fix + scale

Find the existing rules (around line 119-143):

```css
.sidebar-tab {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  text-align: left;
  padding: 10px 10px;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--fg);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-family: inherit;
}
.sidebar-tab:last-child { margin-bottom: 0; }
.sidebar-tab:hover:not(:disabled) { background: var(--surface); }
.sidebar-tab.is-active {
  background: var(--ink);
  color: #fff;
  font-weight: 600;
}
```

Replace with:

```css
.sidebar-tab {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  text-align: left;
  padding: 10px 10px;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--fg);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-family: inherit;
  transition: background 0.12s ease, transform 0.12s ease;
}
.sidebar-tab:last-child { margin-bottom: 0; }
.sidebar-tab:hover:not(:disabled) { background: var(--surface); transform: scale(1.05); }
.sidebar-tab.is-active {
  background: var(--ink);
  color: #fff;
  font-weight: 600;
}
/* .sidebar-tab:hover:not(:disabled) above has higher specificity than
   .sidebar-tab.is-active (one more pseudo-class), so without this rule
   hovering the active tab flips its background back to the plain hover
   color while its text stays white (from .is-active, untouched by the
   hover rule) — unreadable. This reasserts the active background on
   hover; text color is intentionally NOT set here, so it still falls
   through correctly to .is-active's own color (and to this file's
   dark-mode .sidebar-tab.is-active color override below) — don't add a
   `color` declaration to this rule. transform: scale(1.05) from the
   plain hover rule above still applies here too (different property, no
   conflict). */
.sidebar-tab.is-active:hover:not(:disabled) { background: var(--ink); }
```

Do NOT change the `@media (prefers-color-scheme: dark)` block's existing
`.sidebar-tab.is-active { color: #111111; }` override — it's still correct
and needed as-is.

## STEP 2 — web/app.js — fit-status popover

### 2a. Add a helper that explains why a file's layout has an issue

Add this function near `updateGenerateEnabled()` / `effectiveMaterial()` (the
"generate enable/disable" section is a reasonable spot), or anywhere else
that reads well in context:

```js
// Human-readable reason a file's fit-status badge isn't a plain "✓" — either
// a real request-level error (already formatted), or, for the common
// doesn't-fit-the-sheet case, a computed explanation with actual numbers.
// Checked in this order deliberately: it.layout (with fits:false) carries
// far more detail than the generic string the properties-popup handler
// sometimes stores in it.layoutError for the same underlying case, so the
// numeric explanation wins whenever a layout result is present at all.
function describeLayoutIssue(it) {
  if (it.layout && !it.layout.fits) {
    const L = it.layout;
    const maxCount = L.max_cols * L.max_rows;
    return `Наклейка ${fmt(L.cell_w)} × ${fmt(L.cell_h)} мм не вміщується на аркуш ${fmt(L.sheet_w)} × ${fmt(L.sheet_h)} мм ` +
      `(відступ мітки ${fmt(L.mark_offset)} мм + відступ поля ${fmt(L.field_margin)} мм): максимум ${L.max_cols} × ${L.max_rows}` +
      `${maxCount ? ` (= ${maxCount} шт.)` : ""}, а задано ${L.cols} × ${L.rows}.`;
  }
  if (it.layoutError) return it.layoutError;
  return null;
}
```

### 2b. Add popover show/hide helpers

A `position: fixed` element appended to `document.body`, not a CSS-only
`position: absolute` child of the badge — `.file-list` has
`overflow-y: auto; max-height: 260px`, which would clip an absolutely
positioned popover for any row that isn't right at the top of the list. Add
this near the other preview/zoom helper functions, or right above
`renderFileList()`:

```js
// ── file-row fit-status popover ──────────────────────────────────────────

let fitPopoverEl = null;

function hideFitPopover() {
  if (fitPopoverEl) { fitPopoverEl.remove(); fitPopoverEl = null; }
}

function showFitPopover(anchorEl, text) {
  hideFitPopover();
  fitPopoverEl = document.createElement("div");
  fitPopoverEl.className = "fit-popover";
  fitPopoverEl.textContent = text;
  document.body.appendChild(fitPopoverEl);
  const r = anchorEl.getBoundingClientRect();
  const p = fitPopoverEl.getBoundingClientRect();
  let left = r.left + r.width / 2 - p.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - p.width - 8));
  let top = r.top - p.height - 8;
  if (top < 8) top = r.bottom + 8; // flip below the badge if there's no room above
  fitPopoverEl.style.left = `${left}px`;
  fitPopoverEl.style.top = `${top}px`;
}

// Safety net: don't leave a popover floating in place if the page scrolls
// or resizes out from under its anchor.
window.addEventListener("scroll", hideFitPopover, true);
window.addEventListener("resize", hideFitPopover);
```

### 2c. Wire it into `renderFileList()`

Current function:

```js
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
```

Replace with:

```js
function renderFileList() {
  hideFitPopover(); // don't leave a stale popover from before this re-render
  fileListEl.innerHTML = "";
  fileListEl.hidden = items.length === 0;
  fileListEmptyEl.hidden = items.length > 0;
  items.forEach((it, i) => {
    const row = document.createElement("div");
    row.className = "file-row" + (i === selectedIndex ? " is-selected" : "");
    const fitOk = it.layout && it.layout.fits;
    const fitLabel = it.layoutError ? "помилка" : (it.layout ? (fitOk ? "✓" : "!") : "…");
    const issueText = describeLayoutIssue(it);
    row.innerHTML = `
      <button type="button" class="file-row-main">
        <span class="file-row-name">${escapeHtml(it.filename)}</span>
        <span class="file-row-size">${fmt(it.dim_w)} × ${fmt(it.dim_h)} мм${shapeMode && it.actualW != null ? ` (факт. ${fmt(it.actualW)} × ${fmt(it.actualH)})` : ""}</span>
        <span class="file-row-fit ${it.layoutError || (it.layout && !fitOk) ? "is-nofit" : "is-fit"}${issueText ? " has-issue" : ""}">${fitLabel}</span>
      </button>
      <button type="button" class="file-row-icon file-row-props" title="Властивості" aria-label="Властивості">☰</button>
      <button type="button" class="file-row-icon file-row-delete" title="Видалити" aria-label="Видалити">✕</button>
    `;
    row.querySelector(".file-row-main").addEventListener("click", () => selectItem(i));
    row.querySelector(".file-row-props").addEventListener("click", (e) => { e.stopPropagation(); openPropsModal(i); });
    row.querySelector(".file-row-delete").addEventListener("click", (e) => { e.stopPropagation(); removeItem(i); });
    if (issueText) {
      const fitEl = row.querySelector(".file-row-fit");
      fitEl.addEventListener("mouseenter", () => showFitPopover(fitEl, issueText));
      fitEl.addEventListener("mouseleave", hideFitPopover);
    }
    fileListEl.appendChild(row);
  });
}
```

Do NOT change anything else in this file.

## STEP 3 — web/style.css — popover styling

Add near `.file-row-fit` (around line 369-371):

```css
.file-row-fit.has-issue { cursor: help; }
.fit-popover {
  position: fixed;
  z-index: 50;
  max-width: 260px;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.4;
  color: #fff;
  background: var(--ink);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-1);
  pointer-events: none;
}
```

And add one line to the existing `@media (prefers-color-scheme: dark)` block
(around line 547-572), alongside the other dark-mode text-color overrides —
`--ink` flips to a light color in dark mode (see the existing
`.sidebar-tab.is-active { color: #111111; }` line right above it, same
reason):

```css
  .fit-popover { color: #111111; }
```

## STEP 4 — SMOKE TEST

1. Restart the local server. Open the app, hover the active sidebar tab
   ("Прямокутні наліпки" is active by default) — background should stay
   dark, text stays clearly readable white, and the row should visibly grow
   ~5% on hover. Hover the inactive tab too — same scale effect, normal
   light hover background, no readability issue there either way.

2. Upload (or re-use) a rectangular test PDF sized so it does NOT fit the
   default SRA3 sheet (e.g. 360×520mm, the exact case that prompted this).
   Confirm the file row shows "!" — hover it and confirm a dark popover
   appears near the icon with a specific, numeric explanation (sticker size,
   sheet size, margins, max grid vs. requested grid) — not the old generic
   "Сітка не вміщується на аркуші з поточними параметрами" text.

3. Force a real request-level error (e.g. via the properties popup, set
   cols/rows to something that still round-trips as a genuine fetch/HTTP
   failure if you can construct one, or temporarily stop the server mid
   analyze to produce a network error) and confirm the popover falls back to
   showing that message.

4. Upload a file that DOES fit — confirm its badge is "✓", no `has-issue`
   class, no popover on hover, `cursor` stays default (not `help`).

5. Scroll the file list (with 5+ items) while a popover is open on a
   mid-list row — confirm the popover disappears rather than floating in a
   stale position. Resize the browser window similarly.

6. Dark mode: switch the OS to dark color scheme (or however you normally
   test this project's dark-mode block) and repeat points 1 and 2 — confirm
   both the active-tab hover text and the popover text stay readable (not
   white-on-light-background in either case).

## STEP 5 — CLAUDE.md

Append a short entry to "Останній стан" noting: the sidebar active-tab hover
fix + scale(1.05), and the new fit-status popover (with the numeric
doesn't-fit explanation) on the file list badge.

## STEP 6 — COMMIT + PUSH

```
git add web/style.css web/app.js CLAUDE.md
git commit -m "fix(web): active sidebar tab hover contrast + add fit-status popover with reason"
git push origin main
```

## STEP 7 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🔴 Not implemented
### 🧪 Smoke test results (all 6 points)
### 📋 Known issues for next session
