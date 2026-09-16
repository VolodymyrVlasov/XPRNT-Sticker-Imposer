import math
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from server import session_store
from server.core.cut_contour_pdf import generate_cut_contour_pdf
from server.core.layout import resolve_grid
from server.core.packaging import build_batch_zip
from server.core.pdf_template import generate_template_pdf
from server.core.plt_writer import generate_plt
from server.core.print_pdf import generate_print_pdf
from server.models import BatchGenerateRequest
from server.utils.naming import build_folder_name, build_print_filename, fmt_dim, get_unique_path

router = APIRouter()


@router.post("/api/generate-batch")
def generate_batch(payload: BatchGenerateRequest, background_tasks: BackgroundTasks) -> FileResponse:
    if not payload.items:
        raise HTTPException(400, "Немає файлів для обробки")
    if not payload.material.strip():
        raise HTTPException(400, "Матеріал обов'язковий")

    work_dir = session_store.new_work_dir()
    template_folders: dict[str, list[str]] = {}
    print_paths: list[str] = []

    try:
        for item in payload.items:
            try:
                artwork_path, artwork_filename = session_store.get_upload(item.upload_id)
            except KeyError as exc:
                raise HTTPException(404, f"{exc.args[0]} ({item.upload_id})") from exc

            # Batch mode always auto-fits, at the artwork's own native size —
            # no per-item manual grid/size override, no gap.
            grid = resolve_grid(
                item.dim_w, item.dim_h, payload.sheet_w, payload.sheet_h,
                payload.mark_offset, payload.field_margin, 0,
                orientation=payload.orientation,
            )
            if not grid.fits:
                raise HTTPException(
                    400,
                    f"«{artwork_filename}» ({fmt_dim(item.dim_w)}x{fmt_dim(item.dim_h)} мм) "
                    "не вміщується на аркуші з поточними параметрами",
                )

            folder_name = build_folder_name(
                grid.cell_w, grid.cell_h, grid.cols, grid.rows,
                grid.orientation, payload.sheet_name, grid.gap,
            )
            if folder_name in template_folders:
                tpl_pdf = template_folders[folder_name][0]
            else:
                template_dir = os.path.join(work_dir, folder_name)
                os.makedirs(template_dir, exist_ok=True)
                tpl_pdf = os.path.join(template_dir, folder_name + ".pdf")
                plt_file = os.path.join(template_dir, folder_name + ".plt")
                generate_template_pdf(tpl_pdf, grid, folder_name)
                generate_plt(plt_file, grid)
                files = [tpl_pdf, plt_file]
                if payload.cut_contour:
                    contour_pdf = os.path.join(template_dir, folder_name + " - contour.pdf")
                    generate_cut_contour_pdf(contour_pdf, grid)
                    files.append(contour_pdf)
                template_folders[folder_name] = files

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
            generate_print_pdf(print_path, tpl_pdf, artwork_path, grid)
            print_paths.append(print_path)

        zip_path = os.path.join(work_dir, "output.zip")
        build_batch_zip(zip_path, print_paths, template_folders)
    except Exception:
        session_store.cleanup_dir(work_dir)
        raise

    for item in payload.items:
        session_store.touch_upload(item.upload_id)
    background_tasks.add_task(session_store.cleanup_dir, work_dir)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"batch - {len(payload.items)} файлів.zip",
        background=background_tasks,
    )
