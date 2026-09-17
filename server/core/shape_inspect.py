"""Read raster+vector structure from an uploaded PDF for the 'shaped stickers' mode.

Validates the file has both:
  - at least one raster (image) object — the print artwork
  - at least one vector path — the cut contour (every vector path in the file counts,
    no color/layer filtering)
and extracts the vector geometry as a list of closed subpaths (lines + cubic beziers),
in mm, positioned relative to the PDF page's own top-left corner (its TrimBox, or
MediaBox if no TrimBox is defined) — NOT relative to the cut-line's own bounding box.

The sticker's tile size (dim_w/dim_h, which feeds the grid/imposition math) is the
PDF page's own size. The cut-contour's bounding box is irrelevant to sizing — the
contour can be any size, anywhere within the page. Bleed is a caller-supplied
parameter used only to compute a separate "actual"/net size for display.

Coordinate note: PyMuPDF's page-space coordinates (as returned by get_drawings/
get_images) have their origin at the page's TOP-LEFT corner with Y increasing
DOWNWARD, in points — this already matches this project's mm convention (see
server/core/layout.py's module docstring), confirmed empirically with a synthetic
PDF. So converting is just a division by MM, no axis flip needed.
"""

from dataclasses import dataclass, field

from server.utils.constants import MM

# Tolerance (in PDF points) for treating two path endpoints as "the same point"
# when grouping raw drawing items into subpaths / detecting closure.
_POINT_EPS = 0.05

# Below this cumulative opacity, a drawing is treated as invisible/never painted.
_OPACITY_EPS = 0.01


@dataclass
class ContourSegment:
    kind: str  # "L" (line) or "C" (cubic bezier)
    # for "L": (x, y) end point
    # for "C": (x1, y1, x2, y2, x, y) — two control points + end point
    points: tuple[float, ...]


@dataclass
class ContourSubpath:
    start: tuple[float, float]
    segments: list[ContourSegment] = field(default_factory=list)
    closed: bool = False


@dataclass
class ShapeArtworkInfo:
    dim_w: float  # PDF page width (TrimBox if present else MediaBox), mm — feeds
    # the grid/imposition math, exactly like before; just no longer bleed-derived.
    dim_h: float
    actual_w: float  # dim_w - 2*bleed_mm — the displayed "actual"/net sticker
    # size (see module docstring). Display only — never feeds grid math.
    actual_h: float
    bleed_mm: float  # the bleed value actually used to compute actual_w/actual_h
    page_count: int
    subpaths: list[ContourSubpath]  # coordinates relative to the PAGE's own
    # top-left corner (mm) — i.e. relative to page_box_pt's own (x0, y0), not
    # inset by any bleed amount.
    page_box_pt: tuple[float, float, float, float]  # (x0, y0, x1, y1) — the
    # page's own TrimBox (or MediaBox) in the SOURCE PDF's own point space. This
    # is exactly the region extract_raster_only_pdf should crop the artwork to.


