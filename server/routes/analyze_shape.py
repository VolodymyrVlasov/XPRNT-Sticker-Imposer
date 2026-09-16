import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from server import session_store
from server.core.layout import resolve_grid
from server.core.shape_inspect import inspect_shape_pdf
from server.core.thumbnail import render_thumbnail_data_uri
from server.models import ContourGeometry, ContourSegment, ContourSubpath, LayoutResult, ShapeAnalyzeResponse
from server.utils.constants import DEFAULT_FIELD_MARGIN, DEFAULT_MARK_OFFSET, SHEET_PRESETS

router = APIRouter()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@router.post("/api/analyze-shape", response_model=ShapeAnalyzeResponse)
async def analyze_shape(file: UploadFile = File(...)) -> ShapeAnalyzeResponse:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Очікується файл PDF")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Файл порожній")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Файл завеликий (ліміт 100 МБ)")

    upload_id = session_store.save_upload(file.filename, data)
    path, _ = session_store.get_upload(upload_id)

    try:
        info = inspect_shape_pdf(path)
    except ValueError as exc:
        session_store.drop_upload(upload_id)
        raise HTTPException(400, str(exc)) from exc

    try:
        thumbnail = render_thumbnail_data_uri(path)
    except Exception as exc:
        session_store.drop_upload(upload_id)
        raise HTTPException(400, f"Не вдалося зробити мініатюру PDF: {exc}") from exc

    default_sheet = "SRA3"
    sheet_w, sheet_h = SHEET_PRESETS[default_sheet]

    # Shaped-sticker tiles are placed flush against each other (gap=0): the 1mm
    # bleed already baked into dim_w/dim_h provides the necessary spacing.
    grid = resolve_grid(
        info.dim_w, info.dim_h,
        sheet_w, sheet_h,
        DEFAULT_MARK_OFFSET, DEFAULT_FIELD_MARGIN, 0,
    )

    contour = ContourGeometry(
        bleed_mm=info.bleed_mm,
        subpaths=[
            ContourSubpath(
                start=sp.start,
                segments=[ContourSegment(kind=seg.kind, points=list(seg.points)) for seg in sp.segments],
                closed=sp.closed,
            )
            for sp in info.subpaths
        ],
    )

    return ShapeAnalyzeResponse(
        upload_id=upload_id,
        filename=os.path.basename(path),
        dim_w=round(info.dim_w, 2),
        dim_h=round(info.dim_h, 2),
        page_count=info.page_count,
        sheet_name=default_sheet,
        layout=LayoutResult(**grid.as_dict()),
        thumbnail=thumbnail,
        contour=contour,
    )
