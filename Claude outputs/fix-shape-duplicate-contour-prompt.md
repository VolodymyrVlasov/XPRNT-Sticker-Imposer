You are working in the project root. This is a bugfix to the already-merged shaped-
stickers feature, found by the user testing with a REAL production file.

⚠️ This prompt SUPERSEDES an earlier one I may have sent you titled roughly
"fix(shape): deduplicate identical cut-contour subpaths" — if you have not run that
one yet, ignore it and use this one instead; it covers the same file with a more
precise, better-diagnosed fix (both the original geometric-dedup idea AND the real
root cause, described below).

Pull latest main first.

This is a small, single-file task: per this project's convention for micro/small
tasks, commit directly to main, no feature branch, no PR needed.

## GOAL — root cause (already diagnosed precisely, don't re-derive it)

User reported: the PLT cut file for a shaped-sticker job cut every cell TWICE. They
also opened the source artwork in Illustrator and saw, under one Group, two `<Path>`
objects with identical geometry — one a real 0.1mm green stroke, the other appearing
to have no color/width.

I inspected the exact real file with PyMuPDF's `page.get_drawings(extended=True)`
(the non-extended `get_drawings()` this module currently uses is NOT enough — see
why below) and found the precise mechanism:

- Illustrator exported the cut line TWICE, each copy wrapped in its own nested
  transparency-group Form XObject (`/Group /S /Transparency`).
- One group has `opacity: 0.0` — genuinely, structurally invisible, not "no
  color/width" but zero composite opacity. It contains a stroke of width 1.0pt,
  color green (identical geometry to the other copy).
- The other group has `opacity: 1.0` — the real, visible cut line. Its stroke width
  is 0.283pt, which is exactly 0.1mm (0.283 / 2.83465 pt-per-mm ≈ 0.0999mm) — this is
  the 0.1mm green stroke the user saw in Illustrator.

Critically: PyMuPDF's plain `get_drawings()` (what `inspect_shape_pdf()` currently
calls) reports BOTH copies as ordinary, fully-opaque strokes with real color and
width — it does NOT account for the outer transparency-group opacity the Form
XObject was invoked under. So a naive "only keep paths that have a color and a
width" check (my first instinct too) would NOT have caught this, since both copies
report a real color and a real width at that API level. The actual signal only
shows up in `get_drawings(extended=True)`, which additionally emits `"type":
"group"` entries (with `opacity` and a `level` depth) interleaved with the draw
items in document order — walking that stream and tracking CUMULATIVE opacity
through nested groups is what correctly identifies the invisible copy.

This is a plausible, likely-recurring pattern in real client files: a designer
hides a duplicate/old copy of the cut line via opacity instead of deleting it,
and forgets to remove it before export.

The fix belongs in `server/core/shape_inspect.py`, specifically in
`inspect_shape_pdf()`, since every consumer (`/api/analyze-shape`, `/api/generate-
shape`, `/api/generate-batch-shape`) reads its `subpaths` list as the single source
of truth — fixing it there fixes the browser preview, the contour PDF, and the PLT
file all at once. No changes needed to `shape_plt_writer.py`, `shape_contour_pdf.py`,
`shape_print_pdf.py`, or any route file.

## STEP 1 — UPDATE: server/core/shape_inspect.py

### 1a. Add an opacity-aware drawing filter (the real fix)

Add a helper that walks `page.get_drawings(extended=True)` and returns only the
draw entries (type `"s"`/`"f"`/`"fs"` with an `"items"` key) whose CUMULATIVE
opacity — through however many nested transparency groups wrap it, PLUS its own
local `stroke_opacity`/`fill_opacity` — is above a negligible threshold. Groups
nest by the `"level"` field extended mode provides: an entry belongs to the most
recently-seen group whose level is less than its own, and a group "closes" (is
popped) as soon as a later entry appears at a level less than or equal to that
group's own level (document order tracks this correctly with a simple stack, no
need to look at `q`/`Q` operators directly).

