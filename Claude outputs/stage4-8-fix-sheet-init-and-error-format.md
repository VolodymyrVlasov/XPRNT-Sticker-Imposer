You are working in the project root. This is a small, targeted bug-fix
follow-up to the stage 4-8 frontend overhaul just merged to `main` (commit
`0547ebc`). Pull latest `main` first — confirm that commit is present.

First things first: **restart the local dev server** before testing anything
in this task — the previous `run_server.py`/`uvicorn` process on port 8000
is still running with pre-stage-4-8 code loaded in memory (it never got
restarted after the last few pushes), which is why a fresh
`run_server.py` launch just failed with "only one usage of each socket
address" (`WinError 10048`). Stop that old process (find and kill the
`python`/`uvicorn` process bound to port 8000 — Task Manager or `netstat
-ano | findstr :8000` + `taskkill /PID ... /F` on Windows), then start a
fresh one so you're testing the actual current code.

I (the Cowork session) drove the running app through a real browser just
now and found two real bugs, confirmed live, not just from reading the
code:

## BUG 1 (the important one) — Tab 2's sheet size never gets initialized

**Symptom:** upload any file (single or batch) → its row in the Tab 1 file
list stays stuck on "…" forever, the preview card never shows anything
beyond "Оберіть файл зі списку", and the generate button never enables —
even though the file analyzed successfully and appears in the list.

**Root cause:** `#sheet-w`/`#sheet-h` (Tab 2) never get populated with the
selected sheet preset's dimensions. Before this stage, `handleSingleFile`/
`handleBatchFiles` did this explicitly on every analyze:
```js
sheetSelect.value = data.sheet_name;
onSheetChanged(); // copies config.sheet_presets[value] into sheet-w/sheet-h
```
`onSheetChanged()` is now only ever wired to `sheetSelect`'s own `change`
event — nothing calls it on page load or when the first file is added. So
`sheetWInput.value`/`sheetHInput.value` stay `""` forever (until/unless the
user manually touches the sheet dropdown), `applyTab2Params()` reads them as
`0`, `appliedParams.sheetW`/`sheetH` stay `0`, and every `/api/layout` call
this triggers is either skipped by a guard or fails — either way, no item
ever gets a `layout` or a `layoutError`, so the list row is stuck on the
"…" placeholder forever with no error shown anywhere.

**Fix:** call `onSheetChanged()` once at the end of `loadConfig()`, right
after setting `markOffsetInput.value`/`fieldMarginInput.value` from
`config.defaults`:

```js
async function loadConfig() {
  // ...existing body...
  markOffsetInput.value = config.defaults.mark_offset;
  fieldMarginInput.value = config.defaults.field_margin;
  onSheetChanged(); // populate sheet-w/sheet-h from the default preset immediately,
  // not just after the sheet <select>'s own change event — otherwise Tab 2's
  // sheet size stays blank (and appliedParams.sheetW/sheetH stay 0) until the
  // user manually touches the dropdown, silently breaking every /api/layout
  // call for the first file(s) added.
}
```

This makes Tab 2 show a correct sheet size from the moment the page loads
(better UX on its own — no more blank fields before any file is uploaded),
and means `appliedParams` is correctly seeded before `addFiles()`'s
`if (!appliedParams.sheetW) applyTab2Params();` check ever runs.

Also double check `startNewTask()`/`switchMode()` (the reset path) — they
already call `onSheetChanged()` after resetting `sheetSelect.value =
"SRA3"`, so they should be fine, but verify after this fix that switching
sidebar tabs (rectangular ↔ shaped) still leaves Tab 2's sheet-w/h correctly
populated afterward too, not blank.

## BUG 2 — generation errors render as "[object Object]"

**Symptom:** trigger any generate-time error whose server response
`detail` is NOT a plain string — most commonly a FastAPI 422 validation
error, where `detail` is an array of `{type, loc, msg, input}` objects —
and the status line shows the literal text `[object Object]` instead of
anything useful.

**Root cause:** in `postForZip()` (and check `analyzeFile()`/
`analyzeShapeFile()` too, same pattern), the error path does roughly
`throw new Error((await res.json()).detail || detail)`. When `detail` is an
array, `new Error(arrayOfObjects)` stringifies it via `Array.prototype
.toString()`, which joins elements with `,` after calling `.toString()` on
each object — and a plain object's `.toString()` is `"[object Object]"`.
`setStatus(String(err.message || err), "error")` then displays that.

**Fix:** format a non-string `detail` into something readable before
throwing. FastAPI's validation-error shape is well-known
(`[{type, loc, msg, ...}, ...]`), so extract `.msg` from each entry when
present; fall back to `JSON.stringify` for anything else:

```js
function formatErrorDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => (e && typeof e === "object" && "msg" in e) ? e.msg : JSON.stringify(e)).join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return "Помилка";
}
```

Use it everywhere a response's `detail` is turned into a thrown `Error` —
at minimum `postForZip()`; check `analyzeFile()`/`analyzeShapeFile()` for
the same pattern and apply the same fix there if present.

## SMOKE TEST

1. Fresh server start (after killing the stale process). Upload 1 file
   (either mode) → confirm the list row resolves to `✓`/`!` within roughly
   the layout-fetch round trip, NOT stuck on "…", and the preview renders
   without any manual console intervention.
2. Confirm Tab 2's `#sheet-w`/`#sheet-h` already show the SRA3 preset's
   values immediately on page load, before any file is uploaded.
3. Trigger a real 422 from the batch generate endpoint (e.g. temporarily
   send a payload missing a required field via the browser console, or
   construct a scenario that reproduces one naturally) — confirm the status
   line now shows a readable message built from the validation errors'
   `msg` fields, not `[object Object]`.
4. Regression: everything stage 4-8's own STEP 10 already covered (upload,
   append, delete-with-reselect, properties popup validate/apply, deform,
   bleed recompute, Tab 2 buffered apply, zoom/pan, mixed batch generate,
   "Нове завдання" reset, mode-switch regression) still behaves correctly
   with this fix applied — this bug was likely masking some of those from
   ever being reachable in a real browser, so give the full list another
   pass now that the root blocker is fixed.

## CLAUDE.md

Append a short entry noting this fix (root cause + the one-line
`onSheetChanged()` call + the error-formatting helper), referencing that it
was found via live browser testing after the stage 4-8 merge, not caught by
the static trace that stage originally shipped with.

## COMMIT + PUSH

```
git add web/app.js CLAUDE.md
git commit -m "fix(web): initialize Tab 2 sheet size on load, format non-string generate errors"
git push origin main
```

## SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (all 4 points)
### 📋 Known issues for next session
