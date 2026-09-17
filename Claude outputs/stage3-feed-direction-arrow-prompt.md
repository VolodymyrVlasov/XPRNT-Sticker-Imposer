You are working in the project root. This is stage 3 of the same multi-stage
redesign as the previous two stages (backend + a later frontend overhaul —
this stage is backend-only, like stages 1 and 2). Pull latest `main` first —
it must already contain stage 1 (shape sizing from the PDF page) and stage 2
(per-batch-item orientation/grid/quantity). If it doesn't, stop and report —
don't proceed on top of a stale base.

Per the user's explicit instruction, this whole line of work (every stage,
regardless of size) commits and pushes directly to `main` — no feature
branches, no PRs, for anything in this effort.

## GOAL — a printed feed-direction arrow

An earlier version of this app printed a small arrow/triangle at the top of
the sheet showing which way to load it into the plotter. That got lost at
some point and needs to come back. Per the user (with a reference photo of a
real production sheet): a solid black triangle, pointing up, centered
horizontally across the sheet width, sitting at roughly the same height as
the top corner registration marks. It must be physically drawn into the
generated PDF content — not a UI-only hint — because the physical sheet is
what the person loading the plotter actually looks at.

`server/core/marks.py`'s `draw_registration_marks(c, grid)` is the single
shared function that draws the 4 corner L-bracket registration marks, and it
is called from exactly three places — confirmed by grep, no other call
sites:

- `server/core/pdf_template.py` — the rectangular-mode template PDF, which
  `server/core/print_pdf.py` then merges in as the bottom layer of the final
  rectangular print PDF. So the template PDF (exposed in the batch/single zip
  for manual reuse) and the final print PDF both get whatever
  `draw_registration_marks` draws.
- `server/core/shape_print_pdf.py` — builds a throwaway marks-only PDF via
  `draw_registration_marks`, merges it as the bottom layer of the shaped-
  sticker print PDF, then discards it. This is the ONLY marks layer for shape
  mode — there's no separate template PDF there.
- `server/core/cut_contour_pdf.py` — the rectangular mode's optional vector
  cut-contour reference PDF (for third-party cutting software) also draws the
  same registration marks, specifically so its vector paths can be aligned
  against the printed sheet.

