import math
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from server import session_store
from server.core.layout import resolve_grid
from server.core.packaging import build_shape_zip
from server.core.shape_contour_pdf import generate_shape_contour_pdf
from server.core.shape_inspect import extract_raster_only_pdf, inspect_shape_pdf
from server.core.shape_plt_writer import generate_shape_plt
from server.core.shape_print_pdf import generate_shape_print_pdf
from server.models import ShapeGenerateRequest
from server.utils.naming import build_folder_name, build_print_filename, fmt_dim, get_unique_path

router = APIRouter()


@router.post("/api/generate-shape")
def generate_shape(payload: ShapeGenerateRequest, background_tasks: BackgroundTasks) -> FileResponse:
    try:
        artwork_path, artwork_filename = session_store.get_upload(payload.upload_id)
    except KeyError as exc:
        raise HTTPException(404, exc.args[0]) from exc

    # Never trust a client-supplied size for this mode — re-derive the
    # authoritative dim_w/dim_h and cut contour straight from the file.
    try:
        info = inspect_shape_pdf(artwork_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    grid = resolve_grid(
        info.dim_w, info.dim_h, payload.sheet_w, payload.sheet_h,
        payload.mark_offset, payload.field_margin, 0,
        orientation=payload.orientation, cols=payload.cols, rows=payload.rows,
    )
    if not grid.fits:
        raise HTTPException(400, "Сітка не вміщується на аркуші з поточними параметрами")

    if not payload.material.strip():
        raise HTTPException(400, "Матеріал обов'язковий")

    work_dir = session_store.new_work_dir()
    try:
        # Raster-only copy of the artwork — the cut-contour vector lines must
        # never print, only the print PDF's own drawn-fresh geometry may.
        raster_only_pdf = os.path.join(work_dir, "_raster_only.pdf")
        extract_raster_only_pdf(artwork_path, raster_only_pdf)

        # Descriptive base name only — unlike the rectangular flow, shaped
        # output has no template subfolder, so this never becomes a directory.
        base_name = build_folder_name(
            grid.cell_w, grid.cell_h, grid.cols, grid.rows,
            grid.orientation, payload.sheet_name, grid.gap,
        )

        plt_file = os.path.join(work_dir, base_name + ".plt")
        generate_shape_plt(plt_file, grid, info.subpaths, info.dim_w, info.dim_h)

        contour_pdf = None
        if payload.cut_contour:
            contour_pdf = os.path.join(work_dir, base_name + " - контур.pdf")
            generate_shape_contour_pdf(contour_pdf, grid, info.subpaths, info.dim_w, info.dim_h)

        stickers_per_sheet = grid.count
        sheets_needed = math.ceil(payload.quantity / stickers_per_sheet)
        actual_qty = sheets_needed * stickers_per_sheet

        size_str = f"{fmt_dim(min(grid.cell_w, grid.cell_h))}x{fmt_dim(max(grid.cell_w, grid.cell_h))}"
        print_filename = build_print_filename(
            payload.order.strip(), payload.material.strip(),
            size_str, actual_qty, sheets_needed,
            artwork_filename=artwork_filename,
        )
        print_path = get_unique_path(work_dir, print_filename)
        generate_shape_print_pdf(print_path, raster_only_pdf, grid)

        zip_path = os.path.join(work_dir, "output.zip")
        build_shape_zip(zip_path, print_path, plt_file, contour_pdf)
    except Exception:
        session_store.cleanup_dir(work_dir)
        raise

    # Keep the uploaded artwork around, same as the rectangular flow's /api/generate.
    session_store.touch_upload(payload.upload_id)
    background_tasks.add_task(session_store.cleanup_dir, work_dir)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{base_name}.zip",
        background=background_tasks,
    )