```python
_OPACITY_EPS = 0.01  # below this, treat a path as invisible/never painted


def _visible_drawings(page) -> list[dict]:
    """page.get_drawings() (non-extended) reports every stroke/fill's LOCAL color
    and width, but not the opacity of any transparency GROUP (Form XObject) it may
    be nested inside — so a duplicate cut-line path hidden via 0% group opacity
    (found on a real client file: Illustrator wraps each path in its own
    transparency group on export, and a hidden "backup" copy had its group set to
    opacity 0 instead of being deleted) still comes back looking like an ordinary,
    fully visible stroke. get_drawings(extended=True) additionally interleaves
    "group" entries (with their own opacity and nesting "level") in document
    order, which lets us track cumulative opacity through nested groups and drop
    anything that is not actually visible.
    """
    stack: list[tuple[int, float]] = []  # (level, cumulative opacity at this depth)

    def current_opacity() -> float:
        return stack[-1][1] if stack else 1.0

    visible: list[dict] = []
    for entry in page.get_drawings(extended=True):
        level = entry.get("level", 0)
        while stack and stack[-1][0] >= level:
            stack.pop()

        etype = entry.get("type")
        if etype == "group":
            stack.append((level, current_opacity() * entry.get("opacity", 1.0)))
        elif etype == "clip":
            continue
        elif entry.get("items"):
            local = 1.0
            so = entry.get("stroke_opacity")
            fo = entry.get("fill_opacity")
            if etype == "s" and so is not None:
                local = so
            elif etype == "f" and fo is not None:
                local = fo
            elif etype == "fs":
                local = min(so if so is not None else 1.0, fo if fo is not None else 1.0)
            if current_opacity() * local > _OPACITY_EPS:
                visible.append(entry)
    return visible
```

Then in `inspect_shape_pdf()`, replace:

```python
drawings = [d for d in page.get_drawings() if d.get("items")]
```

with:

```python
drawings = _visible_drawings(page)
```

The rest of `inspect_shape_pdf()` (bbox union, subpath grouping via
`_group_subpaths_pt`, the "no vector geometry found" validation error) reads the
same `d["items"]` / `d["rect"]` keys either way — `get_drawings(extended=True)`'s
draw-type entries carry the exact same keys as the non-extended ones, just with an
extra `level` field we don't otherwise use — so nothing else in the function needs
to change.

### 1b. Also add geometric dedup as a defense-in-depth safety net

Separately from the opacity fix above — which is the real root cause here — also
guard against the simpler case of two subpaths that are BOTH fully visible and
happen to be exactly geometrically identical (e.g. a genuine accidental duplicate
paste, no hidden opacity involved). After `subpaths` is fully built in
`inspect_shape_pdf()`, right before `return ShapeArtworkInfo(...)`, dedup by a
tight-tolerance geometric fingerprint, keeping first occurrence:

```python
# Rounding for the duplicate-detection fingerprint below. Intentionally much
# tighter than the ~0.01mm float-noise tolerance already accepted elsewhere in
# this module (see the dim_w/dim_h rounding comment above) — this exists only to
# catch true bit-for-bit duplicate paths, never to merge two subpaths that are
# merely similar (e.g. a shape with a hole has two subpaths that must both survive).
_DEDUP_DECIMALS = 3  # ~0.001mm


def _subpath_key(sp: "ContourSubpath") -> tuple:
    def r(v: float) -> float:
        return round(v, _DEDUP_DECIMALS)

    key = [("start", r(sp.start[0]), r(sp.start[1]))]
    for seg in sp.segments:
        key.append((seg.kind, tuple(r(v) for v in seg.points)))
    return tuple(key)
```

```python
seen: set = set()
deduped: list[ContourSubpath] = []
for sp in subpaths:
    key = _subpath_key(sp)
    if key in seen:
        continue
    seen.add(key)
    deduped.append(sp)
subpaths = deduped
```

Do not touch the `raw_bbox` / `dim_w` / `dim_h` computation — a duplicate (visible
or not) contributes the same rect to the union either way, so that part is already
a no-op regardless of dedup.

## STEP 2 — SMOKE TEST

