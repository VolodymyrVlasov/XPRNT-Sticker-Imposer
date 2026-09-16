from pydantic import BaseModel, Field


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


class BatchItem(BaseModel):
    upload_id: str
    dim_w: float = Field(gt=0)
    dim_h: float = Field(gt=0)


class BatchGenerateRequest(BaseModel):
    items: list[BatchItem]
    sheet_name: str
    sheet_w: float = Field(gt=0)
    sheet_h: float = Field(gt=0)
    mark_offset: float = Field(ge=0)
    field_margin: float = Field(ge=0)
    orientation: str | None = None
    order: str
    material: str
    quantity: int = Field(gt=0)
    cut_contour: bool = False
