"""Read raster+vector structure from an uploaded PDF for the 'shaped stickers' mode.

Validates the file has both:
  - at least one raster (image) object — the print artwork
  - at least one vector path — the cut contour (every vector path in the file counts,
    no color/layer filtering)
and extracts the vector geometry as a list of closed subpaths (lines + cubic beziers),
in mm, positioned relative to the bleed-inclusive tile's own top-left corner (see
"Bleed" section in the module's issuing prompt) — NOT relative to the raw cut-line
bounding box.

Coordinate note: PyMuPDF's page-space coordinates (as returned by get_drawings/
get_images) have their origin at the page's TOP-LEFT corner with Y increasing
DOWNWARD, in points — this already matches this project's mm convention (see
server/core/layout.py's module docstring), confirmed empirically with a synthetic
PDF. So converting is just a division by MM, no axis flip needed.
"""

from dataclasses import dataclass, field

from server.utils.constants import MM, SHAPE_BLEED_MM

# Tolerance (in PDF points) for treating two path endpoints as "the same point"
# when grouping raw drawing items into subpaths / detecting closure.
_POINT_EPS = 0.05


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
    dim_w: float  # bleed-inclusive tile width (contour bbox + 2*SHAPE_BLEED_MM)
    dim_h: float  # bleed-inclusive tile height
    bleed_mm: float
    page_count: int
    subpaths: list[ContourSubpath]  # coordinates relative to the dim_w x dim_h tile,
    # i.e. already inset by bleed_mm on every side
    bleed_box_pt: tuple[float, float, float, float]  # (x0, y0, x1, y1) — the cut
    # contour's bbox expanded by the bleed on every side, in the SOURCE PDF's own
    # point space (not mm, not yet re-based to the tile's own origin) — this is
    # exactly the region extract_raster_only_pdf should crop the artwork to.


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


def extract_raster_only_pdf(
    path: str, output_path: str, bleed_box_pt: tuple[float, float, float, float],
) -> None:
    """Write a copy of page 0's raster image(s), CROPPED to `bleed_box_pt` (the
    cut contour's bbox expanded by the bleed, in the source PDF's own point
    space — see ShapeArtworkInfo.bleed_box_pt), with all vector paths stripped.

    The new page is sized exactly to that box, and images are re-inserted
    shifted so the box's own origin becomes (0, 0) — this is what gets tiled
    into the print PDF, since the cut-contour vector lines must never be
    printed, and the artwork must not be padded by any extra canvas margin the
    source page happened to have around the actual bleed-inclusive tile.
    """
    import fitz  # PyMuPDF

    src = fitz.open(path)
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

        box_x0, box_y0, box_x1, box_y1 = bleed_box_pt

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


def inspect_shape_pdf(path: str) -> ShapeArtworkInfo:
    """Raises ValueError with a clear Ukrainian message on any validation failure."""
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path)
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

        drawings = [d for d in page.get_drawings() if d.get("items")]
        if not drawings:
            raise ValueError(
                "У файлі не знайдено векторного контуру порізки — "
                "додайте векторні лінії, що визначають лінію різу"
            )

        # Raw cut-contour bounding box, in PDF points, from ALL vector geometry.
        raw_bbox = drawings[0]["rect"]
        for d in drawings[1:]:
            raw_bbox = raw_bbox | d["rect"]

        bleed_pt = SHAPE_BLEED_MM * MM
        offset_x = raw_bbox.x0 - bleed_pt
        offset_y = raw_bbox.y0 - bleed_pt
        bleed_box_pt = (offset_x, offset_y, raw_bbox.x1 + bleed_pt, raw_bbox.y1 + bleed_pt)

        contour_w_mm = raw_bbox.width / MM
        contour_h_mm = raw_bbox.height / MM
        # Round here, at the single source of truth both /api/analyze-shape and
        # /api/generate-shape call — otherwise PDF-roundtrip float noise (e.g.
        # 42.00000859830114) makes fmt_dim() treat whole numbers as fractional
        # and print filenames like "32.0x42.0" instead of "32x42". Sub-0.01mm
        # noise in the subpath coordinates themselves is well under cutting
        # precision and doesn't need the same treatment.
        dim_w = round(contour_w_mm + 2 * SHAPE_BLEED_MM, 2)
        dim_h = round(contour_h_mm + 2 * SHAPE_BLEED_MM, 2)

        def to_mm(p) -> tuple[float, float]:
            return ((p.x - offset_x) / MM, (p.y - offset_y) / MM)

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

        return ShapeArtworkInfo(
            dim_w=dim_w,
            dim_h=dim_h,
            bleed_mm=SHAPE_BLEED_MM,
            page_count=doc.page_count,
            subpaths=subpaths,
            bleed_box_pt=bleed_box_pt,
        )
    finally:
        doc.close()
