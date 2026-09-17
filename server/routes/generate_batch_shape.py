import math
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from server import session_store
from server.core.layout import resolve_grid
from server.core.packaging import build_shape_batch_zip
from server.core.shape_contour_pdf import generate_shape_contour_pdf
from server.core.shape_inspect import extract_raster_only_pdf, inspect_shape_pdf
from server.core.shape_plt_writer import generate_shape_plt
from server.core.shape_print_pdf import generate_shape_print_pdf
from server.models import ShapeBatchGenerateRequest
from server.utils.naming import build_folder_name, build_print_filename, extract_artwork_name, fmt_dim, get_unique_path

router = APIRouter()


@router.post("/api/generate-batch-shape")
def generate_batch_shape(payload: ShapeBatchGenerateRequest, background_tasks: BackgroundTasks) -> FileResponse:
    if not payload.items:
        raise HTTPException(400, "Немає файлів для обробки")
    if not payload.material.strip():
        raise HTTPException(400, "Матеріал обов'язковий")

    work_dir = session_store.new_work_dir()
    zip_items: list[dict] = []

    try:
        for item in payload.items:
            try:
                artwork_path, artwork_filename = session_store.get_upload(item.upload_id)
            except KeyError as exc:
                raise HTTPException(404, f"{exc.args[0]} ({item.upload_id})") from exc

            # Never trust a client-supplied size for this mode — re-derive the
            # authoritative dim_w/dim_h and cut contour straight from the file,
            # same as the single-file endpoint.
            try:
                info = inspect_shape_pdf(artwork_path, payload.bleed_mm)
            except ValueError as exc:
                raise HTTPException(400, f"«{artwork_filename}»: {exc}") from exc

            # Each item resolves its own grid independently — explicit per-item
            # orientation/cols/rows win, anything left unset auto-fits for that item
            # alone. No gap in batch mode (unchanged).
            grid = resolve_grid(
                info.dim_w, info.dim_h, payload.sheet_w, payload.sheet_h,
                payload.mark_offset, payload.field_margin, 0,
                orientation=item.orientation, cols=item.cols, rows=item.rows,
            )
            if not grid.fits:
                raise HTTPException(
                    400,
                    f"«{artwork_filename}» ({fmt_dim(info.dim_w)}x{fmt_dim(info.dim_h)} мм) "
                    "не вміщується на аркуші з поточними параметрами",
                )

            # No dedup — two shaped-sticker uploads can share a bounding box
            # (same grid-based base name) while being completely different
            # cut shapes, so every item always gets its own print PDF / PLT /
            # contour PDF. Fold the artwork's own label into the base name so
            # same-bbox items don't collide, with get_unique_path as a
            # further safety net.
            grid_base_name = build_folder_name(
                grid.cell_w, grid.cell_h, grid.cols, grid.rows,
                grid.orientation, payload.sheet_name, grid.gap,
            )
            item_base_name = f"{grid_base_name} - {extract_artwork_name(artwork_filename)}"

            raster_only_pdf = os.path.join(work_dir, f"_raster_only_{len(zip_items)}.pdf")
            extract_raster_only_pdf(artwork_path, raster_only_pdf, info.page_box_pt)

            plt_path = get_unique_path(work_dir, item_base_name + ".plt")
            generate_shape_plt(plt_path, grid, info.subpaths, info.dim_w, info.dim_h)

            contour_path = None
            if payload.cut_contour:
                contour_path = get_unique_path(work_dir, item_base_name + " - контур.pdf")
                generate_shape_contour_pdf(contour_path, grid, info.subpaths, info.dim_w, info.dim_h)

            stickers_per_sheet = grid.count
            sheets_needed = math.ceil(item.quantity / stickers_per_sheet)
            actual_qty = sheets_needed * stickers_per_sheet

            size_str = f"{fmt_dim(min(grid.cell_w, grid.cell_h))}x{fmt_dim(max(grid.cell_w, grid.cell_h))}"
            print_filename = build_print_filename(
                payload.order.strip(), payload.material.strip(),
                size_str, actual_qty, sheets_needed,
                artwork_filename=artwork_filename,
            )
            print_path = get_unique_path(work_dir, print_filename)
            generate_shape_print_pdf(print_path, raster_only_pdf, grid)

            zip_items.append({"print_pdf": print_path, "plt": plt_path, "contour_pdf": contour_path})

        zip_path = os.path.join(work_dir, "output.zip")
        build_shape_batch_zip(zip_path, zip_items)
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