def _load_with_all_layers_visible(path: str) -> "fitz.Document":
    """Open the PDF with every Optional Content Group (Illustrator "layer")
    forced to visible, regardless of the file's own default layer-visibility
    state.

    Real client files routinely have a layer toggled OFF/hidden in Illustrator —
    most commonly the cut-contour layer, hidden for a clean design view while
    still expected to be read by prepress/plotter tooling. Verified on a real
    client file: a rounded-rect cut contour on a layer literally named "Різ"
    (OFF by default in /OCProperties/D/OFF) was completely invisible to
    page.get_drawings() — no trace of it at all, even in extended mode — while
    the identical geometry on a visible layer was found normally.
    page.get_image_info(xrefs=True) (used by extract_raster_only_pdf below) has
    the same blind spot, so this is applied to raster extraction too, in case
    the design/raster layer is ever the hidden one instead.

    This only affects layer VISIBILITY, never which paths count as contour
    geometry — every vector path in the file still counts regardless of which
    layer it's on or what that layer is named, per this module's original
    design (see the module docstring).

    Note: doc.set_layer() alone updates the OCG config dict, but
    get_drawings()/get_image_info() on the SAME live Document object do not
    pick up the change — only a freshly (re)parsed document does, hence the
    tobytes() + reopen round-trip below.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    ocgs = doc.get_ocgs()
    if not ocgs:
        return doc
    doc.set_layer(-1, on=list(ocgs.keys()), off=[])
    buf = doc.tobytes()
    doc.close()
    return fitz.open(stream=buf, filetype="pdf")


def _points_close(a, b) -> bool:
    return abs(a.x - b.x) <= _POINT_EPS and abs(a.y - b.y) <= _POINT_EPS


def _flatten_items(items: list) -> list[tuple]:
    """Flatten a drawing's raw 'items' into a list of (kind, start, end, extra) tuples,
    where kind is "L" or "C", start/end are fitz.Point, and extra holds the two
    control points for "C" (else None). 're' and 'qu' items are expanded into their
    4 constituent line segments.
    """
    import fitz  # PyMuPDF

    flat = []
    for it in items:
        code = it[0]
        if code == "l":
            p1, p2 = it[1], it[2]
            flat.append(("L", p1, p2, None))
        elif code == "c":
            p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
            flat.append(("C", p1, p4, (p2, p3)))
        elif code == "re":
            rect = it[1]
            corners = [
                fitz.Point(rect.x0, rect.y0),
                fitz.Point(rect.x1, rect.y0),
                fitz.Point(rect.x1, rect.y1),
                fitz.Point(rect.x0, rect.y1),
            ]
            for i in range(4):
                flat.append(("L", corners[i], corners[(i + 1) % 4], None))
        elif code == "qu":
            quad = it[1]
            corners = [quad.ul, quad.ur, quad.lr, quad.ll]
            for i in range(4):
                flat.append(("L", corners[i], corners[(i + 1) % 4], None))
        # unknown item codes are ignored
    return flat


def _group_subpaths_pt(items: list) -> list[list[tuple]]:
    """Group flattened (kind, start, end, extra) segments into subpaths (still in raw
    PDF points), splitting whenever a segment's start doesn't match the previous
    segment's end.
    """
    subpaths: list[list[tuple]] = []
    current: list[tuple] | None = None

    for seg in _flatten_items(items):
        _kind, p_start, _p_end, _extra = seg
        if current is None or not _points_close(p_start, current[-1][2]):
            current = []
            subpaths.append(current)
        current.append(seg)

    return subpaths


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


# Rounding for the duplicate-detection fingerprint in _subpath_key(). Intentionally
# much tighter than the ~0.01mm float-noise tolerance already accepted elsewhere in
# this module (see the dim_w/dim_h rounding comment below) — this exists only to
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


def extract_raster_only_pdf(
    path: str, output_path: str, page_box_pt: tuple[float, float, float, float],
) -> None:
    """Write a copy of page 0's raster image(s), CROPPED to `page_box_pt` (the
    page's own TrimBox, or MediaBox if no TrimBox is defined — see
    ShapeArtworkInfo.page_box_pt), with all vector paths stripped.

    The new page is sized exactly to that box, and images are re-inserted
    shifted so the box's own origin becomes (0, 0) — this is what gets tiled
    into the print PDF, since the cut-contour vector lines must never be
    printed, and the artwork must not be padded by any extra canvas margin the
    source page happened to have around the actual bleed-inclusive tile.
    """
    import fitz  # PyMuPDF

    src = _load_with_all_layers_visible(path)
    try:
        if src.page_count == 0:
            raise ValueError("PDF не містить сторінок")
        page = src[0]

        images_info = [i for i in page.get_image_info(xrefs=True) if i.get("xref")]
        if not images_info:
            raise ValueError(
                "У файлі не знайдено растрового шару для друку — "
                "додайте зображення для друку як растровий об'єкт"
            )

        box_x0, box_y0, box_x1, box_y1 = page_box_pt

        out = fitz.open()
        try:
            new_page = out.new_page(width=box_x1 - box_x0, height=box_y1 - box_y0)
            for info in images_info:
                xref = info["xref"]
                img_bytes = src.extract_image(xref)["image"]
                bx0, by0, bx1, by1 = info["bbox"]
                cropped_rect = fitz.Rect(bx0 - box_x0, by0 - box_y0, bx1 - box_x0, by1 - box_y0)
                new_page.insert_image(cropped_rect, stream=img_bytes)
            out.save(output_path)
        finally:
            out.close()
    finally:
        src.close()


def inspect_shape_pdf(path: str, bleed_mm: float) -> ShapeArtworkInfo:
    """Raises ValueError with a clear Ukrainian message on any validation failure."""
    import fitz  # PyMuPDF

    try:
        doc = _load_with_all_layers_visible(path)
    except Exception as exc:
        raise ValueError(f"Не вдалося прочитати PDF: {exc}") from exc

    try:
        if doc.page_count == 0:
            raise ValueError("PDF не містить сторінок")

        page = doc[0]

        images = page.get_images(full=True)
        if not images:
            raise ValueError(
                "У файлі не знайдено растрового шару для друку — "
                "додайте зображення для друку як растровий об'єкт"
            )

        drawings = _visible_drawings(page)
        if not drawings:
            raise ValueError(
                "У файлі не знайдено векторного контуру порізки — "
                "додайте векторні лінії, що визначають лінію різу"
            )

        page_box = page.trimbox  # falls back to MediaBox automatically when no
        # TrimBox is defined on the page (verified empirically) — same convention
        # as server/core/pdf_inspect.py's pypdf-based TrimBox-else-MediaBox logic.

        # Round here, at the single source of truth both /api/analyze-shape and
        # /api/generate-shape call — otherwise PDF-roundtrip float noise (e.g.
        # 42.00000859830114) makes fmt_dim() treat whole numbers as fractional
        # and print filenames like "32.0x42.0" instead of "32x42". Sub-0.01mm
        # noise in the subpath coordinates themselves is well under cutting
        # precision and doesn't need the same treatment.
        dim_w = round(page_box.width / MM, 2)
        dim_h = round(page_box.height / MM, 2)
        if dim_w <= 0 or dim_h <= 0:
            raise ValueError("Некоректний розмір сторінки PDF")

        actual_w = round(dim_w - 2 * bleed_mm, 2)
        actual_h = round(dim_h - 2 * bleed_mm, 2)
        if actual_w <= 0 or actual_h <= 0:
            raise ValueError(
                "Бліда завелика для розміру сторінки — фактичний розмір наліпки виходить "
                "від'ємним або нульовим"
            )

        def to_mm(p) -> tuple[float, float]:
            return ((p.x - page_box.x0) / MM, (p.y - page_box.y0) / MM)

        subpaths: list[ContourSubpath] = []
        for d in drawings:
            for raw_subpath in _group_subpaths_pt(d["items"]):
                if not raw_subpath:
                    continue
                start_mm = to_mm(raw_subpath[0][1])
                segments: list[ContourSegment] = []
                for kind, _p_start, p_end, extra in raw_subpath:
                    if kind == "L":
                        ex, ey = to_mm(p_end)
                        segments.append(ContourSegment(kind="L", points=(ex, ey)))
                    else:
                        c1x, c1y = to_mm(extra[0])
                        c2x, c2y = to_mm(extra[1])
                        ex, ey = to_mm(p_end)
                        segments.append(
                            ContourSegment(kind="C", points=(c1x, c1y, c2x, c2y, ex, ey))
                        )
                last_end = raw_subpath[-1][2]
                closed = _points_close(last_end, raw_subpath[0][1])
                subpaths.append(ContourSubpath(start=start_mm, segments=segments, closed=closed))

        seen: set = set()
        deduped: list[ContourSubpath] = []
        for sp in subpaths:
            key = _subpath_key(sp)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(sp)
        subpaths = deduped

        return ShapeArtworkInfo(
            dim_w=dim_w,
            dim_h=dim_h,
            actual_w=actual_w,
            actual_h=actual_h,
            bleed_mm=bleed_mm,
            page_count=doc.page_count,
            subpaths=subpaths,
            page_box_pt=(page_box.x0, page_box.y0, page_box.x1, page_box.y1),
        )
    finally:
        doc.close()