1. Build a synthetic shaped-sticker test PDF reusing the established pattern from
   earlier stages (rounded-rect + bezier corners + 1mm bleed via reportlab), but
   draw the cut-contour path TWICE at the same geometry: once with
   `canvas.setStrokeAlpha(0)` (or your reportlab version's equivalent — if
   unavailable, use an ExtGState with `/CA 0` via `canvas._doc` internals or
   pikepdf post-processing) before stroking it, and once normally
   (`setStrokeAlpha(1)`) with a different stroke width, mirroring the real file's
   pattern (one invisible copy, one real copy, different widths). Confirm
   `inspect_shape_pdf()` on this file returns exactly 1 subpath (the visible one),
   not 2.
2. Also build a variant where BOTH copies are fully visible (opacity 1 both) and
   geometrically identical (no opacity trick at all) — confirm the geometric-dedup
   safety net alone still collapses this to 1 subpath.
3. Run the full `/api/generate-shape` flow (`cut_contour: true`) on the invisible-
   duplicate file, unzip, and confirm via a plain-text parse of the `.plt` file:
   exactly ONE `U...` pen-up path per grid cell (not two). Paste the before/after
   per-cell `U`-count in your summary.
4. Regression — build a PDF with two genuinely DIFFERENT, both-visible closed
   subpaths (e.g. an outer contour plus a separate small closed loop simulating a
   hole) and confirm `len(subpaths) == 2` is preserved (the fix must not merge or
   drop subpaths that are merely similar, only ones that are truly invisible or
   truly identical).
5. Full regression pass: existing single-file and batch shaped-sticker generation
   (synthetic PDFs without the duplicate/invisible pattern) produce identical
   output to before this fix, and rectangular-mode generation (single + batch) is
   unaffected.
6. If you still have access to the real file(s) the user tested with (they may be
   dropped into the repo somewhere for you, e.g. under a `test_assets/` or similar
   folder — check before assuming they aren't there), run `/api/generate-shape` on
   the real one too as extra confirmation and note the result in your summary; if
   not available, the synthetic repro above is sufficient.

## STEP 3 — UPDATE: CLAUDE.md "Останній стан"

Append ONE new entry at the end of the changelog section (after the existing
2026-09-17 "Фігурні стікери" entry — do not edit that entry, add a new one below
it):

```
- **2026-09-17** — Виправлено дублювання контуру порізки у фігурних стікерах.
  Причина (знайдено на реальному файлі клієнта, підтверджено через
  `get_drawings(extended=True)`): дизайнер продублював лінію різу в Illustrator і
  замість видалення сховав стару копію через прозорість (opacity групи = 0%),
  а не видимість шару — обидві копії мають однакову геометрію, різну товщину лінії
  (1.0pt невидима і 0.283pt = 0.1мм видима). Звичайний `page.get_drawings()`
  (без extended-режиму) не бачить прозорість вкладеної transparency-групи і
  показує обидві копії як однаково видимі strokes — тому проста перевірка
  "чи є колір/товщина" нічого б не відфільтрувала. Виправлено в
  `inspect_shape_pdf` (`server/core/shape_inspect.py`) двома шарами: (1) основний
  фікс — підрахунок кумулятивної прозорості через вкладені transparency-групи
  (`get_drawings(extended=True)`), контури з нульовою сукупною прозорістю
  ігноруються; (2) додатковий запобіжник — геометричний дедуп повністю
  ідентичних (з точністю ~0.001мм) підконтурів на випадок, коли обидві копії
  видимі. Підконтури з дійсно різною геометрією (напр. форма з отвором) не
  зачіпаються. Виправлення в одному файлі (`shape_inspect.py`) автоматично
  закриває і прев'ю, і contour-PDF, і PLT, бо всі вони читають один і той самий
  список підконтурів.
```

Include this file in the same commit as the code fix — write and commit it
atomically together, not as a separate uncommitted edit.

## STEP 4 — COMMIT + PUSH

git add server/core/shape_inspect.py CLAUDE.md
git commit -m "fix(shape): ignore invisible/duplicate cut-contour paths (opacity + geometric dedup)"
git push origin main

## STEP 5 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (before/after per-cell U-count, both dedup paths verified separately, hole-shape regression, full regression pass)
### 📋 Known issues for next session
