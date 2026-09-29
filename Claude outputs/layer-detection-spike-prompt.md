You are working in the project root.
Do NOT modify existing working code beyond what is listed below.
Base branch: `main`. No feature branch — per standing agreement for this
project, commit and push directly to `main` (single-maintainer repo).

## CONTEXT / DESIGN DECISIONS (already made — do not re-litigate these)

This is **Prompt 1 of 2** for a new capability: detecting which content in an
uploaded PDF is the *cut contour* vs. the *print content* by reading the
PDF's own Optional Content Group (OCG) — i.e. Illustrator "layer" — names,
instead of (as today) treating every single vector path on the page as
contour geometry regardless of what layer it's on.

**Why this is needed:** `server/core/shape_inspect.py`'s `inspect_shape_pdf`
currently treats *every visible vector path anywhere on the page* as
cut-contour geometry (see its own module docstring: "every vector path in
the file counts, no color/layer filtering"). That's fine for simple files,
but breaks the moment a design has vector elements that are NOT meant as
cut lines (a logo drawn as a vector shape, decorative vector lines on the
artwork layer, etc.) — those get incorrectly folded into the cut-contour
geometry. Real client files already routinely separate this by Illustrator
layer (see `_load_with_all_layers_visible`'s own docstring, which describes
a real client file with a layer literally named "Різ" (=cut, Ukrainian)
that was OFF by default). The plan is to use that existing separation, when
present, to scope contour extraction to only the layer(s) that are actually
named as a cut/contour layer.

**Scope of THIS prompt (Prompt 1 — detection only, no behavior change):**
Add a new, purely additive detection/classification step that reads a PDF's
OCG layers, classifies each one as "cut contour" / "print content" /
"unknown" by name using a multilingual keyword list, and reports this as a
new read-only field on the existing `/api/analyze-shape` response. **Do NOT
change what `inspect_shape_pdf` treats as contour geometry, do NOT change
`extract_raster_only_pdf`, do NOT touch any `/api/generate-shape*` route or
PDF-generation code, and do NOT touch the frontend (`web/`) at all.**
Every existing file that works today must keep producing byte-identical
`dim_w`/`dim_h`/`contour`/`thumbnail` output — this prompt only *adds* a new
field alongside the existing ones. Restricting actual contour extraction to
the detected layer, and building the UI for it (including a manual
picker for files where detection is ambiguous), is **Prompt 2**, written
separately after seeing this prompt's findings — do not attempt either of
those here.

**Applies to both "Фігурні стікери" and "Стікерпаки" sidebar modes** — no
extra work needed for that: both already go through the same
`/api/analyze-shape` → `inspect_shape_pdf` code path, so extending that one
function covers both.

## STEP 0 — FEASIBILITY SPIKE (do this first, before writing the real code)

We know `doc.get_ocgs()` (PyMuPDF) returns `{xref: {"name": ..., "on": bool,
...}}` — this project's own code already calls it in
`_load_with_all_layers_visible` in `server/core/shape_inspect.py`, so OCG
*names* are already proven readable. What's **not yet confirmed** is
whether a specific vector drawing (as returned by `page.get_drawings()` /
`page.get_drawings(extended=True)`, which `_visible_drawings` already uses)
can be mapped back to *which* OCG it belongs to. That mapping is the crux of
the whole feature, so verify it concretely before building anything:

1. Using PyMuPDF directly (no need for reportlab), build a small throwaway
   test script (not committed — scratch only) that:
   - Creates a new in-memory PDF page with `fitz.open()` / `new_page(...)`.
   - Adds two OCGs with `doc.add_ocg("Cut Contour", on=True)` and
     `doc.add_ocg("Print Art", on=True)` (or similar names).
   - Draws a rectangle assigned to the first OCG (check whether
     `page.draw_rect(..., oc=<xref>)` — or whichever drawing method accepts
     an `oc=` parameter in the installed PyMuPDF version — actually tags the
     drawn content with that OCG; look this up in the installed PyMuPDF's
     own docs/docstrings, don't guess the signature) and inserts an image
     assigned to the second OCG.
   - Re-opens/re-reads the page (`page.get_drawings(extended=True)` and, if
     it exists in the installed version, `page.get_cdrawings()`) and checks
     whether any field in the returned dicts (per-item or per-"group" entry)
     identifies the owning OCG — e.g. an `"oc"` / `"seqno"` key, or
     anything else that correlates.
   - If the high-level drawing APIs don't expose this, fall back to reading
     the raw page content stream (`page.read_contents()`) and looking for
     marked-content `/OC /MCn BDC ... EMC` blocks wrapping the drawing
     operators, then resolving `/MCn` through the page's
     `/Resources/Properties` dictionary to the OCG's xref (pypdf can read
     these low-level objects if PyMuPDF doesn't expose them conveniently).
     Confirm whether this fallback is actually necessary or the high-level
     API already works.

2. Separately, spend at most ~15 minutes checking whether **non-OCG
   "groups"** (a plain Illustrator sub-group that was never promoted to a
   top-level Acrobat/Illustrator layer) have *any* retrievable name via
   standard PDF structures — check the page's `/Group` dictionary and, if
   you can produce or find a real Illustrator-exported PDF with named
   sub-groups, look for Illustrator's private `/Illustrator` /
   `AI*PrivateData` resources. Our working assumption (base this on what
   you actually find, don't just assert it) is that this is **not**
   reliably retrievable through standard PDF tooling — Illustrator's Layers
   panel group names are normally internal to the .ai/.pdf's private data
   and are lost or inaccessible through standard export unless the group
   was promoted to an OCG/top-level layer. If you find a reliable way to
   read them anyway, note it, but do not build support for it in this
   prompt regardless — just document the finding for Prompt 2 to decide on.

3. Write up exactly what you found in the Summary (STEP 6 below) — the
   actual field names / API calls that work in the PyMuPDF version this
   project has pinned (`requirements.txt`), and whether the marked-content
   fallback was needed. **This determines how STEP 2 below must be
   implemented, so adjust STEP 2's approach to match what you actually
   found working, rather than what's sketched below, if they differ** — the
   sketch is a reasonable starting guess, not gospel.

## STEP 1 — server/models.py — new response fields

Add near the other Contour* models:

```python
class LayerInfo(BaseModel):
    xref: int
    name: str
    role: str  # "cut_contour" | "print_content" | "unknown"


class LayerDetectionInfo(BaseModel):
    # "none": 0 or 1 OCG layers found on the page — not a layered file,
    #         existing flat single-pass extraction is authoritative.
    # "confident": 2+ layers found and exactly one matched the cut-contour
    #         keyword list — that layer is the suggested contour source.
    # "ambiguous": 2+ layers found but 0 or 2+ of them matched the
    #         cut-contour keyword list — can't tell automatically.
    classification: str
    layers: list[LayerInfo]
    contour_layer_xref: int | None = None  # set only when classification == "confident"
```

Add `layer_info: LayerDetectionInfo` to `ShapeAnalyzeResponse` (after
`contour`, not replacing anything).

## STEP 2 — server/core/shape_inspect.py — detection + keyword classification

Add a multilingual keyword list as a module-level constant. Start from this
list, but you're expected to sanity-check and extend it with any other
reasonable real-world variants you think of (common abbreviations,
"diecut"/"die cut" spacing variants, typos you'd realistically see from a
designer) — note in the Summary anything you added beyond this starting
set:

```python
# Layer-name keywords that identify a cut/contour layer, matched against a
# normalized (lowercased, separators collapsed to spaces) layer name — see
# _classify_layer_name below. English, Ukrainian, and Russian variants,
# since real client files use all three depending on the designer.
_CONTOUR_KEYWORDS = [
    # English
    "cut", "cutline", "cut line", "cutpath", "cut path", "cutting",
    "contour", "dieline", "die line", "die", "die cut", "diecut",
    "kiss", "kisscut", "kiss cut", "perf", "perforation",
    "knife", "blade", "route", "rout", "laser", "plotter", "trim",
    # Ukrainian
    "різ", "контур різу", "лінія різу", "різка", "висічка", "вирубка",
    "ніж", "ножовий контур", "кісс", "кісс-різ", "кісс різ",
    "перфорація", "лазер", "плотер", "різак",
    # Russian
    "рез", "контур реза", "линия реза", "резка", "высечка", "вырубка",
    "нож", "ножевой контур", "кисс", "кисс-рез", "кисс рез",
    "перфорация", "лазер", "плоттер", "резак",
]

# Secondary/optional — layer-name keywords that identify a print-content
# layer. Not required for classification (see _classify_layer_name: a
# layer is "print_content" by elimination once another layer confidently
# matches _CONTOUR_KEYWORDS), but useful for logging/diagnostics and for
# Prompt 2's UI to show a friendlier label than "unknown".
_CONTENT_KEYWORDS = [
    "print", "art", "artwork", "design", "content", "image", "graphic",
    "graphics", "cmyk", "raster", "artboard",
    "друк", "дизайн", "малюнок", "зображення", "растр", "контент", "макет",
    "печать", "дизайн", "рисунок", "изображение", "растр", "контент", "макет",
]
```

Add a normalization + matching helper and the detection function (adjust
the actual OCG→drawing mapping mechanism to whatever STEP 0 found works):

```python
def _normalize_layer_name(name: str) -> str:
    norm = name.strip().lower()
    for sep in ("-", "_", "."):
        norm = norm.replace(sep, " ")
    return " ".join(norm.split())


def _layer_matches(norm_name: str, keywords: list[str]) -> bool:
    return any(kw in norm_name for kw in keywords)


def detect_layers(path: str) -> "LayerDetectionResult":
    """Read this PDF's OCG layers (if any) and classify each one as a
    likely cut-contour or print-content source by name, using
    _CONTOUR_KEYWORDS/_CONTENT_KEYWORDS. Purely diagnostic — does not
    change what inspect_shape_pdf treats as contour geometry (that's
    Prompt 2). See STEP 0's findings for how layer membership of specific
    drawings is actually determined, if this function ends up needing it —
    it may turn out this function only needs doc.get_ocgs() names and
    doesn't need per-drawing OCG membership at all for the "classification"
    verdict itself (that mapping is only needed once Prompt 2 actually
    restricts extraction to one layer).
    """
    ...
```

(Define a small `LayerDetectionResult` dataclass mirroring
`LayerDetectionInfo` from STEP 1, same shape, in this module — same
pattern `ShapeArtworkInfo` already follows relative to `ShapeAnalyzeResponse`.)

Classification logic:
- 0 or 1 OCG layers on the page → `classification="none"`, `layers` lists
  whatever was found (0 or 1 entries), `contour_layer_xref=None`.
- 2+ OCG layers → normalize each name, check against `_CONTOUR_KEYWORDS`.
  - Exactly one layer matches → `classification="confident"`, that layer's
    `role="cut_contour"`, every other layer gets `role="print_content"`,
    `contour_layer_xref` set to the matching layer's xref.
  - Zero or 2+ layers match → `classification="ambiguous"`, every layer's
    `role="unknown"` (you may set `role="print_content"` for layers that
    match `_CONTENT_KEYWORDS` if you find that adds real signal — your
    call, just document what you did).

## STEP 3 — wire into inspect_shape_pdf + the route

In `inspect_shape_pdf` (`server/core/shape_inspect.py`), call `detect_layers`
and add its result onto `ShapeArtworkInfo` as a new field (same file, same
dataclass pattern as the existing fields). **Do not use this result to
change `dim_w`/`dim_h`/`subpaths`/anything else already computed in this
function — it's an extra, independent field.**

In `server/routes/analyze_shape.py`, pass that field through to
`ShapeAnalyzeResponse(..., layer_info=...)`.

## STEP 4 — SMOKE TEST

1. Build 3 small synthetic test PDFs with PyMuPDF (same technique as your
   STEP 0 spike) and run them through `/api/analyze-shape` (server running
   locally via `python run_server.py`, `curl -F` or a short Python script
   using `requests`):
   - **No OCG layers at all** (today's typical file) → confirm
     `layer_info.classification == "none"` and every other response field
     (`dim_w`, `dim_h`, `contour.subpaths`, `thumbnail`) is unchanged from
     what this exact file produced before this prompt's changes (diff the
     JSON response against a copy saved before you started, minus the new
     `layer_info` field).
   - **Two OCG layers, one named unambiguously** (e.g. "Cut Contour" +
     "Print Art") → confirm `classification == "confident"`,
     `contour_layer_xref` points at the right layer.
   - **Two OCG layers, neither name matching any keyword** (e.g. "Layer 1"
     + "Layer 2") → confirm `classification == "ambiguous"`.
2. Also test at least one Ukrainian-named and one Russian-named variant
   (e.g. a layer named "Різ" and one named "Рез") to confirm the keyword
   list actually matches them — this is the main point of the multilingual
   list, don't skip it.
3. Confirm `/api/generate-shape` and `/api/generate-batch-shape` still
   produce identical output to before this prompt (unchanged code path) —
   run one existing real test file through generation and confirm the
   output PDF/zip is byte-identical or at least visually identical to a
   pre-change run.
4. Confirm the "Стікерпаки" tab's flow (same endpoint) also returns the new
   `layer_info` field — no separate test file needed, just confirm nothing
   in the route requires the sticker-pack-specific fields to be present.

## STEP 5 — CLAUDE.md

Append a short entry to "Останній стан": what `layer_info` is, that it's
diagnostic-only (STEP 3's note — nothing consumes it yet), and a one-line
pointer that Prompt 2 (not yet written) will use it to restrict contour
extraction and add a manual-override UI for the "ambiguous" case.

## STEP 6 — COMMIT + PUSH

```
git add server/models.py server/core/shape_inspect.py server/routes/analyze_shape.py CLAUDE.md
git commit -m "feat: detect and classify PDF OCG layers for cut-contour vs print-content (diagnostic only)"
git push origin main
```

## STEP 7 — SUMMARY

### ✅ Completed
### ⚠️ Issues encountered
### 🔴 Not implemented
### 🧪 Smoke test results (all points from STEP 4, including the actual JSON `layer_info` for each synthetic file)
### 📋 STEP 0 feasibility findings (required — this is the most important part of this Summary)
- Exact PyMuPDF API/field that maps a drawing to its owning OCG (or confirmation the marked-content fallback was needed, and why).
- Whether non-OCG "group" names turned out to be retrievable at all, and how you checked.
- Any keyword-list additions you made beyond the starting list in STEP 2.
### 📋 Known issues for next session
