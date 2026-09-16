import math
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from server import session_store
from server.core.cut_contour_pdf import generate_cut_contour_pdf
from server.core.layout import resolve_grid
from server.core.packaging import build_zip
from server.core.pdf_template import generate_template_pdf
from server.core.plt_writer import generate_plt
from server.core.print_pdf import generate_print_pdf
from server.models import GenerateRequest
from server.utils.naming import build_folder_name, build_print_filename, fmt_dim, get_unique_path

router = APIRouter()


@router.post("/api/generate")
def generate(payload: GenerateRequest, background_tasks: BackgroundTasks) -> FileResponse:
    try:
        artwork_path, artwork_filename = session_store.get_upload(payload.upload_id)
    except KeyError as exc:
        raise HTTPException(404, exc.args[0]) from exc

    li = payload.layout
    grid = resolve_grid(
        li.dim_w, li.dim_h, li.sheet_w, li.sheet_h,
        li.mark_offset, li.field_margin, li.gap,
        orientation=li.orientation, cols=li.cols, rows=li.rows,
    )
    if not grid.fits:
        raise HTTPException(400, "Сітка не вміщується на аркуші з поточними параметрами")

    if not payload.material.strip():
        raise HTTPException(400, "Матеріал обов'язковий")

    work_dir = session_store.new_work_dir()
    try:
        folder_name = build_folder_name(
            grid.cell_w, grid.cell_h, grid.cols, grid.rows,
            grid.orientation, payload.sheet_name, grid.gap,
        )
        template_dir = os.path.join(work_dir, folder_name)
        os.makedirs(template_dir, exist_ok=True)

        tpl_pdf = os.path.join(template_dir, folder_name + ".pdf")
        plt_file = os.path.join(template_dir, folder_name + ".plt")
        generate_template_pdf(tpl_pdf, grid, folder_name)
        generate_plt(plt_file, grid)
        template_files = [tpl_pdf, plt_file]

        if payload.cut_contour:
            contour_pdf = os.path.join(template_dir, folder_name + " - contour.pdf")
            generate_cut_contour_pdf(contour_pdf, grid)
            template_files.append(contour_pdf)

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
        generate_print_pdf(print_path, tpl_pdf, artwork_path, grid, deform=payload.deform)

        zip_path = os.path.join(work_dir, "output.zip")
        build_zip(zip_path, print_path, folder_name, template_files)
    except Exception:
        session_store.cleanup_dir(work_dir)
        raise

    # Keep the uploaded artwork around — the same session may generate again
    # with tweaked parameters without re-uploading (dropped by /api/session
    # on "new task", or by TTL if the tab is just left open).
    session_store.touch_upload(payload.upload_id)
    background_tasks.add_task(session_store.cleanup_dir, work_dir)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{folder_name}.zip",
        background=background_tasks,
    )