So adding the arrow inside `draw_registration_marks` itself is the one
change needed to get it onto every one of these outputs, with no changes to
any of the three call sites — they already all set the same solid fill color
(`K100`, pure black) on their canvas before calling it, so the arrow will
render solid black automatically, no extra styling needed. (Shape mode's
`server/core/shape_contour_pdf.py`, the shaped-sticker vector cut-contour
reference file, deliberately does NOT call `draw_registration_marks` at all
— by existing design, per its own docstring, registration marks only belong
on the actual printed sheet or a reference file meant to align against it.
Leave that file untouched; this change doesn't reach it.)

## STEP 1 — UPDATE: server/core/marks.py

```python
"""Corner registration marks and the feed-direction arrow, shared by the
template PDF, the shaped-sticker print PDF, and the vector cut-contour
reference PDF — everywhere a person or a plotter aligns against the physical
printed sheet.
"""

from server.core.layout import Grid
from server.utils.constants import MM

# Feed-direction arrow: a solid triangle pointing toward the top sheet edge,
# centered horizontally, telling the operator which way to load the sheet
# into the plotter. Sized to sit in roughly the same vertical band as the
# top corner marks' own 9mm arms (see draw_registration_marks) — not
# fine-tuned pixel-for-pixel against the reference photo yet. Check the
# smoke-test renders and adjust these two constants if the size/position
# looks off before calling this done.
FEED_ARROW_WIDTH_MM = 8.0
FEED_ARROW_HEIGHT_MM = 8.0


def draw_registration_marks(c, grid: Grid) -> None:
    """Four filled L-brackets, each pointing from its sheet corner toward the
    interior, plus a feed-direction arrow centered at the top of the sheet.
    """
    sheet_w, sheet_h, mo = grid.sheet_w, grid.sheet_h, grid.mark_offset

    def pt(v: float) -> float:
        return v * MM

    def fr(x: float, y: float, w: float, h: float) -> None:
        """Filled rect. x,y = top-left origin, Y axis pointing down, all mm."""
        c.rect(pt(x), pt(sheet_h - y - h), pt(w), pt(h), fill=1, stroke=0)

    fr(mo,                  mo - 0.5,            9, 1)
    fr(mo - 0.5,            mo,                  1, 9)
    fr(sheet_w - mo - 9,    mo - 0.5,            9, 1)
    fr(sheet_w - mo - 0.5,  mo,                  1, 9)
    fr(mo,                  sheet_h - mo - 0.5,  9, 1)
    fr(mo - 0.5,            sheet_h - mo - 9,    1, 9)
    fr(sheet_w - mo - 9,    sheet_h - mo - 0.5,  9, 1)
    fr(sheet_w - mo - 0.5,  sheet_h - mo - 9,    1, 9)

    _draw_feed_arrow(c, sheet_w, sheet_h, mo)


def _draw_feed_arrow(c, sheet_w: float, sheet_h: float, mark_offset: float) -> None:
    """Solid triangle, apex toward the top sheet edge, centered horizontally
    across the sheet width — indicates which edge to feed into the plotter
    first. Roughly spans the same vertical band as the top corner marks.
    """
    def pt(v: float) -> float:
        return v * MM

    cx = sheet_w / 2.0
    apex_y = mark_offset - 0.5  # distance from the top sheet edge, mm — same
    # -0.5 baseline the top corner marks' own horizontal bars use.
    base_y = apex_y + FEED_ARROW_HEIGHT_MM
    half_w = FEED_ARROW_WIDTH_MM / 2.0

    p = c.beginPath()
    p.moveTo(pt(cx),           pt(sheet_h - apex_y))
    p.lineTo(pt(cx - half_w),  pt(sheet_h - base_y))
    p.lineTo(pt(cx + half_w),  pt(sheet_h - base_y))
    p.close()
    c.drawPath(p, fill=1, stroke=0)
```

## STEP 2 — SMOKE TEST (with rendered visual review)

This one needs an eyeball check, not just assertions — a misplaced or
oddly-sized arrow is a visual judgment call, not something a unit test alone
can catch.

1. Run the existing rectangular single-file flow (`/api/generate`) and the
   shaped-sticker single-file flow (`/api/generate-shape`, with
   `cut_contour: true`) against small test artworks (reuse or adapt the
   synthetic test PDFs from earlier stages), at the default SRA3 sheet size
   and default `mark_offset`.
2. Using PyMuPDF (`fitz`, already a project dependency — see `server/core/
   thumbnail.py` for the existing rasterization pattern), render page 0 of
   EACH of these four outputs to a PNG at a resolution high enough to clearly
   see the marks (e.g. 200+ DPI): the rectangular template PDF, the
   rectangular print PDF, the shaped-sticker print PDF, and (with
   `cut_contour: true`) the rectangular vector cut-contour PDF. Save all four
   PNGs somewhere easy to find (e.g. a top-level `_smoke_renders/` folder,
   gitignored / not committed) and crop or additionally save a zoomed-in crop
   of just the top-center band of each, so the arrow is clearly visible.
3. Visually confirm in those renders: a solid black triangle, apex pointing
   up toward the sheet's top edge, horizontally centered on the sheet width,
   sitting close to the same height as the top-left/top-right corner marks —
   not overlapping the corner marks themselves, not overlapping any sticker
   cell, and clearly visible against the white background.
4. Regression: confirm the 4 corner registration marks themselves are
   unchanged in position/size in all four renders (only the new arrow was
   added).
5. Batch flows (`/api/generate-batch`, `/api/generate-batch-shape`) — spot-
   check one output from each, same visual check as point 3.

In your summary, describe what you saw in the renders (or attach/paste them
if your environment lets you) — if the arrow's size or vertical position
looks off (too close to the corner marks, too small/large, etc.), it's fine
to adjust `FEED_ARROW_WIDTH_MM`/`FEED_ARROW_HEIGHT_MM`/the `- 0.5` offset in
`_draw_feed_arrow` and re-render before finalizing; just say in the summary
what you changed and why. This is expected to need one round of visual
tuning — get it roughly right and flag it for a follow-up look rather than
guessing indefinitely.

## STEP 3 — UPDATE: CLAUDE.md "Останній стан"

Read the current file first — stage 2 added a sub-bullet ending with a
"Наступні стадії" list that starts "3 — стрілка напряму подачі...". Add a
new sub-bullet under that same dated entry (or a new dated entry if today's
date has moved on) documenting stage 3's completion, and trim stage 3 off
the front of the "Наступні стадії" list (renumber so it now starts from 4).
Something in this spirit:

```
  **Стадія 3 (бекенд, стрілка напряму подачі) — виконано.** Додано друковану
  стрілку (суцільний чорний трикутник, вістрям вгору, по центру ширини
  аркуша, на висоті верхніх кутових міток приводки) у
  `server/core/marks.py`, `draw_registration_marks()` — автоматично
  потрапляє на всі три виходи, що використовують цю функцію: шаблон PDF і
  фінальний друк-PDF (прямокутний режим), друк-PDF (фігурний режим),
  векторний PDF контуру різу (прямокутний режим). Розмір/позиція підібрані
  орієнтовно (`FEED_ARROW_WIDTH_MM`/`FEED_ARROW_HEIGHT_MM`), звірені з
  рендером, але не з референсним фото піксель-в-піксель — можливе
  подальше тонке підлаштування за фідбеком користувача.

  Наступні стадії (заплановано, ще не почато): 4-8 — фронтенд: вкладки
  картки параметрів, уніфікація списку файлів (завжди список), попап
  властивостей файлу (сітка/орієнтація/кількість), зум/пан прев'ю, прибрати
  індикатор "вміщується", компактна статистика, ширини карток 2/5:3/5,
  відступ сайдбару "Типи розкладки".
```

## STEP 4 — COMMIT + PUSH

```
git add server/core/marks.py CLAUDE.md
git commit -m "feat(print): add a printed feed-direction arrow to the sheet marks"
git push origin main
```

## STEP 5 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🧪 Smoke test results (all 5 points from STEP 2, including what the renders showed)
### 📋 Known issues for next session
