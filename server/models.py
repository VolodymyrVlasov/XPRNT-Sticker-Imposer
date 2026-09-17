from pydantic import BaseModel, Field

from server.utils.constants import SHAPE_BLEED_MM


class LayoutInput(BaseModel):
    dim_w: float = Field(gt=0)
    dim_h: float = Field(gt=0)
    sheet_w: float = Field(gt=0)
    sheet_h: float = Field(gt=0)
    mark_offset: float = Field(ge=0)
    field_margin: float = Field(ge=0)
    gap: float = Field(ge=0)
    orientation: str | None = None   # "WIDE" | "TALL" | None -> auto-pick
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)


class LayoutResult(BaseModel):
    orientation: str
    cell_w: float
    cell_h: float
    cols: int
    rows: int
    max_cols: int
    max_rows: int
    gap: float
    grid_w: float
    grid_h: float
    grid_x: float
    grid_y: float
    sheet_w: float
    sheet_h: float
    mark_offset: float
    field_margin: float
    fits: bool
    count: int


class AnalyzeResponse(BaseModel):
    upload_id: str
    filename: str
    dim_w: float
    dim_h: float
    page_count: int
    sheet_name: str
    layout: LayoutResult
    thumbnail: str


class GenerateRequest(BaseModel):
    upload_id: str
    layout: LayoutInput
    sheet_name: str
    order: str
    material: str
    quantity: int = Field(gt=0)
    # False (default): uniform contain-fit, artwork keeps its own aspect ratio.
    # True: artwork is stretched independently on X/Y to exactly fill the cell —
    # only meaningful once the sticker size was resized off the artwork's native ratio.
    deform: bool = False
    # Also emit a vector PDF of the cut geometry, for recreating a cut file in
    # third-party cutting software from this layout.
    cut_contour: bool = False
    # Draw a 0.1mm solid black outline frame around every sticker cell.
    outline: bool = False


class BatchItem(BaseModel):
    upload_id: str
    dim_w: float = Field(gt=0)
    dim_h: float = Field(gt=0)
    orientation: str | None = None
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    quantity: int = Field(gt=0)
    deform: bool = False


class ContourSegment(BaseModel):
    kind: str  # "L" or "C"
    points: list[float]


class ContourSubpath(BaseModel):
    start: tuple[float, float]
    segments: list[ContourSegment]
    closed: bool


class ContourGeometry(BaseModel):
    subpaths: list[ContourSubpath]  # relative to the page's own top-left corner (mm)


class ShapeAnalyzeResponse(BaseModel):
    upload_id: str
    filename: str
    dim_w: float  # PDF page size (TrimBox/MediaBox) — feeds the grid math
    dim_h: float
    actual_w: float  # dim_w - 2*bleed_mm — the "actual"/net size, for display
    actual_h: float
    bleed_mm: float
    page_count: int
    sheet_name: str
    layout: LayoutResult
    thumbnail: str
    contour: ContourGeometry


class ShapeGenerateRequest(BaseModel):
    upload_id: str
    sheet_name: str
    sheet_w: float = Field(gt=0)
    sheet_h: float = Field(gt=0)
    mark_offset: float = Field(ge=0)
    field_margin: float = Field(ge=0)
    orientation: str | None = None
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    order: str
    material: str
    quantity: int = Field(gt=0)
    cut_contour: bool = False
    # Draw a 0.1mm solid black outline frame around every sticker cell.
    outline: bool = False
    bleed_mm: float = Field(default=SHAPE_BLEED_MM, ge=0)
    # No dim_w/dim_h/gap/deform — the server re-derives the authoritative size
    # and contour by re-running inspect_shape_pdf on the stored upload, and
    # gap is always 0 for this mode.


class ShapeBatchItem(BaseModel):
    upload_id: str
    orientation: str | None = None
    cols: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    quantity: int = Field(gt=0)


class ShapeBatchGenerateRequest(BaseModel):
    items: list[ShapeBatchItem]
    sheet_name: str
    sheet_w: float = Field(gt=0)
    sheet_h: float = Field(gt=0)
    mark_offset: float = Field(ge=0)
    field_margin: float = Field(ge=0)
    order: str
    material: str
    cut_contour: bool = False
    # Draw a 0.1mm solid black outline frame around every sticker cell.
    outline: bool = False
    bleed_mm: float = Field(default=SHAPE_BLEED_MM, ge=0)
    # No per-item dim_w/dim_h — re-derived server-side per item, same as
    # ShapeGenerateRequest. bleed_mm is shared across every item in the batch,
    # same as sheet_name/material/etc. orientation/cols/rows/quantity are now
    # per-item (see ShapeBatchItem) — only sheet/margins/material/order/
    # cut_contour/bleed_mm stay shared across the whole batch.


class BatchGenerateRequest(BaseModel):
    items: list[BatchItem]
    sheet_name: str
    sheet_w: float = Field(gt=0)
    sheet_h: float = Field(gt=0)
    mark_offset: float = Field(ge=0)
    field_margin: float = Field(ge=0)
    order: str
    material: str
    cut_contour: bool = False
    # Draw a 0.1mm solid black outline frame around every sticker cell.
    outline: bool = False
