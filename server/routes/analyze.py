import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from server import session_store
from server.core.layout import resolve_grid
from server.core.pdf_inspect import inspect_pdf
from server.core.thumbnail import render_thumbnail_data_uri
from server.models import AnalyzeResponse, LayoutResult
from server.utils.constants import DEFAULT_FIELD_MARGIN, DEFAULT_GAP, DEFAULT_MARK_OFFSET, SHEET_PRESETS

router = APIRouter()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@router.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(file: UploadFile = File(...)) -> AnalyzeResponse:
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
        info = inspect_pdf(path)
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

    grid = resolve_grid(
        info.width_mm, info.height_mm,
        sheet_w, sheet_h,
        DEFAULT_MARK_OFFSET, DEFAULT_FIELD_MARGIN, DEFAULT_GAP,
    )

    return AnalyzeResponse(
        upload_id=upload_id,
        filename=os.path.basename(path),
        dim_w=round(info.width_mm, 2),
        dim_h=round(info.height_mm, 2),
        page_count=info.page_count,
        sheet_name=default_sheet,
        layout=LayoutResult(**grid.as_dict()),
        thumbnail=thumbnail,
    )
